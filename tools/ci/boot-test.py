#!/usr/bin/env python3
"""Boot a Hunter Linux ISO under QEMU and test the live desktop for real.

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
            ("falkon", "falkon --no-sandbox 'about:blank'", "falkon", 90),
        ):
            shell.run(f"DISPLAY=:0 setsid {command} >/tmp/{name}.log 2>&1 &",
                      timeout=30)
            time.sleep(wait)
            count = shell.run(f"pgrep -c -f '^[a-z]*{proc}'")
            monitor.screenshot(f"02-{name}")
            number = re.search(r"^(\d+)$", count.strip(), re.M)
            check(results, f"{name} launched",
                  bool(number) and int(number.group(1)) > 0)

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
            shell.run("DISPLAY=:0 xfce4-panel -q; sleep 2; "
                      "mv -f ~/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml "
                      "~/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml.bak; "
                      "DISPLAY=:0 xfconf-query -c xfce4-panel -r -R >/dev/null 2>&1; "
                      "echo reset-done", timeout=120)
            shell.run("DISPLAY=:0 setsid xfce4-panel >/tmp/panel.log 2>&1 &", timeout=30)
            time.sleep(25)
            monitor.screenshot("05-panel-default")
            shell.run("DISPLAY=:0 xfconf-query -c xfce4-panel -l | head -40", timeout=60)
            shell.run("cat /tmp/panel.log | head -20", timeout=30)

        # --- idle memory -----------------------------------------------------
        shell.run("pkill -f firefox-esr; pkill -f falkon; pkill -f calamares; "
                  "sleep 8; free -m", timeout=60)
        monitor.screenshot("04-final")
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
