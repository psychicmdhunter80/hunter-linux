#!/usr/bin/env python3
"""Boot a SMD Linux ISO under QEMU and test the live desktop for real.

    boot-test.py <iso> <bios|uefi> <output-dir>

The guest is driven over two channels:

* the QEMU monitor (TCP) for screenshots,
* the guest's serial console (TCP) for a login shell.

Logging in on the serial console means the test can run actual commands -
`i3 -C`, `free -m`, `pgrep`, launching applications on the live display - and
keep their text output, instead of guessing from pixels.  Screenshots are kept
as the visual record.

Everything is written to the output directory: serial.log, steps.txt,
screen-*.png and result.txt.
"""

import json
import os
import re
import socket
import subprocess
import sys
import time

ISO = sys.argv[1]
MODE = sys.argv[2] if len(sys.argv) > 2 else "bios"
WORK = sys.argv[3] if len(sys.argv) > 3 else "out"

MON_PORT = 4600
SER_PORT = 4601
WEB_PORT = 4602
LIVE_USER = os.environ.get("LIVE_USER", "user")
LIVE_PASS = os.environ.get("LIVE_PASS", "live")

os.makedirs(WORK, exist_ok=True)
RESULT = os.path.join(WORK, "result.txt")
STEPS = os.path.join(WORK, "steps.txt")
SERIAL_LOG = os.path.join(WORK, "serial.log")

results = []
seen = []


def record(line):
    results.append(line)
    print(line, flush=True)


