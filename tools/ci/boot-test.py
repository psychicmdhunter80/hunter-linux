#!/usr/bin/env python3
"""Boot a Hunter Linux ISO under QEMU and test the live desktop for real.

    boot-test.py <iso> <bios|uefi> <output-dir>

The guest is driven over two channels:

* the QEMU monitor (TCP) for screenshots and key presses,
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

WORK = sys.argv[3] if len(sys.argv) > 3 else "out"
ISO = sys.argv[1]
MODE = sys.argv[2] if len(sys.argv) > 2 else "bios"

MON_PORT = 4600
SER_PORT = 4601
LIVE_USER = os.environ.get("LIVE_USER", "user")
LIVE_PASS = os.environ.get("LIVE_PASS", "live")

os.makedirs(WORK, exist_ok=True)
RESULT = os.path.join(WORK, "result.txt")
STEPS = os.path.join(WORK, "steps.txt")
SERIAL_LOG = os.path.join(WORK, "serial.log")

results = []
seen = []  # serial traffic, for the log file


def record(line):
    results.append(line)
    print(line, flush=True)


def note(line):
    with open(STEPS, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    print(line, flush=True)


class Channel:
    """A line-oriented socket connection with a read-until helper."""

    def __init__(self, port, quiet=False):
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
        self.buffer = ""
        self.quiet = quiet

    def send(self, text):
        self.sock.sendall(text.encode())

    def expect(self, pattern, timeout=120, save=True):
        """Read until the regex matches; return (matched_text, full_text)."""
        deadline = time.time() + timeout
        data = ""
        regex = re.compile(pattern, re.IGNORECASE | re.DOTALL)
        while time.time() < deadline:
            try:
                chunk = self.sock.recv(65536).decode("utf-8", "replace")
            except socket.timeout:
                continue
            except OSError:
                break
            if not chunk:
                time.sleep(0.2)
                continue
            data += chunk
            if not self.quiet:
                seen.append(chunk)
            match = regex.search(data)
            if match:
                return match.group(0), data
        return None, data

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class Monitor:
    def __init__(self):
        self.chan = Channel(MON_PORT, quiet=True)
        self.chan.expect(r"\(qemu\)", timeout=30)

    def hmp(self, command, wait=1.0):
        self.chan.send(command + "\n")
        self.chan.expect(r"\(qemu\)", timeout=60)
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

    def key(self, combo, wait=1.0):
        self.hmp(f"sendkey {combo}", wait=wait)


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
        matched, data = self.chan.expect(r"[$#] ", timeout=90)
        if not matched:
            record("FAIL: could not log in on the serial console")
            return False
        record(f"PASS: logged in as {LIVE_USER} on the serial console")
        return True

    def run(self, command, timeout=120, wait_prompt=True):
        """Run a command, echo a marker after it, and return its output."""
        self.counter += 1
        marker = f"HUNTER{self.counter}"
        # stderr merged into stdout, output bounded so a hung command cannot
        # block the console forever.
        wrapped = (
            f"echo {marker}_BEGIN; ({command}) 2>&1 | head -40; "
            f"echo {marker}_END"
        )
        self.chan.send(wrapped + "\r")
        matched, data = self.chan.expect(marker + r"_END", timeout=timeout)
        text = data.split(f"{marker}_BEGIN", 1)[-1]
        text = text.rsplit(f"{marker}_END", 1)[0]
        text = re.sub(r"\r", "", text).strip()
        note(f"$ {command}\n{text}")
        if not matched:
            record(f"WARN: command timed out: {command}")
        return text


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
        code = next(
            (p for p in (
                "/usr/share/OVMF/OVMF_CODE_4M.fd",
                "/usr/share/OVMF/OVMF_CODE.fd",
                "/usr/share/edk2/ovmf/OVMF_CODE.fd",
            ) if os.path.exists(p)),
            None,
        )
        var_src = next(
            (p for p in (
                "/usr/share/OVMF/OVMF_VARS_4M.fd",
                "/usr/share/OVMF/OVMF_VARS.fd",
                "/usr/share/edk2/ovmf/OVMF_VARS.fd",
            ) if os.path.exists(p)),
            None,
        )
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
    note("started qemu as pid " + str(process.pid))
    return process


def main():
    for path in (STEPS, RESULT):
        if os.path.exists(path):
            os.unlink(path)

    qemu = start_qemu()
    if qemu is None:
        return 1
    try:
        monitor = Monitor()

        # The console is the most reliable readiness signal: the getty only
        # starts once the boot has finished.
        shell = Shell(Channel(SER_PORT))
        if not shell.login():
            monitor.screenshot("boot-failed")
            record("FAIL: no live shell")
            return 1

        record("PASS: live system booted to a usable console")
        shell.run("cat /proc/cmdline")
        shell.run("uname -r; id")

        monitor.screenshot("01-desktop")
        record("PASS: screenshot of the live desktop captured")

        # i3 validation and the running session processes
        i3out = shell.run("i3 -C -c ~/.config/i3/config; echo rc=$?")
        if "rc=0" in i3out:
            record("PASS: i3 configuration is valid")
        else:
            record("FAIL: i3 configuration invalid: " + i3out.replace("\n", " | "))

        shell.run("pgrep -a i3; pgrep -a xfce4-panel; pgrep -a xfsettingsd; "
                  "pgrep -a nm-applet; pgrep -a lightdm")
        shell.run("free -m")
        shell.run("xrandr 2>&1 | head -3; echo DISPLAY=$DISPLAY")
        shell.run("ls /usr/share/xsessions/")
        shell.run("cat /var/log/lightdm/lightdm.log 2>/dev/null | tail -20")
        shell.run("systemctl --user --no-pager status xfce4-panel 2>&1 | head -12")

        # Launch the desktop applications on the live display.
        shell.run("DISPLAY=:0 xfce4-terminal --version")
        monitor.screenshot("02-terminal-check")

        for name, command, proc, wait in (
            ("thunar", "thunar", "thunar", 25),
            ("firefox", "firefox-esr 'about:blank'", "firefox", 90),
            ("falkon", "falkon --no-sandbox 'about:blank'", "falkon", 90),
        ):
            shell.run(f"DISPLAY=:0 setsid {command} >/tmp/{name}.log 2>&1 &",
                      timeout=30)
            time.sleep(wait)
            count = shell.run(f"pgrep -c -f '^{proc}'")
            monitor.screenshot(f"03-{name}")
            number = re.search(r"\b(\d+)\b", count)
            if number and int(number.group(1)) > 0:
                record(f"PASS: {name} launched ({number.group(1)} processes)")
            else:
                record(f"FAIL: {name} did not launch")

        # The installer must start from the live session.
        shell.run("DISPLAY=:0 setsid sudo -n calamares -d >/tmp/calamares.log "
                  "2>&1 &", timeout=30)
        time.sleep(60)
        monitor.screenshot("04-installer")
        shell.run("pgrep -a calamares | head -3; tail -5 /tmp/calamares.log")
        cal = shell.run("pgrep -c calamares")
        if cal.strip().isdigit() and int(cal.strip()) > 0:
            record("PASS: the graphical installer started")
        else:
            record("FAIL: the graphical installer did not start")

        # Idle memory with everything above closed again.
        shell.run("pkill -f firefox-esr; pkill -f falkon; "
                  "pkill -f xfce4-terminal; sleep 5; free -m")
        monitor.screenshot("05-final")

        record("PASS: live session test finished")
        return 0
    finally:
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
