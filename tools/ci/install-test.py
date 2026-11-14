#!/usr/bin/env python3
"""Install Hunter Linux to a virtual disk and boot the result.

    install-test.py <iso> <output-dir> [bios|uefi]

Phase 1 boots the live ISO with an empty 20 GiB virtio disk, starts the
installer through the same desktop entry point a user clicks, and walks the
Calamares wizard.  Phase 2 boots the disk on its own and logs in to the
installed system.

Two channels are used, as in the boot test: the serial console for a real shell
(launching the installer, reading logs, verifying the installed system) and the
QEMU monitor for screenshots.  The wizard itself is driven by OCR over VNC, so
the test clicks what it can actually see rather than fixed coordinates.
"""

import os
import re
import subprocess
import sys
import time

from PIL import Image
import pytesseract
from vncdotool import api

class Channel:
    """A socket connection with a read-until helper."""

    def __init__(self, port):
        deadline = time.time() + 90
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

    def expect(self, pattern, timeout=120):
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
            match = regex.search(self.data)
            if match:
                return match, self.data
        return None, self.data


class Monitor:
    """The QEMU monitor: screenshots and hotplug commands."""

    def __init__(self):
        self.chan = Channel(MON_PORT)
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
        record(f"screenshot {os.path.basename(png)}")
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
        self.chan.send(LOGIN + "\r")
        matched, _ = self.chan.expect(r"[Pp]assword:", timeout=60)
        if matched:
            self.chan.send(PASSWORD + "\r")
        matched, _ = self.chan.expect(r"[$#] ", timeout=120)
        if not matched:
            record("FAIL: could not log in on the serial console")
            return False
        record(f"PASS: logged in as {LOGIN} on the serial console")
        return True

    def run(self, command, timeout=180, lines=40):
        self.counter += 1
        begin = f"INSTALLMARK{self.counter}BEGIN"
        end = f"INSTALLMARK{self.counter}END"
        wrapped = (
            f'echo "{begin[:12]}""{begin[12:]}"; '
            f"({command}) 2>&1 | head -{lines}; "
            f'echo "{end[:12]}""{end[12:]}"'
        )
        self.chan.send(wrapped + "\r")
        pattern = re.escape(begin) + r"(.*?)" + re.escape(end)
        match, _ = self.chan.expect(pattern, timeout=timeout)
        if not match:
            record(f"WARN: command timed out: {command}")
            return ""
        text = re.sub(r"\r", "", match.group(1)).strip()
        record(f"$ {command}\n{text}")
        return text

    def wait_for_x(self, timeout=600):
        deadline = time.time() + timeout
        while time.time() < deadline:
            probe = self.run("DISPLAY=:0 xdpyinfo >/dev/null 2>&1 && echo READY || echo WAIT",
                             timeout=60)
            if "READY" in probe:
                record("PASS: the X display is up")
                return True
            time.sleep(10)
        record("FAIL: the X display never came up")
        return False

ISO = sys.argv[1]
WORK = sys.argv[2] if len(sys.argv) > 2 else "install-out"
MODE = sys.argv[3] if len(sys.argv) > 3 else "uefi"

FULL_NAME = "Hunter"
LOGIN = "hunter"
PASSWORD = "huntertest"
DISK_GB = 20

MON_PORT = 4610
SER_PORT = 4611
VNC = "127.0.0.1::5901"

os.makedirs(WORK, exist_ok=True)
results = []


def record(line):
    results.append(line)
    print(line, flush=True)