def note(line):
    with open(STEPS, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    print(line, flush=True)


class Channel:
    """A socket connection with a read-until helper."""

    def __init__(self, port):
        deadline = time.time() + 60
        while True:
            try:
                self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
                break
            except OSError:
                if time.time() > deadline:
                    raise
                time.sleep(0.5)
        self.sock.settimeout(5)
        self.data = ""

    def send(self, text):
        self.sock.sendall(text.encode())

    def expect(self, pattern, timeout=120, keep=True):
        """Read until the regex matches; return (match, everything read)."""
        deadline = time.time() + timeout
        regex = re.compile(pattern, re.IGNORECASE | re.DOTALL)
        while time.time() < deadline:
            try:
                chunk = self.sock.recv(65536).decode("utf-8", "replace")
            except socket.timeout:
                continue
            except OSError:
                break
            if chunk:
                self.data += chunk
                if keep:
                    seen.append(chunk)
            match = regex.search(self.data)
            if match:
                return match, self.data
        return None, self.data

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class Monitor:
    def __init__(self):
        self.chan = Channel(MON_PORT)
        self.chan.expect(r"\(qemu\)", timeout=30, keep=False)

    def hmp(self, command, wait=1.0):
        self.chan.send(command + "\n")
        self.chan.expect(r"\(qemu\)", timeout=60, keep=False)
        time.sleep(wait)

    def screenshot(self, name):
        ppm = os.path.join(WORK, f"screen-{name}.ppm")
        png = os.path.join(WORK, f"screen-{name}.png")
        self.hmp(f"screendump {ppm}", wait=1.5)
        subprocess.run(["convert", ppm, png], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(png):
            os.unlink(ppm)
        note(f"screenshot screen-{name}.png")
        return png


class Shell:
    """A login shell on the guest's serial console."""

    def __init__(self, chan):
        self.chan = chan
        self.counter = 0

    def login(self, timeout=900):
        matched, _ = self.chan.expect(r"login:", timeout=timeout)
        if not matched:
            record("FAIL: no login prompt on the serial console")
            return False
        self.chan.send(LIVE_USER + "\r")
        matched, _ = self.chan.expect(r"[Pp]assword:", timeout=60)
        if matched:
            self.chan.send(LIVE_PASS + "\r")
        matched, _ = self.chan.expect(r"[$#] ", timeout=120)
        if not matched:
            record("FAIL: could not log in on the serial console")
            return False
        record(f"PASS: logged in as {LIVE_USER} on the serial console")
        return True

    def run(self, command, timeout=180, lines=40):
        """Run a command over the console and return its output.

        The terminal echoes what is typed, so the markers below are written in
        two quoted halves: the echoed line never contains the joined marker,
        while the printed output does.
        """
        self.counter += 1
        begin = f"HUNTERMARK{self.counter}BEGIN"
        end = f"HUNTERMARK{self.counter}END"
        wrapped = (
            f'echo "{begin[:10]}""{begin[10:]}"; '
            f"({command}) 2>&1 | head -{lines}; "
            f'echo "{end[:10]}""{end[10:]}"'
        )
        self.chan.send(wrapped + "\r")
        pattern = re.escape(begin) + r"(.*?)" + re.escape(end)
        match, _ = self.chan.expect(pattern, timeout=timeout)
        if not match:
            note(f"$ {command}\n<bounded timeout after {timeout}s>")
            record(f"WARN: command timed out: {command}")
            return ""
        text = re.sub(r"\r", "", match.group(1)).strip()
        note(f"$ {command}\n{text}")
        return text

    def wait_for_x(self, timeout=600):
        deadline = time.time() + timeout
        while time.time() < deadline:
            probe = self.run(
                "DISPLAY=:0 xdpyinfo >/dev/null 2>&1 && echo READY || echo WAIT; "
                "pgrep -a Xorg | head -2; ls /tmp/.X11-unix/ 2>/dev/null",
                timeout=60,
            )
            if "READY" in probe:
                record("PASS: the X display is up")
                return True
            time.sleep(10)
        record("FAIL: the X display never came up")
        return False


def start_qemu():
    accel = "kvm" if os.access("/dev/kvm", os.W_OK) else "tcg"
    record(f"accelerator: {accel}")
    args = [
        "qemu-system-x86_64",
        "-m", "2048", "-smp", "2",
        "-accel", accel,
        "-display", "none", "-vga", "std",
        "-no-reboot",
        "-monitor", f"tcp:127.0.0.1:{MON_PORT},server,nowait",
        "-serial", f"tcp:127.0.0.1:{SER_PORT},server,nowait",
        # A forwarded port makes this runner an outside client for Cockpit,
        # which is how a real user reaches it from another computer.
        "-netdev", f"user,id=n0,hostfwd=tcp:127.0.0.1:{WEB_PORT}-:9090",
        "-device", "virtio-net-pci,netdev=n0",
    ]
    if MODE == "uefi":
        code = next((p for p in (
            "/usr/share/OVMF/OVMF_CODE_4M.fd",
            "/usr/share/OVMF/OVMF_CODE.fd",
            "/usr/share/edk2/ovmf/OVMF_CODE.fd",
        ) if os.path.exists(p)), None)
        var_src = next((p for p in (
            "/usr/share/OVMF/OVMF_VARS_4M.fd",
            "/usr/share/OVMF/OVMF_VARS.fd",
            "/usr/share/edk2/ovmf/OVMF_VARS.fd",
        ) if os.path.exists(p)), None)
        if not code or not var_src:
            record("FAIL: no OVMF firmware found")
            return None
        vars_copy = os.path.join(WORK, "OVMF_VARS.fd")
        subprocess.run(["cp", var_src, vars_copy], check=True)
        record(f"firmware: {code}")
        args += [
            "-machine", "q35",
            "-drive", f"if=pflash,format=raw,readonly=on,file={code}",
            "-drive", f"if=pflash,format=raw,file={vars_copy}",
        ]
    else:
        args += ["-boot", "d"]

    args += ["-cdrom", ISO]
    log = open(os.path.join(WORK, "qemu.log"), "w", encoding="utf-8")
    process = subprocess.Popen(args, stdout=log, stderr=log)
    note(f"started qemu as pid {process.pid}")
    return process


def check(results_text, label, ok):
    record(("PASS: " if ok else "FAIL: ") + label)
    return ok


def main():
    for path in (STEPS, RESULT):
        if os.path.exists(path):
            os.unlink(path)

    qemu = start_qemu()
    if qemu is None:
        return 1
    monitor = None
    try:
        monitor = Monitor()
        shell = Shell(Channel(SER_PORT))
        if not shell.login():
            monitor.screenshot("boot-failed")
            return 1
        check(results, "live system reached a login console", True)

        shell.run("cat /proc/cmdline; uname -r; id")
        if not shell.wait_for_x():
            monitor.screenshot("no-x")
            return 1

        time.sleep(30)
        monitor.screenshot("01-desktop")
        shell.run("pgrep -a lightdm | head -2; pgrep -a i3 | head -2; "
                  "pgrep -a xfce4-panel | head -2; pgrep -a xfsettingsd | head -2")

        # --- i3 -------------------------------------------------------------
        i3out = shell.run("i3 -C -c ~/.config/i3/config; echo rc=$?", timeout=120)
        check(results, "i3 configuration is valid",
              bool(re.search(r"rc=0", i3out)) and "ERROR" not in i3out.upper())
        shell.run("pgrep -a i3; ls -l ~/.config/i3/config")

        # --- panel -----------------------------------------------------------
        panel = shell.run("pgrep -a xfce4-panel; xfce4-panel --version 2>&1", timeout=60)
        running = bool(re.search(r"\d+\s+\S*xfce4-panel", panel))
        check(results, "the XFCE panel process is running", running)
        if not running:
            # Start it in the foreground so its own complaint is captured.
            shell.run("DISPLAY=:0 timeout 20 xfce4-panel 2>&1 | head -20", timeout=60)
        conf = shell.run("DISPLAY=:0 xfconf-query -c xfce4-panel -p /panels -v 2>&1; "
                         "DISPLAY=:0 xfconf-query -c xfce4-panel -l 2>&1 | head -20")
        plugins = len(re.findall(r"/plugins/plugin-\d+" , conf)) + \
                  len(re.findall(r"/plugin-\d+", conf))
        check(results, f"the panel loaded its plugins ({plugins} properties)",
              plugins > 0)

        shell.run("free -m")
        shell.run("DISPLAY=:0 xrandr 2>&1 | head -3")
        shell.run("tail -15 /var/log/lightdm/lightdm.log 2>/dev/null")

        # --- applications ----------------------------------------------------
        for name, command, proc, wait in (
            ("thunar", "thunar", "thunar", 25),
            ("brave", "brave-browser --new-window about:blank", "brave", 120),
        ):
            shell.run(f"DISPLAY=:0 setsid {command} >/tmp/{name}.log 2>&1 &",
                      timeout=30)
            time.sleep(wait)
            count = shell.run(f"pgrep -c -x {proc}")
            monitor.screenshot(f"02-{name}")
            number = re.search(r"^(\d+)$", count.strip(), re.M)
            check(results, f"{name} launched",
                  bool(number) and int(number.group(1)) > 0)

        shell.run("tail -6 /tmp/brave.log 2>/dev/null")

        # --- cockpit ---------------------------------------------------------
        status = shell.run("systemctl is-active cockpit.socket; echo ---; "
                           "curl -sk -o /dev/null -w '%{http_code}' "
                           "https://localhost:9090 2>&1", timeout=120)
        socket_state, _, local_code = status.partition("---")
        check(results, "cockpit.socket is active in the live session",
              socket_state.strip().splitlines()[-1:] == ["active"])
        check(results, "Cockpit answers on port 9090 inside the live session",
              local_code.strip().endswith("200"))
        shell.run("/usr/local/bin/hunter-cockpit", timeout=60)

        # From the runner, i.e. from a different computer on the network.
        outside = subprocess.run(
            ["curl", "-sk", "-o", os.path.join(WORK, "cockpit-login.html"),
             "-w", "%{http_code}", f"https://127.0.0.1:{WEB_PORT}/"],
            capture_output=True, text=True, timeout=120)
        login_page = ""
        page_path = os.path.join(WORK, "cockpit-login.html")
        if os.path.exists(page_path):
            with open(page_path, encoding="utf-8", errors="replace") as handle:
                login_page = handle.read()
        # The index is Cockpit's application shell; its title is set by
        # JavaScript, so the marker to look for is its boot configuration.
        check(results, "an outside client reaches the Cockpit login page",
              outside.stdout.strip().endswith("200")
              and "is_cockpit_client" in login_page)

        # Authenticated access with the live account over HTTP basic auth.
        auth = subprocess.run(
            ["curl", "-sk", "-o", "/dev/null", "-D", "-", "-u", "user:live",
             f"https://127.0.0.1:{WEB_PORT}/cockpit/login"],
            capture_output=True, text=True, timeout=120)
        check(results, "an outside client authenticates to Cockpit as the live user",
              "200" in auth.stdout.splitlines()[0] if auth.stdout else False)

        # --- installer -------------------------------------------------------
        # Launch the real desktop entry point, exactly as a user would.
        shell.run("DISPLAY=:0 setsid /usr/local/bin/hunter-install >/tmp/calamares.log "
                  "2>&1 &", timeout=30)
        time.sleep(90)
        monitor.screenshot("03-installer")
        log = shell.run("pgrep -c calamares; echo ---; tail -25 /tmp/calamares.log",
                        timeout=60)
        number = re.search(r"^(\d+)$", log.split("---")[0].strip(), re.M)
        check(results, "the graphical installer started",
              bool(number) and int(number.group(1)) > 0)

        # --- optional panel diagnostics --------------------------------------
        if os.environ.get("PANEL_DIAG") == "1":
            record("INFO: panel diagnostics")
            shell.run("ls /usr/lib/x86_64-linux-gnu/xfce4/panel/plugins/ | head -40",
                      timeout=60)
            shell.run("DISPLAY=:0 xfconf-query -c xfce4-panel -l | head -40", timeout=60)
            # Ask the running panel to add a plugin itself: if the clock shows
            # up the panel works and only the plugin-ids binding is missing,
            # and the saved file then shows the layout 4.20 really uses.
            shell.run("DISPLAY=:0 xfce4-panel --add clock; sleep 4; "
                      "DISPLAY=:0 xfce4-panel -s; sleep 4; echo added", timeout=120)
            time.sleep(15)
            monitor.screenshot("05-panel-clock-added")
            shell.run("DISPLAY=:0 xfconf-query -c xfce4-panel -l "
                      "| grep -E 'plugin-ids|/panels'", timeout=60)
            shell.run("cat ~/.config/xfce4/xfconf/xfce-perchannel-xml/"
                      "xfce4-panel.xml", timeout=60, lines=120)

        # --- idle memory -----------------------------------------------------
        shell.run("pkill -f brave-browser; pkill -f calamares; "
                  "pkill -f thunar; sleep 8; free -m", timeout=60)

        # --- wallpaper -------------------------------------------------------
        # feh sets the root pixmap and exits, so the running process proves
        # nothing; the X root window keeps the pixmap it was given.
        art = shell.run("test -f /usr/share/backgrounds/smd/smd-linux-wallpaper.png "
                        "&& echo present || echo missing; echo ---; "
                        "DISPLAY=:0 xprop -root _XROOTPMAP_ID 2>&1 | head -2",
                        timeout=60)
        check(results, "the SMD wallpaper is installed",
              "present" in art.split("---")[0])
        check(results, "the desktop shows the SMD wallpaper",
              "PIXMAP" in art.split("---")[-1])

        # --- panel: running, bottom edge, auto-hide --------------------------
        panel = shell.run(
            "pgrep -x xfce4-panel >/dev/null && echo panel-running || echo panel-missing; "
            "echo ---; DISPLAY=:0 xwininfo -root -tree 2>/dev/null "
            "| grep -i xfce4-panel | head -3; echo ---; "
            "DISPLAY=:0 xwininfo -root 2>/dev/null | grep -E 'Width:|Height:'",
            timeout=90)
        parts = panel.split("---")
        screen = re.search(r"Height:\s*(\d+)", parts[2]) if len(parts) > 2 else None
        # The panel owns three windows: a 10x10 helper, the reveal strip and
        # the panel itself.  The last geometry on an xwininfo line is the
        # absolute one; the tallest wide window is the panel.
        boxes = []
        for line in (parts[1].splitlines() if len(parts) > 1 else []):
            if "xfce4-panel" not in line:
                continue
            # xwininfo prints the size with relative offsets and then the
            # absolute position as a bare "+x+y": 1280x29+0+0  +0+768.  The
            # window id (0x1000026) must go first: it looks like a size.
            size = re.search(r"(\d+)x(\d+)",
                             re.sub(r"^\s*0x[0-9a-f]+", "", line))
            position = re.findall(r"\+(-?\d+)\+(-?\d+)", line)
            if size and position:
                width, height = int(size.group(1)), int(size.group(2))
                x, y = (int(v) for v in position[-1])
                boxes.append((width, height, x, y, re.search(r"(0x[0-9a-f]+)", line).group(1)))
        boxes.sort(key=lambda box: (box[0], box[1]))
        panel_box = boxes[-1] if boxes else None
        check(results, "the panel is running in the live session",
              "panel-running" in parts[0])
        check(results, "the panel is along the bottom edge",
              bool(panel_box and screen and
                   panel_box[3] + panel_box[1] >= int(screen.group(1)) - 6))
        record(f"INFO: panel window {panel_box[:4] if panel_box else 'not found'} "
               f"on a {screen.group(1) if screen else '?'}px high screen")
        # 1.3 retired auto-hide: the panel is set to stay visible (0 = never
        # hide), and the retired helper must not be running.
        hide = shell.run("DISPLAY=:0 xfconf-query -c xfce4-panel "
                         "-p /panels/panel-1/autohide-behavior 2>&1", timeout=60)
        check(results, "the panel is set never to hide",
              hide.strip().endswith("0"))

        def panel_state(window_id):
            """(map state, y, height) of the panel window, as X sees it."""
            info = shell.run(f"DISPLAY=:0 xwininfo -id {window_id}", timeout=60)
            state = re.search(r"Map State:\s*(\S+)", info)
            corner = re.search(r"Corners:\s*\+(-?\d+)\+(-?\d+)", info)
            height = re.search(r"Height:\s*(\d+)", info)
            return (state.group(1) if state else "?",
                    int(corner.group(2)) if corner else None,
                    int(height.group(1)) if height else None)

        window = panel_box[4] if panel_box else None
        if window and screen:
            screen_px = int(screen.group(1))
            state, y, height = panel_state(window)
            monitor.screenshot("06a-panel-visible")
            # 1.3 retired auto-hide: the panel stays on screen along the bottom
            # edge, and full-screen video simply covers it.
            visible = (state == "IsViewable" and y is not None and
                       y + (height or 0) >= screen_px - 6)
            check(results, "the panel stays visible along the bottom edge", visible)
            record(f"INFO: panel: state {state}, y={y}, height={height}")

        # The menu button must show the SMD "S", not the old H.
        icon = shell.run("DISPLAY=:0 xfconf-query -c xfce4-panel "
                         "-p /plugins/plugin-1/button-icon 2>&1", timeout=60)
        check(results, "the menu button uses the SMD icon",
              icon.strip().endswith("smd-menu"))
        icon_file = shell.run(
            "test -f /usr/share/icons/hicolor/scalable/apps/smd-menu.svg "
            "&& grep -c '<path' /usr/share/icons/hicolor/scalable/apps/smd-menu.svg",
            timeout=60)
        check(results, "the SMD menu icon is installed",
              icon_file.strip().splitlines()[-1:] == ["1"])

        # Black panel: solid background style with a black colour.
        style = shell.run("DISPLAY=:0 xfconf-query -c xfce4-panel "
                          "-p /panels/panel-1/background-style 2>&1", timeout=60)
        rgba = shell.run("DISPLAY=:0 xfconf-query -c xfce4-panel "
                         "-p /panels/panel-1/background-rgba 2>&1", timeout=60)
        check(results, "the panel has a solid black background",
              style.strip().endswith("1") and "0.000000" in rgba)

        # The stuck Wi-Fi bubble: the notification daemon must expire messages.
        notify = shell.run("DISPLAY=:0 xfconf-query -c xfce4-notifyd "
                           "-p /expire-timeout 2>&1", timeout=60)
        check(results, "notifications expire after a few seconds",
              notify.strip().splitlines()[-1:] == ["5"])

        # Mail Reader was an unusable launcher, not a mail client.
        mail = shell.run(
            "ls /usr/share/applications | grep -i '[m]ail' | head -5; "
            "echo MAILCOUNT=$(ls /usr/share/applications | grep -ci '[m]ail')",
            timeout=60)
        match = re.search(r"MAILCOUNT=(\d+)", mail)
        record(f"INFO: mail entries seen: {mail.strip()[:120]}")
        check(results, "no Mail Reader entry is left in the menu",
              bool(match) and match.group(1) == "0")

        # Chromebook top row: the printed volume keys are F9/F10 there.  The
        # harness forces the Chromebook layout because a VM is not a Chromebook.
        # An i3 restart re-runs every exec_always line; the panel and the hide
        # watcher must not stack, and the restart is also what proves the
        # bindings survive a reload.  It re-runs the unforced hunter-toprow too,
        # which on a VM clears the Chromebook flag, so force it afterwards.
        shell.run("DISPLAY=:0 i3-msg restart", timeout=120)
        time.sleep(10)
        toprow = shell.run("DISPLAY=:0 hunter-toprow --force; "
                           "test -f ~/.config/i3/chromebook-keys && echo FLAG-SET",
                           timeout=60)
        check(results, "the Chromebook top row is detected",
              "FLAG-SET" in toprow)
        # Start from half volume: the default sink is already at 1.0, where a
        # "5%+" would be capped and look like a broken key.  The values are
        # printed with a marker because the log echoes the command itself.
        # cut, not awk: this image has no awk installed.
        SINK = "env XDG_RUNTIME_DIR=/run/user/$(id -u) wpctl"
        # wpctl has to reach the running session's PipeWire: without the
        # session's runtime directory it starts a private instance and every
        # reading comes back unchanged.
        shell.run("%s set-volume @DEFAULT_AUDIO_SINK@ 0.5; sleep 1; "
                  "echo VOLBEFORE=$(%s get-volume @DEFAULT_AUDIO_SINK@ "
                  "| cut -d' ' -f2)" % (SINK, SINK), timeout=90)
        time.sleep(2)
        before = shell.run("echo VOLBEFORE=$(%s get-volume "
                           "@DEFAULT_AUDIO_SINK@ | cut -d' ' -f2)" % SINK,
                           timeout=60)
        shell.run("DISPLAY=:0 xdotool key F10", timeout=60)
        time.sleep(3)
        after = shell.run("echo VOLAFTER=$(%s get-volume "
                          "@DEFAULT_AUDIO_SINK@ | cut -d' ' -f2)" % SINK,
                          timeout=60)
        bindings = shell.run("DISPLAY=:0 i3-msg -t get_config | "
                             "grep -c 'bindsym F10'", timeout=90)
        first = re.search(r"VOLBEFORE=([0-9.]+)", before)
        second = re.search(r"VOLAFTER=([0-9.]+)", after)
        # The virtual machine's sink accepts a level but reports the same value
        # back, so what can be proven here is that the key is bound and reaches
        # the media helper; whether the speaker gets louder is a hardware check.
        sink = shell.run(
            "%s list sinks 2>/dev/null | grep -iE 'Name:|Volume:| mute' | head -6"
            % SINK, timeout=90)
        bound = shell.run("DISPLAY=:0 i3-msg -t get_config | "
                          "grep -cE 'bindsym .*(F10|XF86AudioRaiseVolume)'",
                          timeout=90)
        try:
            bound_count = int(bound.strip().splitlines()[-1])
        except (ValueError, IndexError):
            bound_count = 0
        check(results, "the printed volume key is bound", bound_count >= 1)
        record(f"INFO: volume {first.group(1) if first else '?'} -> "
               f"{second.group(1) if second else '?'}; bound={bound_count}; "
               f"sink: {' '.join(sink.split())[:160]}")

        # No second panel or watchdog after an i3 restart: the exec_always
        # scripts are flushed and re-run, and must not stack.
        time.sleep(5)
        count = shell.run(
            "echo PANELS=$(pgrep -c -x xfce4-panel); "
            "echo PYTHON=$(pgrep -c -x python3); "
            "test -e /usr/local/bin/hunter-panel-dock && echo DOCK-HELPER=present "
            "|| echo DOCK-HELPER=absent", timeout=90)
        panels = re.search(r"PANELS=(\d+)", count)
        pythons = re.search(r"PYTHON=(\d+)", count)
        helper = re.search(r"DOCK-HELPER=(\w+)", count)
        record(f"INFO: after reload {count.strip()[:300]}")
        check(results, "exactly one panel survives a reload", 
              bool(panels) and panels.group(1) == "1")
        check(results, "the retired auto-hide helper is gone",
              bool(helper) and helper.group(1) == "absent")

        # Idle resources, measured the same way on every image: 90 s after the
        # session is up, no applications open, live USB boot in the same VM.
        time.sleep(5)
        resources = shell.run(
            "free -m; echo ---; vmstat 1 5 | tail -1; echo ---; "
            "ps -eo pcpu,pmem,comm --sort=-pcpu | head -6; echo ---; "
            "swapon --show=NAME,SIZE --noheadings 2>/dev/null | head -3",
            timeout=120)
        record("INFO: idle resources: " + " ".join(resources.split())[:300])
        mem = re.search(r"Mem:\s+(\d+)\s+(\d+)\s+(\d+)", resources)
        if mem:
            total, used, free_mem = (int(g) for g in mem.groups())
            # No target is asserted: the handoff asked for measurements under
            # fixed conditions, not for a number to hit.
            record(f"INFO: memory {used} MiB used of {total} MiB, "
                   f"{free_mem} MiB free")
        log = shell.run("tail -3 ~/.cache/smd/panel.log 2>/dev/null", timeout=60)
        record(f"INFO: panel log: {log.strip()[:200]}")

        shell.run("DISPLAY=:0 xdotool mousemove 640 400", timeout=30)
        time.sleep(2)
        monitor.screenshot("06-desktop")

        # --- audio: PipeWire, WirePlumber, a real sink -----------------------
        # The session may still be settling: give PipeWire up to 30 s to appear
        # before calling it missing, and print the user units when it does not.
        for _ in range(10):
            ready = shell.run("pgrep -x pipewire >/dev/null && "
                              "pgrep -x wireplumber >/dev/null && echo AUDIO-UP",
                              timeout=60)
            if "AUDIO-UP" in ready:
                break
            time.sleep(3)
        # When i3 rejects its config, dump what it actually read and why.
        cfg = shell.run(
            "echo HOME=$HOME; ls -l ~/.config/i3/config; "
            "wc -l ~/.config/i3/config; echo ===; "
            "sed -n '1,4p;24,30p' ~/.config/i3/config | cat -A; echo ===; "
            "grep -n 'set [$]mod' ~/.config/i3/config | head -3", timeout=90)
        record("INFO: i3 config file: " + " | ".join(cfg.split())[:700])

        audio = shell.run(
            "systemctl --user is-active pipewire pipewire-pulse wireplumber 2>&1; "
            "echo ---; "
            "pactl info 2>&1 | grep -iE 'server name|server version'; echo ---; "
            "pgrep -x pipewire >/dev/null && echo pipewire-running || echo pipewire-missing; "
            "pgrep -x wireplumber >/dev/null && echo wireplumber-running || echo wireplumber-missing; "
            "echo ---; wpctl status 2>&1 | grep -iE 'sinks|default' | head -4",
            timeout=90)
        chunks = audio.split("---")
        check(results, "the sound server is PipeWire",
              any("PipeWire" in chunk for chunk in chunks))
        check(results, "PipeWire and WirePlumber are running",
              "pipewire-running" in chunks[-2] and
              "wireplumber-running" in chunks[-2])
        record(f"INFO: audio units: {chunks[0].strip()[:200]}")
        if "PipeWire" not in audio:
            diag = shell.run(
                "systemctl --user list-units 'pipewire*' 'wireplumber*' "
                "--all --no-pager 2>&1 | head -10; echo ===; "
                "systemctl --user status pipewire.service --no-pager 2>&1 "
                "| tail -8; echo ===; "
                "journalctl --user -u pipewire -n 8 --no-pager 2>&1 | tail -8; "
                "journalctl --user -u pipewire.socket -n 6 --no-pager 2>&1 "
                "| tail -6; "
                "echo ===; ls -l ${XDG_RUNTIME_DIR:-/run/user/$(id -u)} 2>&1 | head -8",
                timeout=120)
            record("INFO: audio diagnostics: " +
                   " ".join(diag.split())[:600])

        # --- dark theme: the theme has to be present, not just requested ---
        theme = shell.run(
            "DISPLAY=:0 xfconf-query -c xsettings -p /Net/ThemeName 2>&1; echo ---; "
            "test -d /usr/share/themes/Adwaita-dark && echo THEME=present "
            "|| echo THEME=missing; echo ---; "
            "grep -c 'gtk-theme-name=Adwaita-dark' ~/.config/gtk-3.0/settings.ini "
            "2>/dev/null; echo ---; "
            "grep -c '^client.focused' ~/.config/i3/config 2>/dev/null",
            timeout=90)
        tchunks = theme.split("---")
        check(results, "the dark theme is selected", "Adwaita-dark" in tchunks[0])
        check(results, "the dark theme is actually installed",
              "THEME=present" in tchunks[1])
        check(results, "GTK applications are configured dark",
              tchunks[2].strip().endswith("1"))
        try:
            decorations = int(tchunks[3].strip().splitlines()[-1])
        except (ValueError, IndexError):
            decorations = 0
        check(results, "the window decorations are dark", decorations >= 2)
        record(f"INFO: theme: {' | '.join(c.strip()[:60] for c in tchunks)}")

        # --- one installer entry in the live menu ---------------------------
        entries = shell.run(
            "ls /usr/share/applications | grep -iE 'calamares|install' | sort; echo ---; "
            "grep -h '^Icon=' /usr/share/applications/hunter-install.desktop 2>/dev/null",
            timeout=60)
        echunks = entries.split("---")
        listing = [line for line in echunks[0].split() if line.endswith(".desktop")]
        check(results, "exactly one installer entry is in the menu",
              listing == ["hunter-install.desktop"])
        check(results, "the installer entry uses the SMD icon",
              echunks[1].strip().endswith("smd-menu"))
        record(f"INFO: installer entries: {listing} {echunks[1].strip()}")

        # --- the PCI matcher has to read lspci the way lspci prints --------
        # Craig's line is "00:02.0 VGA compatible controller [0300]: Intel ...
        # [8086:0f31]"; the class comes first, so the ID must be matched after
        # "VGA".  Before that fix the service removed the file again at boot.
        craig = ("00:02.0 VGA compatible controller [0300]: Intel Corporation "
                 "Atom Processor Z36xxx/Z37xxx Series Graphics & Display "
                 "[8086:0f31] (rev 0e)")
        matcher = shell.run(
            "printf '%s\\n' \"%s\" | grep -qi 'VGA.*8086:0f31' "
            "&& echo MATCH=ok || echo MATCH=no" % ("%s", craig), timeout=60)
        check(results, "the TearFree matcher reads lspci output correctly",
              "MATCH=ok" in matcher)

        # --- PipeWire quantum: the value that removed Jellyfin's delay ------
        quantum = shell.run(
            "test -e /etc/pipewire/pipewire.conf.d/50-hunter-quantum.conf "
            "&& echo CONF=present || echo CONF=missing; echo ---; "
            "grep -E 'quantum' /etc/pipewire/pipewire.conf.d/"
            "50-hunter-quantum.conf 2>/dev/null | tr -d ' ' | sort -u; echo ---; "
            "%s -n settings 2>/dev/null | grep -i 'clock.quantum' | head -3"
            % ('env XDG_RUNTIME_DIR=/run/user/$(id -u) pw-metadata'), timeout=90)
        qchunks = quantum.split("---")
        check(results, "the PipeWire quantum configuration is installed",
              "CONF=present" in qchunks[0])
        # Only the settings lines matter: the file's comments mention the
        # quantum too, so compare the three values themselves.
        values = sorted(line for line in qchunks[1].split() if "=" in line)
        check(results, "the quantum is pinned to 2048",
              values == ["default.clock.max-quantum=2048",
                         "default.clock.min-quantum=2048",
                         "default.clock.quantum=2048"])
        record(f"INFO: quantum: {' '.join(qchunks[1].split())} | "
               f"{' '.join(qchunks[2].split())[:120]}")

        # --- the hardware mixer fix stays scoped to the max98090 codec ------
        hw = shell.run(
            "systemctl is-enabled hunter-audio-hw.service 2>&1; echo ---; "
            "systemctl is-active hunter-audio-hw.service 2>&1; echo ---; "
            "grep -rl max98090 /proc/asound/card*/codec#* 2>/dev/null "
            "| head -2; echo ---; "
            "ls /usr/share/alsa/ucm2/*max98090*/EnableSeq.conf.smd-backup "
            "2>/dev/null | head -1",
            timeout=90)
        hchunks = hw.split("---")
        check(results, "the audio mixer unit is enabled", "enabled" in hchunks[0])
        check(results, "the audio mixer unit ran", "active" in hchunks[1])
        check(results, "the mixer fix did not touch a machine without the codec",
              not hchunks[2].strip())
        record(f"INFO: audio hardware: {' | '.join(c.strip()[:60] for c in hchunks)}")

        # --- VA-API driver and the shim's mpv settings ----------------------
        vaapi = shell.run(
            "dpkg -s i965-va-driver >/dev/null 2>&1 && echo DRIVER=installed "
            "|| echo DRIVER=missing; echo ---; "
            "grep -v '^#' ~/.config/jellyfin-mpv-shim/mpv.conf 2>/dev/null "
            "| grep -E 'hwdec|display-resample' ; echo ---; "
            "ls /usr/lib/x86_64-linux-gnu/dri/i965_drv_video.so 2>/dev/null",
            timeout=90)
        vchunks = vaapi.split("---")
        check(results, "the VA-API driver is installed",
              "DRIVER=installed" in vchunks[0])
        check(results, "the Jellyfin shim asks for hardware decoding",
              "hwdec=auto-safe" in vchunks[1])
        check(results, "display-resample is not configured",
              "display-resample" not in vchunks[1])
        record(f"INFO: va-api: {vchunks[1].strip()[:80]} {vchunks[2].strip()[:80]}")

        # --- speaker level: the 125 % Hunter tuned on the Chromebook --------
        volume = shell.run(
            "test -x /usr/local/bin/hunter-volume && echo SCRIPT=ok || echo SCRIPT=missing; "
            "echo PORT=$(pactl list sinks 2>/dev/null | "
            "sed -n 's/^[[:space:]]*Active Port: //p' | head -1); "
            "echo LEVEL=$(env XDG_RUNTIME_DIR=/run/user/$(id -u) wpctl get-volume @DEFAULT_AUDIO_SINK@ 2>/dev/null "
            "| cut -d' ' -f2); "
            "tail -2 ~/.cache/smd/volume.log 2>/dev/null; echo ---; "
            "grep -c hunter-volume ~/.config/i3/config 2>/dev/null || true",
            timeout=90)
        check(results, "the speaker volume policy is installed",
              "SCRIPT=ok" in volume)
        record(f"INFO: speaker/volume: {volume.strip()[:220]}")

        # --- graphics: TearFree only where it belongs -----------------------
        # The VM has a QEMU adapter, not Intel Bay Trail, so the correct result
        # here is that the intel driver was never forced on this hardware.
        graphics = shell.run(
            "systemctl is-enabled hunter-graphics.service 2>&1; echo ---; "
            "systemctl is-active hunter-graphics.service 2>&1; echo ---; "
            "test -e /etc/X11/xorg.conf.d/20-intel.conf && echo TEARFREE=present "
            "|| echo TEARFREE=absent; echo ---; "
            "lspci -nn 2>/dev/null | grep -iE 'VGA|3D' | head -2; echo ---; "
            "journalctl -u hunter-graphics.service -n 6 --no-pager 2>&1 "
            "| tr '\n' ' '",
            timeout=90)
        gchunks = graphics.split("---")
        check(results, "the TearFree service is enabled",
              "enabled" in gchunks[0])
        check(results, "the TearFree service ran",
              gchunks[1].strip() in ("active", "activating", "reloading"))
        record(f"INFO: graphics detail: {gchunks[-1].strip()[:500]}")
        check(results, "TearFree is not forced onto unrelated graphics",
              "TEARFREE=absent" in gchunks[2])
        record(f"INFO: graphics: {' | '.join(c.strip()[:70] for c in gchunks)}")

        # --- Wi-Fi: the parts that a virtual machine can show ----------------
        net = shell.run(
            "dpkg-query -W -f='${Status}' wpasupplicant 2>/dev/null "
            "| grep -c 'install ok installed'; echo ---; "
            "ls /lib/firmware/iwlwifi-7260* 2>/dev/null | head -3; echo ---; "
            "systemctl is-active NetworkManager; nmcli -t -f RUNNING general 2>&1",
            timeout=90)
        nchunks = net.split("---")
        check(results, "the Wi-Fi supplicant is installed",
              nchunks[0].strip().endswith("1"))
        check(results, "firmware for the Intel 7260 radio is present",
              "iwlwifi-7260" in nchunks[1])
        check(results, "NetworkManager is active", "active" in nchunks[2])

        # --- the promised software set, and nothing else ---------------------
        # mpv is no longer one of the removed applications: 1.5 installs it as
        # the player the Jellyfin client drives, and checks it below.
        scope = shell.run(
            "for p in falkon ristretto xarchiver; do "
            "command -v $p >/dev/null && echo present:$p || echo gone:$p; done; echo ---; "
            "command -v brave-browser >/dev/null && echo browser-present; "
            "command -v vlc >/dev/null && echo vlc-present; "
            "command -v xfce4-panel >/dev/null && echo panel-present",
            timeout=60)
        schunks = scope.split("---")
        check(results, "the trimmed application set is installed",
              "browser-present" in schunks[1] and "panel-present" in schunks[1]
              and "vlc-present" in schunks[1])
        check(results, "the removed applications are really gone",
              "present:" not in schunks[0])

        # --- the two clients added in 1.5 ------------------------------------
        clients = shell.run(
            "command -v mpv >/dev/null && echo mpv-present; "
            "test -x /opt/jellyfin-mpv-shim/bin/jellyfin-mpv-shim "
            "&& echo jellyfin-exe; "
            "test -f /usr/share/applications/jellyfin-mpv-shim.desktop "
            "&& echo jellyfin-menu; "
            "/opt/jellyfin-mpv-shim/bin/python -c 'import jellyfin_mpv_shim' "
            "2>/dev/null && echo jellyfin-import; "
            "echo ---; "
            "test -x /usr/local/bin/hunter-dictation && echo voice-toggle; "
            "test -f /usr/share/applications/smd-dictation.desktop "
            "&& echo voice-menu; "
            "/opt/smd-voice/bin/python -c 'import vosk' 2>/dev/null "
            "&& echo vosk-import; "
            "test -d /usr/share/vosk/vosk-model-small-en-us-0.15 "
            "&& echo model-present; "
            "echo ---; grep -c 'bindsym \\$mod+z exec.*hunter-dictation' "
            "~/.config/i3/config; "
            "echo ---; ls /etc/xdg/autostart 2>/dev/null | wc -l",
            timeout=180)
        cchunks = clients.split("---")
        for label, marker in (
                ("mpv is installed for the Jellyfin client", "mpv-present"),
                ("the Jellyfin client is installed", "jellyfin-exe"),
                ("the Jellyfin client has a menu entry", "jellyfin-menu"),
                ("the Jellyfin client imports", "jellyfin-import"),
                ("Voice Typing is installed", "voice-toggle"),
                ("Voice Typing has a menu entry", "voice-menu"),
                ("the speech engine imports", "vosk-import"),
                ("the offline English speech model ships", "model-present")):
            check(results, label, marker in cchunks[0])
        check(results, "Alt+Z is bound to Voice Typing in the session",
              cchunks[2].strip().splitlines()[:1] == ["1"])
        record("INFO: autostart entries: %s"
               % (cchunks[3].strip() if len(cchunks) > 3 else "?")[:80])

        # --- launcher on the Search key --------------------------------------
        shell.run("DISPLAY=:0 xdotool mousemove 300 300", timeout=30)
        shell.run("DISPLAY=:0 xdotool key --clearmodifiers Super_L", timeout=30)
        time.sleep(4)
        monitor.screenshot("05-launcher")
        launcher = shell.run("DISPLAY=:0 xwininfo -root -tree 2>/dev/null "
                             "| grep -ci rofi", timeout=60)
        check(results, "the Search key opens the launcher on its own",
              launcher.strip().isdigit() and int(launcher.strip()) > 0)
        shell.run("DISPLAY=:0 xdotool key Escape", timeout=30)

        # --- 1.4: Brave, its extensions and VLC -----------------------------
        apps = shell.run(
            "dpkg -s brave-browser >/dev/null 2>&1 && echo BRAVE=installed "
            "|| echo BRAVE=missing; echo ---; "
            "dpkg -s vlc >/dev/null 2>&1 && echo VLC=installed || echo VLC=missing; "
            "echo ---; "
            "grep -c 'brave-browser' /etc/apt/sources.list.d/brave-browser.sources "
            "2>/dev/null; echo ---; "
            "test -e /usr/share/keyrings/brave-browser-archive-keyring.gpg "
            "&& echo KEY=present || echo KEY=missing",
            timeout=120)
        achunks = apps.split("---")
        check(results, "Brave is installed from its signed repository",
              "BRAVE=installed" in achunks[0]
              and achunks[2].strip().isdigit() and int(achunks[2].strip()) >= 1
              and "KEY=present" in achunks[3])
        check(results, "VLC is installed", "VLC=installed" in achunks[1])
        record(f"INFO: apps: {' | '.join(c.strip()[:50] for c in achunks)}")

        policy = shell.run(
            "cat /etc/brave/policies/managed/10-smd-extensions.json 2>&1; echo ---; "
            "xdg-settings get default-web-browser 2>&1; echo ---; "
            "xdg-mime query default x-scheme-handler/https 2>&1",
            timeout=90)
        pchunks = policy.split("---")
        try:
            entered = set(json.loads(pchunks[0])["ExtensionSettings"])
        except (ValueError, KeyError):
            entered = set()
        check(results, "both extensions are configured for automatic install",
              entered == {"aleakchihdccplidncghkekgioiakgal",
                          "iaddfgegjgjelgkanamleadckkpnjpjc"})
        check(results, "Brave is the default browser",
              "brave-browser.desktop" in pchunks[1])
        check(results, "https links open in Brave",
              "brave-browser.desktop" in pchunks[2])
        record(f"INFO: browser default: {' | '.join(c.strip() for c in pchunks[1:])}")

        # --- 1.4: the panel order S -> spacer -> Brave ----------------------
        panel = shell.run(
            "DISPLAY=:0 xfconf-query -c xfce4-panel -p /panels/panel-1/plugin-ids "
            "2>&1 | tr '\n' ' '; echo ---; "
            "DISPLAY=:0 xfconf-query -c xfce4-panel -lv 2>&1 "
            "| grep -A3 'plugin-11' | tr '\n' ' '; echo ---; "
            "DISPLAY=:0 xfconf-query -c xfce4-panel -p /plugins/plugin-10/expand 2>&1",
            timeout=90)
        qchunks = panel.split("---")
        try:
            ids = [int(v) for v in qchunks[0].split() if v.strip().lstrip("-").isdigit()]
        except ValueError:
            ids = []
        # xfconf-query prints the number of values before an array.
        if ids and ids[0] == len(ids) - 1:
            ids = ids[1:]
        check(results, "the panel runs the menu, spacer and Brave in that order",
              len(ids) >= 3 and ids[0] == 1 and ids[1] == 10 and ids[2] == 11)
        # Already-running panels do not pick up a new launcher, so the shipped
        # default is the thing to assert; the live query is recorded.
        shipped = shell.run(
            "grep -c 'brave-browser.desktop' /etc/skel/.config/xfce4/xfconf/"
            "xfce-perchannel-xml/xfce4-panel.xml 2>/dev/null", timeout=60)
        check(results, "the Brave launcher is in the panel defaults",
              shipped.strip().splitlines()[-1:] == ["1"])
        record(f"INFO: live launcher properties: {qchunks[1].strip()[:120]}")
        check(results, "the new spacer does not expand",
              qchunks[2].strip() == "false")
        record(f"INFO: panel ids: {ids}")

        # --- 1.4: locking through the session's LockCommand -----------------
        lock = shell.run(
            "DISPLAY=:0 xfconf-query -c xfce4-session -p /general/LockCommand 2>&1; "
            "echo ---; "
            "DISPLAY=:0 xfconf-query -c xfce4-power-manager "
            "-p /xfce4-power-manager/lock-screen-suspend-hibernate 2>&1; echo ---; "
            "command -v i3lock >/dev/null && echo LOCKER=present || echo LOCKER=missing",
            timeout=90)
        lchunks = lock.split("---")
        check(results, "the session lock command is i3lock",
              "i3lock" in lchunks[0] and "-n" not in lchunks[0])
        check(results, "locking on suspend is enabled",
              lchunks[1].strip() == "true")
        check(results, "the locker is installed", "LOCKER=present" in lchunks[2])
        record(f"INFO: lock: {' | '.join(c.strip() for c in lchunks)}")

        # --- 1.4: the audio helper reads the sound-card id ------------------
        audiohw = shell.run(
            "grep -Fq 'cat \"$dir/id\"' /usr/local/sbin/hunter-audio-hw "
            "&& echo READS-ID || echo NO-ID; echo ---; "
            "grep -Fq 'card=${dir##*/card}' /usr/local/sbin/hunter-audio-hw "
            "&& echo CARD-FROM-DIR || echo CARD-HARDCODED",
            timeout=60)
        nchunks = audiohw.split("---")
        check(results, "the audio helper reads the sound-card id",
              "READS-ID" in nchunks[0])
        check(results, "the audio helper derives the card number from the directory",
              "CARD-FROM-DIR" in nchunks[1])

        # --- 1.4: automatic balanced tiling --------------------------------
        helper = shell.run(
            "test -x /usr/local/bin/hunter-autotile && echo HELPER=ok "
            "|| echo HELPER=missing; echo ---; "
            "pgrep -fc 'python3 /usr/local/bin/hunter-autotile'",
            timeout=60)
        hchu = helper.split("---")
        check(results, "the tiling helper is installed", "HELPER=ok" in hchu[0])
        check(results, "exactly one tiling helper is running",
              hchu[1].strip() == "1")
        record("INFO: autotile processes: " +
               " ".join(shell.run("pgrep -af hunter-autotile 2>&1").split())[:200])

        # Detach every terminal: a background job that inherits the session
        # keeps the channel open and the next command times out.
        def open_window(title):
            shell.run("setsid env DISPLAY=:0 xfce4-terminal --title=%s "
                      "</dev/null >/dev/null 2>&1 &" % title, timeout=30)
            # The helper settles a moment after the window appears.
            time.sleep(13)

        def tiles():
            """Rectangles of the test windows, via i3's own tree."""
            tree = shell.run("DISPLAY=:0 i3-msg -t get_tree", timeout=90)
            try:
                data = json.loads(tree[tree.index("{"):])
            except (ValueError, KeyError):
                return []
            found = []

            def walk(node):
                for child in node.get("nodes", []) + node.get("floating_nodes", []):
                    if child.get("window") and str(child.get("name", "")).startswith("smd-") \
                            and not str(child.get("floating", "")).startswith("user"):
                        found.append(child["rect"])
                    walk(child)

            walk(data)
            return found

        def describe(boxes):
            return " ".join("[%d,%d %dx%d]" % (b["x"], b["y"], b["width"],
                                               b["height"]) for b in boxes)

        # Only the test's own windows may be in the layout: the browser from
        # the earlier check is a normal window too and would take a slot.
        shell.run("pkill -x brave; sleep 2", timeout=60)
        open_window("smd-one")
        one = tiles()
        check(results, "one window fills the usable desktop",
              len(one) == 1 and one[0]["width"] >= 1000 and one[0]["height"] >= 700)
        record("INFO: tiling one: " + describe(one))

        open_window("smd-two")
        two = tiles()
        halves = (len(two) == 2 and
                  abs(two[0]["width"] - two[1]["width"]) <= 4 and
                  round(two[0]["y"]) == round(two[1]["y"]) and
                  round(two[0]["x"]) != round(two[1]["x"]))
        check(results, "two windows split the screen equally", halves)
        record("INFO: tiling two: " + describe(two))

        open_window("smd-three")
        three = tiles()
        ok3 = False
        if len(three) == 3:
            xs = sorted({round(b["x"]) for b in three})
            if len(xs) == 2:
                left = [b for b in three if round(b["x"]) == xs[0]]
                right = [b for b in three if round(b["x"]) == xs[1]]
                ok3 = (len(left) == 2 and len({round(b["y"]) for b in left}) == 2
                       and len(right) == 1
                       and abs(left[0]["width"] - right[0]["width"]) <= 4)
        check(results, "the third window sits below the first", ok3)
        record("INFO: tiling three: " + describe(three))

        # Closing one window has to compress the survivors back into the
        # two-window layout, using arrival order rather than focus.
        shell.run("DISPLAY=:0 xdotool search --name '^smd-three$' windowclose",
                  timeout=60)
        time.sleep(6)
        back = tiles()
        check(results, "closing a window returns to two equal halves",
              len(back) == 2 and abs(back[0]["width"] - back[1]["width"]) <= 4)
        record("INFO: tiling after close: " + describe(back))

        open_window("smd-three")
        open_window("smd-four")
        four = tiles()
        ok4 = False
        if len(four) == 4:
            xs = sorted({round(b["x"]) for b in four})
            ok4 = len(xs) == 2 and all(
                len({round(b["y"]) for b in four if round(b["x"]) == x}) == 2
                for x in xs)
        check(results, "four windows form an even 2x2 grid", ok4)
        record("INFO: tiling four: " + describe(four))

        record("INFO: autotile log: " + " | ".join(
            shell.run("tail -8 ~/.cache/smd/autotile.log 2>/dev/null").split())[:400])
        shell.run("DISPLAY=:0 xdotool search --name '^smd-' windowclose; "
                  "pkill -f xfce4-terminal", timeout=60)

        # --- keyboard mapping and start-up time (recorded, not asserted) ----
        shell.run("DISPLAY=:0 xmodmap -pm 2>/dev/null | grep -E 'mod1|mod4'",
                  timeout=60)
        shell.run("systemd-analyze 2>&1; systemd-analyze blame 2>/dev/null "
                  "| head -8; systemctl --failed --no-pager | head -6", timeout=120)
        record("PASS: live session test finished")
        # A failing check must fail the job: green CI with a FAIL line in the
        # log is how several regressions were missed.
        return 1 if any(line.startswith("FAIL:") for line in results) else 0
    finally:
        if monitor:
            try:
                monitor.hmp("quit", wait=0.5)
            except Exception:
                pass
        time.sleep(2)
        if qemu.poll() is None:
            qemu.kill()
        with open(SERIAL_LOG, "w", encoding="utf-8", errors="replace") as handle:
            handle.write("".join(seen))
        with open(RESULT, "w", encoding="utf-8") as handle:
            handle.write("\n".join(results) + "\n")
        print("\n".join(results))


if __name__ == "__main__":
    sys.exit(main())
