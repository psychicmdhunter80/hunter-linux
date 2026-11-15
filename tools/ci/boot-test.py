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
            ("firefox", "firefox-esr 'about:blank'", "firefox", 90),
        ):
            shell.run(f"DISPLAY=:0 setsid {command} >/tmp/{name}.log 2>&1 &",
                      timeout=30)
            time.sleep(wait)
            count = shell.run(f"pgrep -c -f '^[a-z]*{proc}'")
            monitor.screenshot(f"02-{name}")
            number = re.search(r"^(\d+)$", count.strip(), re.M)
            check(results, f"{name} launched",
                  bool(number) and int(number.group(1)) > 0)

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
        shell.run("pkill -f firefox-esr; pkill -f falkon; pkill -f calamares; "
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
        # Auto-hide is proven by what the running panel itself reports and by
        # the strip it leaves at the screen edge: the strip window (a few pixels
        # tall, full width, at the bottom) only exists while auto-hide is on.
        hide = shell.run("DISPLAY=:0 xfconf-query -c xfce4-panel "
                         "-p /panels/panel-1/autohide-behavior 2>&1", timeout=60)
        check(results, "the panel is configured to auto-hide",
              hide.strip().endswith("2"))
        edge_strip = bool(screen and any(
            box[0] > 500 and box[1] <= 6 and box[3] >= int(screen.group(1)) - 6
            for box in boxes))
        check(results, "the panel leaves a reveal strip along the bottom edge",
              edge_strip)

        window = panel_box[4] if panel_box else None
        if window and screen:
            edge = int(screen.group(1)) - 2
            # Away from the bottom edge: the panel must actually disappear.
            shell.run("DISPLAY=:0 xdotool mousemove 300 300", timeout=30)
            time.sleep(4)
            away = shell.run(f"DISPLAY=:0 xwininfo -id {window} "
                             "| grep 'Map State'", timeout=60)
            monitor.screenshot("06a-panel-hidden")
            check(results, "the panel hides when the pointer leaves the edge",
                  "IsUnMapped" in away)
            # Back to the bottom edge: it must come back.
            shell.run(f"DISPLAY=:0 xdotool mousemove --sync 640 {edge}", timeout=30)
            time.sleep(4)
            near = shell.run(f"DISPLAY=:0 xwininfo -id {window} "
                             "| grep 'Map State'", timeout=60)
            monitor.screenshot("06b-panel-revealed")
            check(results, "the panel comes back at the bottom edge",
                  "IsViewable" in near)
            record(f"INFO: pointer away: {away.strip()[:50]}; "
                   f"at the edge: {near.strip()[:50]}")

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
        # A restart re-runs the unforced hunter-toprow, which on a VM writes the
        # no-Chromebook file; force it again and reload so i3 re-reads the
        # include without re-running the exec lines.
        shell.run("DISPLAY=:0 i3-msg restart", timeout=120)
        time.sleep(8)
        shell.run("DISPLAY=:0 hunter-toprow --force; DISPLAY=:0 i3-msg reload",
                  timeout=120)
        time.sleep(5)
        toprow = shell.run("grep -c 'bindsym F10' ~/.config/i3/toprow.conf 2>&1",
                           timeout=60)
        check(results, "the Chromebook top row bindings are generated",
              toprow.strip().splitlines()[-1:] == ["1"])
        # Start from half volume: the default sink is already at 1.0, where a
        # "5%+" would be capped and look like a broken key.  The values are
        # printed with a marker because the log echoes the command itself.
        shell.run("wpctl set-volume @DEFAULT_AUDIO_SINK@ 0.5; sleep 1; "
                  "echo VOLBEFORE=$(wpctl get-volume @DEFAULT_AUDIO_SINK@ "
                  "| awk '{print $2}')", timeout=90)
        time.sleep(2)
        before = shell.run("echo VOLBEFORE=$(wpctl get-volume @DEFAULT_AUDIO_SINK@ "
                           "| awk '{print $2}')", timeout=60)
        shell.run("DISPLAY=:0 xdotool key F10", timeout=60)
        time.sleep(3)
        after = shell.run("echo VOLAFTER=$(wpctl get-volume @DEFAULT_AUDIO_SINK@ "
                          "| awk '{print $2}')", timeout=60)
        bindings = shell.run("DISPLAY=:0 i3-msg -t get_config | "
                             "grep -c 'bindsym F10'", timeout=90)
        first = re.search(r"VOLBEFORE=([0-9.]+)", before)
        second = re.search(r"VOLAFTER=([0-9.]+)", after)
        rose = bool(first and second and float(second.group(1)) > float(first.group(1)))
        check(results, "the printed volume-up key raises the volume", rose)
        record(f"INFO: volume {first.group(1) if first else '?'} -> "
               f"{second.group(1) if second else '?'}; i3 config: "
               f"{bindings.strip()[-40:]}")

        # No second panel or watchdog after an i3 restart: the exec_always
        # scripts are flushed and re-run, and must not stack.
        time.sleep(5)
        count = shell.run(
            "echo PANELS=$(pgrep -c -x xfce4-panel); "
            "echo HIDERS=$(pgrep -c -f '[h]unter-panel-hide'); "
            "echo WATCHDOGS=$(pgrep -c -f '[h]unter-panel$')", timeout=90)
        panels = re.search(r"PANELS=(\d+)", count)
        hiders = re.search(r"HIDERS=(\d+)", count)
        watchdogs = re.search(r"WATCHDOGS=(\d+)", count)
        record(f"INFO: after reload {count.strip()[:120]}")
        check(results, "exactly one panel and one hide helper survive a reload",
              bool(panels and hiders and watchdogs) and
              panels.group(1) == "1" and hiders.group(1) == "1" and
              watchdogs.group(1) == "1")
        log = shell.run("tail -4 ~/.cache/smd/panel-hide.log 2>/dev/null; "
                        "tail -3 ~/.cache/smd/panel.log 2>/dev/null", timeout=60)
        record(f"INFO: panel logs: {log.strip()[:200]}")

        shell.run("DISPLAY=:0 xdotool mousemove 640 400", timeout=30)
        time.sleep(2)
        monitor.screenshot("06-desktop")

        # --- audio: PipeWire, WirePlumber, a real sink -----------------------
        audio = shell.run(
            "pactl info 2>&1 | grep -iE 'server name|server version'; echo ---; "
            "pgrep -x pipewire >/dev/null && echo pipewire-running || echo pipewire-missing; "
            "pgrep -x wireplumber >/dev/null && echo wireplumber-running || echo wireplumber-missing; "
            "echo ---; wpctl status 2>&1 | grep -iE 'sinks|default' | head -4",
            timeout=90)
        chunks = audio.split("---")
        check(results, "the sound server is PipeWire",
              "PipeWire" in chunks[0])
        check(results, "PipeWire and WirePlumber are running",
              "pipewire-running" in chunks[1] and "wireplumber-running" in chunks[1])

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
        scope = shell.run(
            "for p in falkon mpv ristretto xarchiver; do "
            "command -v $p >/dev/null && echo present:$p || echo gone:$p; done; echo ---; "
            "command -v firefox-esr >/dev/null && echo browser-present; "
            "command -v xfce4-panel >/dev/null && echo panel-present",
            timeout=60)
        schunks = scope.split("---")
        check(results, "the trimmed application set is installed",
              "browser-present" in schunks[1] and "panel-present" in schunks[1])
        check(results, "the removed applications are really gone",
              "present:" not in schunks[0])

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

        # --- keyboard mapping and start-up time (recorded, not asserted) ----
        shell.run("DISPLAY=:0 xmodmap -pm 2>/dev/null | grep -E 'mod1|mod4'",
                  timeout=60)
        shell.run("systemd-analyze 2>&1; systemd-analyze blame 2>/dev/null "
                  "| head -8; systemctl --failed --no-pager | head -6", timeout=120)
        record("PASS: live session test finished")
        return 0
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