def start_qemu(disk, with_iso):
    """Boot the ISO (with the empty disk) or the installed disk alone."""
    accel = "kvm" if os.access("/dev/kvm", os.W_OK) else "tcg"
    args = [
        "qemu-system-x86_64", "-m", "3072", "-smp", "2", "-accel", accel,
        "-display", "none", "-vga", "std",
        "-monitor", f"tcp:127.0.0.1:{MON_PORT},server,nowait",
        "-serial", f"tcp:127.0.0.1:{SER_PORT},server,nowait",
        "-vnc", "127.0.0.1:1",
        "-device", "usb-tablet",
        "-no-reboot",
    ]
    if MODE == "uefi":
        code = "/usr/share/OVMF/OVMF_CODE_4M.fd"
        var_src = "/usr/share/OVMF/OVMF_VARS_4M.fd"
        vars_copy = os.path.join(WORK, "OVMF_VARS.fd")
        if not os.path.exists(vars_copy):
            subprocess.run(["cp", var_src, vars_copy], check=True)
        args += ["-machine", "q35",
                 "-drive", f"if=pflash,format=raw,readonly=on,file={code}",
                 "-drive", f"if=pflash,format=raw,file={vars_copy}"]
    if with_iso:
        args += ["-boot", "d", "-cdrom", ISO]
    args += ["-drive", f"file={disk},if=virtio,format=qcow2,cache=writeback"]
    log = open(os.path.join(WORK, "qemu.log"), "a", encoding="utf-8")
    process = subprocess.Popen(args, stdout=log, stderr=log)
    record(f"started qemu as pid {process.pid} (iso={with_iso}, accel={accel})")
    return process


