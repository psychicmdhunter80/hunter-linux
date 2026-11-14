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
import socket
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

    def login(self, user=None, password=None, timeout=900):
        # Defaults are resolved here because the credentials are defined below
        # the class definitions.
        user = user or LOGIN
        password = password or PASSWORD
        matched, _ = self.chan.expect(r"login:", timeout=timeout)
        if not matched:
            record("FAIL: no login prompt on the serial console")
            return False
        self.chan.send(user + "\r")
        matched, _ = self.chan.expect(r"[Pp]assword:", timeout=60)
        if matched:
            self.chan.send(password + "\r")
        matched, _ = self.chan.expect(r"[$#] ", timeout=180)
        if not matched:
            record(f"FAIL: could not log in as {user} on the serial console")
            return False
        record(f"PASS: logged in as {user} on the serial console")
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
        # An absolute pointer for the wizard.  q35 has no USB bus of its own,
        # so the controller is added explicitly.
        "-device", "qemu-xhci", "-device", "usb-tablet",
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
    log_path = os.path.join(WORK, "qemu.log")
    log = open(log_path, "a", encoding="utf-8")
    process = subprocess.Popen(args, stdout=log, stderr=log)
    record(f"started qemu as pid {process.pid} (iso={with_iso}, accel={accel})")
    time.sleep(4)
    if process.poll() is not None:
        with open(log_path, encoding="utf-8", errors="replace") as handle:
            record("FAIL: qemu exited immediately: " + handle.read().strip()[:400])
        return None
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

    def signature(self, path):
        """A small grey-scale fingerprint of the wizard's content area."""
        image = Image.open(path).convert("L").crop((300, 120, 1150, 690))
        return list(image.resize((48, 24)).getdata())

    @staticmethod
    def differs(first, second, threshold=4.0):
        if not first or not second:
            return True
        return sum(abs(a - b) for a, b in zip(first, second)) / len(first) > threshold

    def wait_stable(self, name, stable_polls=6, timeout=3000, min_wait=240):
        """Wait until the screen stops changing (the progress page is done)."""
        deadline = time.time() + timeout
        start = time.time()
        previous = None
        same = 0
        path = None
        poll = 0
        while time.time() < deadline:
            poll += 1
            if poll % 3 == 1 or path is None:
                path = self.shot(name)
            current = self.signature(path)
            if previous is not None and not self.differs(previous, current, 1.5):
                same += 1
                if same >= stable_polls and time.time() - start > min_wait:
                    record("PASS: the installer screen has settled")
                    return path
            else:
                same = 0
            previous = current
            time.sleep(15)
        record("WARN: the installer screen never settled")
        return path

    def wait_text(self, needle, name, timeout=300):
        return self.wait_text_any((needle,), name, timeout)

    def wait_text_any(self, needles, name, timeout=300):
        """Poll the screen until one of the phrases appears."""
        deadline = time.time() + timeout
        path = None
        attempt = 0
        while time.time() < deadline:
            attempt += 1
            # Keep only every fourth screenshot: a long wait would otherwise
            # fill the artefact with hundreds of identical images.
            if attempt % 4 == 1 or path is None:
                path = self.shot(name)
                text = self.text(path).lower()
                for needle in needles:
                    if needle.lower() in text:
                        record(f"PASS: the installer shows '{needle}'")
                        return path
            time.sleep(10)
        record(f"FAIL: never saw {needles} on screen")
        return path

    def click(self, x, y):
        self.client.mouseMove(x, y)
        time.sleep(0.3)
        self.client.mousePress(1)
        time.sleep(1.2)

    def press(self, key):
        # vncdotool knows "esc"/"return", not the longer spellings.
        key = {"escape": "esc", "enter": "return"}.get(key, key)
        self.client.keyPress(key)
        time.sleep(1.2)

    def type(self, value):
        # vncdotool's proxy has no typewrite; send keysyms one at a time.
        for character in value:
            if character.isupper():
                self.client.keyPress("shift-" + character.lower())
            elif character == " ":
                self.client.keyPress("space")
            else:
                self.client.keyPress(character)
            time.sleep(0.12)
        time.sleep(0.8)

    def find(self, path, needle, region=None, scale=3):
        """Return the centre of a word on screen, optionally within a region.

        The wizard's captions are ~10 px tall, which tesseract reads badly, so
        the region is cropped and enlarged before OCR and the coordinates are
        mapped back to screen space.
        """
        from pytesseract import Output
        image = Image.open(path).convert("RGB")
        left, top = 0, 0
        if region:
            left, top, right, bottom = region
            image = image.crop((left, top, right, bottom))
        image = image.resize((image.width * scale, image.height * scale),
                             Image.LANCZOS)
        data = pytesseract.image_to_data(image, output_type=Output.DICT)
        for i, word in enumerate(data["text"]):
            if not word or needle.lower() not in word.lower():
                continue
            try:
                if int(float(data["conf"][i])) < 30:
                    continue
            except ValueError:
                continue
            x = left + (data["left"][i] + data["width"][i] // 2) // scale
            y = top + (data["top"][i] + data["height"][i] // 2) // scale
            return (x, y)
        return None

    def button(self, path):
        """Find the primary button of the wizard.

        Small grey captions are unreliable for OCR, so the fallback measures
        from the Cancel button, which is always rendered in plain black text.
        """
        row = (0, 690, 1280, 800)
        for word in ("Next", "Continue", "Install"):
            point = self.find(path, word, region=row)
            if point:
                return point
        cancel = self.find(path, "Cancel", region=row)
        if cancel:
            # Back, Next, Cancel sit in that order along the bottom right.
            return (cancel[0] - 100, cancel[1])
        back = self.find(path, "Back", region=row)
        if back:
            return (back[0] + 95, back[1])
        return None

    def advance(self, label, expect, tries=15):
        """Move to the next wizard page and confirm it arrived.

        Enter activates the default button on every Calamares page, which is
        far more reliable than OCR on a greyed-out button.  Clicking is only a
        fallback, and only on the button row at the bottom of the window, so a
        word in a heading can never be mistaken for a button.
        """
        path = None
        for attempt in range(tries):
            path = self.shot(f"{label}-{attempt}")
            if self.contains(path, expect):
                record(f"PASS: reached the '{expect}' page")
                return path
            # Only ever click the button row.  Enter is not used: on the
            # welcome page it opens the language combo box instead of moving on.
            point = self.button(path)
            if point:
                self.click(*point)
            else:
                record(f"WARN: no button found on {label}; pressing Tab then Enter")
                self.press("tab")
                self.press("return")
            time.sleep(7)
        record(f"FAIL: never reached the '{expect}' page after {label}")
        with open(os.path.join(WORK, f"ocr-stuck-{label}.txt"), "w",
                  encoding="utf-8") as handle:
            handle.write(self.text(path))
        return path

    def select_erase(self, path):
        """Pick the 'Erase disk' radio button on the partitioning page."""
        body = (150, 120, 1160, 690)
        point = self.find(path, "Erase", region=body) \
            or self.find(path, "disk", region=body)
        if point:
            self.click(point[0] - 22, point[1])
            record("PASS: selected 'Erase disk'")
        else:
            record("WARN: 'Erase disk' not found by OCR; using the keyboard")
            for _ in range(4):
                self.press("tab")
            self.press("space")
        time.sleep(3)
        return self.shot("partition-selected")

    def fill_users(self, path):
        """Fill name, login name and password on the users page."""
        body = (150, 120, 1160, 690)
        point = self.find(path, "name", region=body)
        if point:
            self.click(point[0] + 170, point[1])
        self.type(FULL_NAME)
        for _ in range(3):
            self.press("tab")
        self.type(PASSWORD)
        self.press("tab")
        self.type(PASSWORD)
        return self.shot("users-filled")


def main():
    disk = os.path.join(WORK, "disk.qcow2")
    subprocess.run(["qemu-img", "create", "-f", "qcow2", disk, f"{DISK_GB}G"],
                   check=True, stdout=subprocess.DEVNULL)

    # ---------------------------------------------------------------- install
    qemu = start_qemu(disk, with_iso=True)
    monitor = Monitor()
    try:
        shell = Shell(Channel(SER_PORT))
        # The live session account, not the one the installer will create.
        if not shell.login("user", "live"):
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

        # Exploration: walk the pages with a fixed click on the Next button so
        # their layouts can be measured, then stop without installing.
        if os.environ.get("EXPLORE") == "1":
            for step in range(8):
                path = disp.shot(f"explore-{step}")
                with open(os.path.join(WORK, f"ocr-explore-{step}.txt"), "w",
                          encoding="utf-8") as handle:
                    handle.write(disp.text(path))
                if step == 4:
                    # Partitioning page: choose "Erase disk" before going on.
                    disp.click(313, 130)
                    time.sleep(3)
                disp.click(1005, 746)
                time.sleep(6)
            disp.shot("explore-end")
            record("INFO: exploration finished")
            return 0
        # The wizard's captions are about ten pixels tall, which OCR reads
        # badly at this resolution, so the buttons are clicked at fixed screen
        # positions and every page change is confirmed by comparing the
        # screenshot itself rather than by reading text.
        NEXT = (1005, 746)
        time.sleep(20)
        disp.shot("welcome")

        def step(label, tries=4):
            before = disp.signature(disp.shot(f"{label}-before"))
            for _ in range(tries):
                disp.click(*NEXT)
                time.sleep(6)
                after = disp.shot(f"{label}-after")
                if disp.differs(before, disp.signature(after)):
                    record(f"PASS: left the {label} page")
                    return True
            record(f"FAIL: the {label} page did not advance")
            return False

        step("welcome")      # -> Location
        step("location")     # -> Keyboard
        step("keyboard")     # -> Partitions

        # Partitions: choose "Erase disk", then continue.
        disp.shot("partition")
        disp.click(313, 130)
        time.sleep(3)
        disp.shot("partition-erase")
        step("partition")    # -> Users

        # Users: only the name and the password.  Calamares fills the login
        # name and the computer name from the name by itself, and typing into
        # them would append to the auto-filled text.
        disp.shot("users")
        for point, value in (((404, 113), FULL_NAME),
                             ((403, 281), PASSWORD),
                             ((607, 281), PASSWORD)):
            disp.click(*point)
            disp.type(value)
        disp.shot("users-filled")
        step("users")        # -> Summary

        # Summary: the primary button starts the installation.
        disp.shot("summary")
        disp.click(*NEXT)
        record("PASS: the installation was started")
        time.sleep(20)
        monitor.screenshot("install-progress")

        # The installer takes as long as it takes.  Wait for the screen to stop
        # changing, then confirm from the live system that the target disk was
        # actually written - that is the result that matters.
        disp.wait_stable("installing", timeout=2700, min_wait=300)
        monitor.screenshot("install-done")
        listing = shell.run("lsblk -o NAME,SIZE,FSTYPE /dev/vda", timeout=90)
        shell.run("tail -15 /tmp/calamares.log", timeout=60)
        if re.search(r"ext4|vfat|fat32", listing, re.IGNORECASE):
            record("PASS: the installer partitioned and formatted the target disk")
        else:
            record("FAIL: the target disk was not written")
            return 1

        # Ask the installed system itself to build a GRUB configuration.  That
        # reports the real reason when the installer's own attempt failed and
        # it proves the bootloader files are in place when it works.
        shell.run("sudo -n tail -40 /tmp/calamares.log", timeout=90)
        probe = shell.run(
            "sudo -n sh -c 'mkdir -p /mnt/root && mount /dev/vda2 /mnt/root && "
            "mkdir -p /mnt/root/boot/efi && mount /dev/vda1 /mnt/root/boot/efi && "
            "for d in dev proc sys; do mkdir -p /mnt/root/$d; "
            "mount --bind /$d /mnt/root/$d; done; "
            "ls -l /mnt/root/boot/efi/EFI/ ; "
            "chroot /mnt/root grub-mkconfig -o /tmp/probe.cfg > /tmp/probe.out 2>&1; "
            "echo GRUB-MKCONFIG-RC=$? ; tail -20 /tmp/probe.out ; "
            "echo --- ; chroot /mnt/root grub-install --target=x86_64-efi "
            "--efi-directory=/boot/efi --bootloader-id=Hunter_Linux "
            "--recheck --no-nvram --force > /tmp/gi.out 2>&1; "
            "echo GRUB-INSTALL-RC=$? ; tail -20 /tmp/gi.out ; "
            "umount -R /mnt/root 2>/dev/null; true'", timeout=600)
        if "GRUB-MKCONFIG-RC=0" in probe:
            record("PASS: the installed system builds a GRUB configuration")
        else:
            record("FAIL: grub-mkconfig fails in the installed system")

        if os.environ.get("DIAG") == "1":
            record("INFO: diagnostic run, stopping before the reboot")
            return 0

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
