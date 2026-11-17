#!/usr/bin/env python3
"""Check the version every part of the image shows, and prove the installer.

Boots one ISO in a virtual machine, reads the version from the files the image
ships, opens the real installer from the live desktop, and captures the window
it puts on screen. The screenshot is the evidence that the label a person sees
is the release the file is named after.

    python3 tools/ci/installer-label.py iso/SMD-Linux-v1.4.1-amd64.iso out-label uefi
"""

import os
import re
import socket
import subprocess
import sys
import time

ISO = sys.argv[1]
WORK = sys.argv[2] if len(sys.argv) > 2 else "label-out"
MODE = sys.argv[3] if len(sys.argv) > 3 else "uefi"

SER_PORT = 4631
MON_PORT = 4630
LOGIN = "user"
PASSWORD = "live"

# The release the file calls itself, e.g. SMD-Linux-v1.4.1-amd64.iso -> 1.4.1
MATCH = re.search(r"v([0-9]+\.[0-9]+(?:\.[0-9]+)?)", os.path.basename(ISO))
EXPECT = MATCH.group(1) if MATCH else ""

os.makedirs(WORK, exist_ok=True)
results = []
passed = True


def record(line):
    results.append(line)
    print(line, flush=True)


def check(ok, line):
    global passed
    record(("PASS: " if ok else "FAIL: ") + line)
    if not ok:
        passed = False
    return ok


class Channel:
    """A telnet-style line channel to a QEMU serial or monitor port."""

    def __init__(self, port, timeout=30):
        deadline = time.time() + timeout
        while True:
            try:
                self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
                break
            except OSError:
                if time.time() > deadline:
                    raise
                time.sleep(0.5)
        self.buffer = ""

    def send(self, text):
        self.sock.sendall(text.encode("utf-8", "replace"))

    def expect(self, pattern, timeout=120):
        regex = re.compile(pattern, re.S)
        deadline = time.time() + timeout
        while time.time() < deadline:
            match = regex.search(self.buffer)
            if match:
                self.buffer = self.buffer[match.end():]
                return match, True
            try:
                self.sock.settimeout(2)
                chunk = self.sock.recv(65536)
            except socket.timeout:
                continue
            except OSError:
                return None, False
            if not chunk:
                return None, False
            self.buffer += chunk.decode("utf-8", "replace")
        return None, False


class Shell:
    """A login shell on the guest's serial console."""

    def __init__(self, chan):
        self.chan = chan
        self.counter = 0

    def login(self, timeout=1200):
        matched, _ = self.chan.expect(r"login:", timeout=timeout)
        if not matched:
            record("FAIL: no login prompt on the serial console")
            return False
        self.chan.send(LOGIN + "\r")
        matched, _ = self.chan.expect(r"[Pp]assword:", timeout=120)
        if matched:
            self.chan.send(PASSWORD + "\r")
        matched, _ = self.chan.expect(r"[$#] ", timeout=240)
        if not matched:
            record("FAIL: could not log in on the serial console")
            return False
        record("PASS: logged in on the serial console")
        return True

    def run(self, command, timeout=180, lines=40):
        self.counter += 1
        begin = "LABELMARK%02dBEGIN" % self.counter
        end = "LABELMARK%02dEND" % self.counter
        self.chan.send('%s; (%s) 2>&1 | head -%d; echo %s\r'
                       % (begin, command, lines, end))
        match, _ = self.chan.expect(re.escape(begin) + r"(.*?)" + re.escape(end),
                                    timeout=timeout)
        if not match:
            record("WARN: command timed out: " + command)
            return ""
        text = re.sub(r"\r", "", match.group(1)).strip()
        record("$ %s\n%s" % (command, text))
        return text

    def wait_for_x(self, timeout=900):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if "READY" in self.run("DISPLAY=:0 xdpyinfo >/dev/null 2>&1 "
                                   "&& echo READY || echo WAIT", timeout=60):
                self.run("DISPLAY=:0 xset s off -dpms >/dev/null 2>&1; "
                         "DISPLAY=:0 xset s noblank >/dev/null 2>&1; echo LIT")
                return check(True, "the live desktop is up")
            time.sleep(10)
        return check(False, "the live desktop never came up")


def start_qemu():
    accel = "kvm" if os.access("/dev/kvm", os.W_OK) else "tcg"
    disk = os.path.join(WORK, "disk.qcow2")
    if not os.path.exists(disk):
        subprocess.run(["qemu-img", "create", "-f", "qcow2", disk, "12G"],
                       check=True, stdout=subprocess.DEVNULL)
    args = [
        "qemu-system-x86_64", "-m", "3072", "-smp", "2", "-accel", accel,
        "-display", "none", "-vga", "std",
        "-monitor", "tcp:127.0.0.1:%d,server,nowait" % MON_PORT,
        "-serial", "tcp:127.0.0.1:%d,server,nowait" % SER_PORT,
        "-device", "qemu-xhci", "-device", "usb-tablet", "-no-reboot",
        "-netdev", "user,id=n0", "-device", "virtio-net-pci,netdev=n0",
    ]
    if MODE == "uefi":
        code = "/usr/share/OVMF/OVMF_CODE_4M.fd"
        var_src = "/usr/share/OVMF/OVMF_VARS_4M.fd"
        vars_copy = os.path.join(WORK, "OVMF_VARS.fd")
        if not os.path.exists(vars_copy):
            subprocess.run(["cp", var_src, vars_copy], check=True)
        args += ["-machine", "q35",
                 "-drive", "if=pflash,format=raw,readonly=on,file=" + code,
                 "-drive", "if=pflash,format=raw,file=" + vars_copy]
    args += ["-boot", "d", "-cdrom", ISO,
             "-drive", "file=%s,if=virtio,format=qcow2,cache=writeback" % disk]
    log_path = os.path.join(WORK, "qemu.log")
    log = open(log_path, "a", encoding="utf-8")
    process = subprocess.Popen(args, stdout=log, stderr=log)
    record("started qemu as pid %d (accel=%s)" % (process.pid, accel))
    time.sleep(4)
    if process.poll() is not None:
        with open(log_path, encoding="utf-8", errors="replace") as handle:
            record("FAIL: qemu exited immediately: " + handle.read().strip()[:400])
        return None
    return process