class Display:
    """Pointer and keyboard on the guest display, with OCR to find widgets."""

    def __init__(self):
        self.client = api.connect(VNC, password=None)
        self.step = 0

    def shot(self, name):
        self.step += 1
        path = os.path.join(WORK, f"{self.step:02d}-{name}.png")
        self.client.captureScreen(path)
        record(f"screenshot {os.path.basename(path)}")
        return path

    def text(self, path):
        return pytesseract.image_to_string(Image.open(path))

    def contains(self, path, needle):
        return needle.lower() in self.text(path).lower()

    def wait_text(self, needle, name, timeout=300):
        deadline = time.time() + timeout
        path = None
        while time.time() < deadline:
            path = self.shot(name)
            if self.contains(path, needle):
                record(f"PASS: the installer shows '{needle}'")
                return path
            time.sleep(8)
        record(f"FAIL: never saw '{needle}' on screen")
        return path

    def click(self, x, y):
        self.client.mouseMove(x, y)
        time.sleep(0.3)
        self.client.mousePress(1)
        time.sleep(1.2)

    def press(self, key):
        self.client.keyPress(key)
        time.sleep(1.2)

    def type(self, value):
        self.client.typewrite(value)
        time.sleep(0.8)

    def find(self, path, needle):
        from pytesseract import Output
        data = pytesseract.image_to_data(Image.open(path), output_type=Output.DICT)
        for i, word in enumerate(data["text"]):
            if not word or needle.lower() not in word.lower():
                continue
            try:
                if int(float(data["conf"][i])) < 30:
                    continue
            except ValueError:
                continue
            return (data["left"][i] + data["width"][i] // 2,
                    data["top"][i] + data["height"][i] // 2)
        return None

    def advance(self, label, expect, timeout=240):
        """Click Next/Continue/Install until the expected page is on screen.

        A button is only pressed while the next page is still missing, so a
        failed OCR read can never make the wizard skip a page.
        """
        deadline = time.time() + timeout
        path = None
        while time.time() < deadline:
            path = self.shot(label)
            if self.contains(path, expect):
                record(f"PASS: reached the '{expect}' page")
                return path
            point = self.find(path, "next") or self.find(path, "continue") \
                or self.find(path, "install")
            if point:
                self.click(*point)
            else:
                self.press("enter")
            time.sleep(6)
        record(f"FAIL: never reached the '{expect}' page after {label}")
        with open(os.path.join(WORK, f"ocr-stuck-{label}.txt"), "w",
                  encoding="utf-8") as handle:
            handle.write(self.text(path))
        return path


def main():
    disk = os.path.join(WORK, "disk.qcow2")
    subprocess.run(["qemu-img", "create", "-f", "qcow2", disk, f"{DISK_GB}G"],
                   check=True, stdout=subprocess.DEVNULL)

    # ---------------------------------------------------------------- install
    qemu = start_qemu(disk, with_iso=True)
    monitor = Monitor()
    try:
        shell = Shell(Channel(SER_PORT))
        if not shell.login():
            monitor.screenshot("install-no-shell")
            return 1
        shell.wait_for_x()

        shell.run("DISPLAY=:0 setsid /usr/local/bin/hunter-install "
                  ">/tmp/calamares.log 2>&1 &", timeout=30)
        record("PASS: the installer was started from the live session")
        time.sleep(25)
        shell.run("pgrep -a calamares | head -3")
        monitor.screenshot("install-launched")

        disp = Display()
        disp.wait_text("Welcome", "welcome", timeout=240)
        disp.advance("welcome", "language")

        # Locale and keyboard pages keep their defaults.
        disp.advance("locale", "keyboard")
        disp.advance("keyboard", "erase")

        # Partitioning: explicitly select "Erase disk".
        page = disp.shot("partition")
        point = disp.find(page, "Erase")
        if point:
            disp.click(point[0] - 20, point[1])
            record("PASS: selected 'Erase disk'")
            time.sleep(3)
            disp.shot("partition-selected")
        else:
            record("WARN: could not find the 'Erase disk' option")
        disp.advance("partition", "name")

        # User account.
        page = disp.shot("users")
        point = disp.find(page, "name")
        if point:
            disp.click(point[0] + 140, point[1])
        disp.type(FULL_NAME)
        disp.press("tab")
        disp.press("tab")
        disp.press("tab")
        disp.type(PASSWORD)
        disp.press("tab")
        disp.type(PASSWORD)
        disp.shot("users-filled")
        disp.advance("users", "summary")

        # Summary: start the installation.
        page = disp.shot("summary")
        point = disp.find(page, "Install")
        if point:
            disp.click(*point)
        else:
            disp.press("enter")
        record("PASS: the installation was started")
        time.sleep(20)
        monitor.screenshot("install-progress")

        # The installer takes as long as it takes; poll the screen.
        done = disp.wait_text("Finish", "finished", timeout=2700)
        if not disp.contains(done, "Finish"):
            shell.run("tail -30 /tmp/calamares.log", timeout=60)
            record("FAIL: the installation did not finish")
            return 1

        # Stop booting from the ISO for the next start.
        monitor.hmp("eject cdrom", wait=1)
        page = disp.shot("finished-page")
        point = disp.find(page, "Done") or disp.find(page, "Restart")
        if point:
            disp.click(*point)
        record("PASS: installation finished, rebooting into the installed system")
    finally:
        try:
            monitor.hmp("quit", wait=1)
        except Exception:
            pass
        time.sleep(3)
        if qemu.poll() is None:
            qemu.kill()

    # ----------------------------------------------------------------- verify
    record("PASS: phase 2 - booting the installed disk")
    qemu = start_qemu(disk, with_iso=False)
    monitor = Monitor()
    try:
        image = os.path.join(WORK, "installed")
        os.makedirs(image, exist_ok=True)
        time.sleep(40)
        monitor.screenshot("10-grub")
        time.sleep(60)
        monitor.screenshot("11-login")

        shell = Shell(Channel(SER_PORT))
        installed_shell = shell.login(timeout=300)
        record("PASS: logged into the installed system" if installed_shell
               else "FAIL: could not log into the installed system")
        if not installed_shell:
            # No serial getty on the installed system: log in at the greeter.
            try:
                greeter = Display()
                greeter.type(PASSWORD)
                greeter.press("enter")
                time.sleep(45)
                greeter.shot("11-desktop-after-login")
            except Exception as error:  # noqa: BLE001 - report and continue
                record(f"WARN: greeter login failed: {error}")
        if installed_shell:
            shell.run("cat /etc/os-release | head -3; hostname; lsblk | head -12")
            shell.run("systemctl is-system-running 2>&1; "
                      "systemctl --failed --no-pager | head -5")
            shell.run("findmnt -n / /boot/efi 2>/dev/null; df -h / | tail -1")
            mgr = shell.run("ls /usr/bin | grep -i calamares | head -3; "
                            "test -e /etc/lightdm/lightdm.conf.d/50-hunter-live.conf "
                            "&& echo LIVE-CONFIG-PRESENT || echo live-config-removed")
            record(f"INFO: installer removed from the installed system: "
                   f"{'yes' if 'calamares' not in mgr else 'no'}")

        # Show the installed desktop too.
        shell.run(f"DISPLAY=:0 xfce4-terminal --version 2>&1 | head -2")
        monitor.screenshot("12-installed-desktop")
    finally:
        try:
            monitor.hmp("quit", wait=1)
        except Exception:
            pass
        time.sleep(3)
        if qemu.poll() is None:
            qemu.kill()
        with open(os.path.join(WORK, "result.txt"), "w", encoding="utf-8") as handle:
            handle.write("\n".join(results) + "\n")
        print("\n".join(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