def screenshot(monitor, name):
    """Ask QEMU for the display, because a screenshot cannot go stale."""
    ppm = os.path.join(WORK, "screen-%s.ppm" % name)
    png = os.path.join(WORK, "screen-%s.png" % name)
    monitor.send("screendump %s\n" % ppm)
    monitor.expect(r"\(qemu\)", timeout=60)
    time.sleep(2)
    if not os.path.exists(ppm):
        record("WARN: the display could not be captured")
        return None
    subprocess.run(["convert", ppm, png], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.path.exists(png):
        os.unlink(ppm)
        return png
    return None


def ocr(path):
    if not path or not os.path.exists(path):
        return ""
    text = subprocess.run(["tesseract", path, "stdout"], capture_output=True,
                          text=True, check=False)
    return text.stdout


def main():
    if not EXPECT:
        record("FAIL: the ISO file name carries no release version")
        return 1

    qemu = start_qemu()
    if qemu is None:
        return 1
    try:
        shell = Shell(Channel(SER_PORT))
        if not shell.login():
            return 1
        if not shell.wait_for_x():
            return 1

        # ------------------------------------------------ what the image says
        branding = shell.run("grep -E 'productName|^ +version:|versionedName' "
                             "/etc/calamares/branding/hunter/branding.desc",
                             timeout=60)
        for field in ("productName", "version:", "versionedName"):
            line = [l for l in branding.splitlines() if field in l]
            found = re.findall(r'"([^"]*)"', line[0]) if line else []
            value = found[0] if found else ""
            check(value.endswith(EXPECT) or value == EXPECT,
                  "Calamares %s is %r (expected %s)" % (field.strip(": "),
                                                       value, EXPECT))

        osr = shell.run(". /etc/os-release; echo \"$PRETTY_NAME|$VERSION_ID\"",
                        timeout=60)
        check(EXPECT in osr, "/etc/os-release says %r" % osr.strip())
        issue = shell.run("head -1 /etc/issue", timeout=60)
        check(EXPECT in issue, "/etc/issue says %r" % issue.strip())
        lsb = shell.run(". /etc/lsb-release; echo \"$DISTRIB_DESCRIPTION\"", timeout=60)
        check(EXPECT in lsb, "/etc/lsb-release says %r" % lsb.strip())

        # ------------------------------------------- what the installer shows
        shell.run("DISPLAY=:0 setsid /usr/local/bin/hunter-install "
                  ">/tmp/calamares.log 2>&1 &", timeout=60)
        time.sleep(35)

        title = shell.run("DISPLAY=:0 xdotool search --class calamares "
                          "getwindowname %1 2>/dev/null | head -2", timeout=60)
        running = "RUNNING" in shell.run(
            "pgrep -f 'calamares' >/dev/null && echo RUNNING || echo GONE",
            timeout=60)
        if not check(running, "the installer started from the live desktop"):
            record("INFO: installer log: " + shell.run(
                "tail -3 /tmp/calamares.log", timeout=60))

        monitor = Channel(MON_PORT)
        monitor.expect(r"\(qemu\)", timeout=60)

        # The sidebar carries the product name and the version on every page.
        text = ""
        png = None
        for attempt in range(6):
            png = screenshot(monitor, "installer-label-%d" % attempt)
            text = ocr(png)
            if EXPECT in text:
                break
            time.sleep(10)
        if png:
            record("INFO: installer window title: %r" % title.strip())
            check(title.strip() != "" and EXPECT in title,
                  "the installer window is called %r" % title.strip())
            check(EXPECT in text, "the installer on screen shows %s" % EXPECT)
            check("1.3" not in text, "the installer on screen shows no 1.3")
            record("INFO: text read from the screen:\n" + text.strip()[:1200])
        else:
            check(False, "the installer screen could not be captured")

        return 0 if passed else 1
    finally:
        qemu.terminate()
        try:
            qemu.wait(timeout=30)
        except subprocess.TimeoutExpired:
            qemu.kill()
        with open(os.path.join(WORK, "result.txt"), "w", encoding="utf-8") as handle:
            handle.write("\n".join(results) + "\n")
        for line in results:
            if line.startswith("FAIL"):
                passed = False
        record("RESULT: %s" % ("passed" if passed else "failed"))


if __name__ == "__main__":
    sys.exit(main())
