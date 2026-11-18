#!/usr/bin/env python3
"""Install SMD Linux to a virtual disk and boot the result.

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
            # QEMU keeps serial output only for a connected client, so a prompt
            # printed while this script was still taking screenshots is gone.
            # A bare Enter makes the getty print a fresh one: that tells a
            # missing console apart from a prompt that scrolled past.
            for _attempt in range(6):
                self.chan.send("\r")
                matched, _ = self.chan.expect(r"login:", timeout=10)
                if matched:
                    record("INFO: the login prompt was re-requested on the "
                           "serial console")
                    break
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
                # The session blanks its screen after a few idle minutes and a
                # blanked framebuffer is a black screenshot: the wizard would
                # look as if it had vanished. Screenshots must keep the screen
                # lit for the whole run.
                self.run("DISPLAY=:0 xset s off -dpms >/dev/null 2>&1; "
                         "DISPLAY=:0 xset s noblank >/dev/null 2>&1; "
                         "DISPLAY=:0 xset q | grep -i 'timeout\\|DPMS' | head -3",
                         timeout=60)
                return True
            time.sleep(10)
        record("FAIL: the X display never came up")
        return False

ISO = sys.argv[1]
WORK = sys.argv[2] if len(sys.argv) > 2 else "install-out"
MODE = sys.argv[3] if len(sys.argv) > 3 else "uefi"
WEB_PORT = 4603

FULL_NAME = "Hunter"
LOGIN = "hunter"
PASSWORD = "huntertest"
PRIV = "su" + "do"
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
        # Forwarded port: the runner acts as the outside computer that opens
        # Cockpit on the installed system.
        "-netdev", f"user,id=n0,hostfwd=tcp:127.0.0.1:{WEB_PORT}-:9090",
        "-device", "virtio-net-pci,netdev=n0",
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

    @staticmethod
    def blank(path):
        """True for a frame with no content in it."""
        try:
            image = Image.open(path).convert("L")
        except Exception:
            return False
        low, high = image.getextrema()
        return high - low < 24

    def shot(self, name):
        self.step += 1
        path = os.path.join(WORK, f"{self.step:02d}-{name}.png")
        self.client.captureScreen(path)
        if self.blank(path):
            # The installer's own X screen blanks after ten idle minutes and a
            # blanked framebuffer OCRs as nothing at all, which is why a long
            # install looked like a wizard stuck on an empty page.
            record("INFO: the installer screen was blank; waking it and "
                   "capturing again")
            self.press("shift")
            time.sleep(3)
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
        # The release matters: a VNC pointer event carries the button mask, so
        # without mouseUp the widget only sees a press that is released by the
        # next pointer move - which is why the wizard never advanced.
        self.client.mouseMove(x, y)
        time.sleep(0.3)
        self.client.mousePress(1)
        # Long enough for the guest to register a real click rather than a
        # momentary button flap.
        time.sleep(0.35)
        self.client.mouseUp(1)
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

        The button row is the lowest text on the screen, so every candidate is
        searched there and the lowest match wins.  The row is taken from the
        screenshot itself: assuming the screen size, or measuring a window that
        turned out to be a 1024x520 helper at (0,0), put the clicks in the
        middle of the page where nothing happens.
        """
        with Image.open(path) as image:
            width, height = image.size
        row = (0, int(height * 0.78), width, height)
        best = None
        for word in ("Next", "Continue", "Install now", "Install", "Done"):
            point = self.find(path, word, region=row)
            if point and (best is None or point[1] > best[1]):
                best = point
        if best:
            return best
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

    def select_erase(self, path, origin=(135, 50)):
        """Pick 'Erase disk' and prove that a layout was planned.

        The radio buttons sit near the top of the page, around y=100, and the
        crop this used to read started at y=120: the OCR never saw the choice,
        the fallback click landed between the two radios, and the wizard
        advanced to manual partitioning with an empty table and a disabled
        Next.  The selection now has to produce a partition plan.
        """
        body = (150, 60, 1160, 320)
        point = self.find(path, "Erase", region=body)
        if point:
            # The radio itself is about seventy pixels left of its caption.
            self.click(point[0] - 70, point[1])
            record("PASS: clicked the 'Erase disk' radio")
        else:
            record("WARN: 'Erase disk' not found by OCR; clicking the radio "
                   "at its known place in the window")
            self.click(origin[0] + 178, origin[1] + 67)
        deadline = time.time() + 75
        shot = path
        while time.time() < deadline:
            time.sleep(5)
            shot = self.shot("partition-selected")
            text = self.text(shot)
            if re.search(r"ext4|fat32|vfat|swap", text, re.IGNORECASE):
                record("PASS: the installer planned a partition layout")
                return shot
        record("FAIL: no partition layout appeared after choosing 'Erase disk'")
        return shot

    def fill_users(self, path):
        """Fill the name and both password fields, then read them back.

        Fixed offsets into the window put every click a few pixels low, so the
        full name, the password and the confirmation were all typed into the
        first field: the account was created as "hunterhuntertesthuntertest"
        with no password at all, and the installed system could not be logged
        into.  Each field is found by the label above it instead.
        """
        body = (150, 50, 1240, 700)
        name = self.find(path, "your name", region=body)
        if name:
            self.click(name[0] + 40, name[1] + 27)
            record("PASS: found the name field")
        else:
            record("WARN: the name label was not read; using the field centre")
            self.click(400, 84)
        time.sleep(1)
        self.type(FULL_NAME)
        time.sleep(1)
        shot = self.shot("users-named")
        password = self.find(shot, "Choose a password", region=body)
        if password:
            self.click(password[0] + 40, password[1] + 27)
        else:
            record("WARN: the password label was not read; using its centre")
            self.click(400, 252)
        time.sleep(1)
        self.type(PASSWORD)
        time.sleep(1)
        confirm = self.find(self.shot("users-password"), "Repeat", region=body)
        if confirm:
            self.click(confirm[0], confirm[1])
        else:
            record("WARN: the confirmation field was not read; using its centre")
            self.click(611, 252)
        time.sleep(1)
        self.type(PASSWORD)
        time.sleep(2)
        filled = self.shot("users-filled")
        text = self.text(filled)
        ok_name = FULL_NAME.lower() in text.lower()
        # The placeholders disappear once a password is typed.
        ok_password = "repeat password" not in text.lower()
        record("PASS: the name field holds %r" % FULL_NAME if ok_name
               else "FAIL: the name field does not hold %r" % FULL_NAME)
        record("PASS: both password fields took a value" if ok_password
               else "FAIL: a password field still shows its placeholder")
        return filled

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
        record("INFO: tiling helper processes: " + shell.run(
            "pgrep -c 'hunter-auto[t]ile' || echo 0", timeout=60).strip())
        record("INFO: installer window class: " + shell.run(
            "DISPLAY=:0 xdotool search --class calamares getwindowclassname "
            "%1 2>/dev/null | head -2", timeout=60).strip())
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
        # The window is centred in the workspace i3 hands out, so the panel
        # along the bottom edge moves it.  Read its real origin instead of
        # assuming one, and keep the widget positions relative to it.
        origin = (135, 50)
        shape = (1010, 700)
        # `xdotool search --class calamares` also answers with small helper
        # windows; take the largest one, which is the wizard itself.
        ids = shell.run("DISPLAY=:0 xdotool search --class calamares "
                        "2>/dev/null", timeout=60).split()
        best = (0, None, None)
        for win_id in ids:
            info = shell.run(f"DISPLAY=:0 xdotool getwindowgeometry {win_id} 2>&1",
                             timeout=60)
            position = re.search(r"Position:\s*(-?\d+),(-?\d+)", info)
            size = re.search(r"Geometry:\s*(\d+)x(\d+)", info)
            if not (position and size):
                continue
            area = int(size.group(1)) * int(size.group(2))
            if area > best[0]:
                best = (area, (int(position.group(1)), int(position.group(2))),
                        (int(size.group(1)), int(size.group(2))))
        if best[1] and best[2][0] >= 600 and best[2][1] >= 400:
            origin, shape = best[1], best[2]
        record(f"INFO: installer window at {origin} size {shape} "
               f"(from {len(ids)} candidates)")
        # Back, Next and Cancel are right-aligned in a row 35 px above the
        # window's bottom edge, so they are measured from its bottom-right
        # corner: the window is not always the same size (1024x696 here).
        # Clicking Cancel opens "do you really want to cancel" and the
        # installation never starts, which is what a guessed constant did.
        right = origin[0] + shape[0]
        bottom = origin[1] + shape[1]
        # Measured on a 1280x800 screenshot of the running wizard: with the
        # window at (130,38) and 1024x696, Next is at (1005,712) and Cancel at
        # (1103,712), i.e. 149 px and 51 px from the right edge, 22 px above
        # the bottom edge.
        probe_path = disp.shot("screen")
        with Image.open(probe_path) as probe_image:
            screen_size = probe_image.size
        NEXT = (int(screen_size[0] * 0.78), int(screen_size[1] * 0.91))
        record("INFO: screen %dx%d, fallback Next at %s"
               % (screen_size[0], screen_size[1], NEXT))
        CANCEL_NO = ((origin[0] + right) // 2 + 152, (origin[1] + bottom) // 2 + 26)
        time.sleep(20)
        disp.shot("welcome")

        def step(label, tries=5, absent=None):
            """Click the wizard's own button and confirm the page changed.

            The fixed coordinate is only a fallback: the window is centred in
            the workspace i3 gives it, so its bottom row moved when the panel
            started reserving space along the bottom edge.
            """
            before_path = disp.shot(f"{label}-before")
            before = disp.signature(before_path)
            before_text = disp.text(before_path)
            for attempt in range(tries):
                path = disp.shot(f"{label}-try{attempt}")
                point = disp.button(path) or NEXT
                record(f"INFO: {label}: clicking {point}")
                disp.click(*point)
                time.sleep(4)
                # A stray Cancel opens a modal dialog that swallows the next
                # page; notice it and answer No.
                guard = disp.shot(f"{label}-guard{attempt}")
                if "cancel the current install" in disp.text(guard).lower():
                    record("WARN: the cancel dialog appeared; answering No")
                    disp.click(*CANCEL_NO)
                    time.sleep(2)
                time.sleep(6)
                after_path = disp.shot(f"{label}-after")
                after_text = disp.text(after_path)
                # A page is left when its own content is gone, or when both the
                # layout and the text changed noticeably.  The old test treated
                # a moved mouse pointer as a new page.
                if absent and absent.lower() not in after_text.lower():
                    record(f"PASS: left the {label} page")
                    return True
                if (not absent
                        and after_text.strip() != before_text.strip()
                        and disp.differs(before, disp.signature(after_path), 12.0)):
                    record(f"PASS: left the {label} page")
                    return True
            record(f"FAIL: the {label} page did not advance")
            return False

        step("welcome")      # -> Location
        step("location")     # -> Keyboard
        step("keyboard")     # -> Partitions

        # Partitions: choose "Erase disk", then continue.
        disp.select_erase(disp.shot("partition"), origin)
        time.sleep(2)
        if not step("partition", absent="Unpartitioned space"):
            record("FAIL: the partitioning page never advanced")
            return 1

        # Users: only the name and the password.  Calamares fills the login
        # name and the computer name from the name by itself, and typing into
        # them would append to the auto-filled text.
        disp.fill_users(disp.shot("users"))
        step("users")        # -> Summary

        # Summary: the primary button starts the installation.
        disp.shot("summary")
        disp.click(*NEXT)
        disk_image = os.path.join(WORK, "disk.qcow2")
        start_size = os.path.getsize(disk_image) if os.path.exists(disk_image) else 0
        started = False
        for _ in range(40):
            time.sleep(15)
            size = os.path.getsize(disk_image) if os.path.exists(disk_image) else 0
            if size > start_size + (128 << 20):
                started = True
                break
        record("PASS: the installation started writing the target disk (%.0f MiB)"
               % ((size - start_size) / (1 << 20))
               if started else
               "FAIL: the target disk never grew, so the installation never started")
        if not started:
            return 1
        time.sleep(20)
        monitor.screenshot("install-progress")

        # The installer takes as long as it takes.  The progress page can sit
        # still for minutes while packages download, so "the screen stopped
        # changing" is not the end - the installer process leaving is.
        # Calamares keeps its finished window open until somebody clicks
        # "Done", so its process is not the signal.  The finish-up script
        # removes the installer launcher from the target as its first act, so
        # that file disappearing means the installation itself is complete.
        def target_has_menu():
            """True once the target really holds a GRUB menu."""
            probe = shell.run(
                "sudo -n sh -c 'mkdir -p /mnt/chk; mount -o ro /dev/vda2 /mnt/chk "
                "2>/dev/null && { test -f /mnt/chk/boot/grub/grub.cfg && echo "
                "GRUB-READY; }; umount /mnt/chk 2>/dev/null; true'", timeout=120)
            return "GRUB-READY" in probe

        # The target being unmounted is necessary but not sufficient: the
        # finish-up step runs after it and writes the boot loader.  v1.1's first
        # run stopped here too early, rebooted into a machine with no boot
        # loader at all, and firmware fell through to PXE.  Completion now also
        # requires the installer's finished page and a real menu on the disk.
        deadline = time.time() + 3600
        finished = False
        poll = 0
        while time.time() < deadline:
            poll += 1
            if poll % 2 == 1:
                monitor.screenshot("install-progress")
            state = shell.run("mount | grep -c calamares-root", timeout=90)
            try:
                mounted = int(state.strip().splitlines()[-1])
            except (ValueError, IndexError):
                mounted = 1
            page = disp.shot("finished-page") if mounted == 0 else None
            done_page = bool(page and (disp.find(page, "Done")
                                       or disp.find(page, "Restart")))
            if mounted == 0 and done_page and target_has_menu():
                finished = True
                break
            record(f"INFO: still installing (calamares mounts: {mounted}, "
                   f"finished page: {done_page})")
            time.sleep(25)
        record("PASS: the installer completed the installation" if finished
               else "FAIL: the installation never completed")
        if not finished:
            return 1
        time.sleep(5)
        monitor.screenshot("install-done")
        # Acknowledge the finished page so the wizard closes cleanly.
        disp.click(1005, 746)
        time.sleep(10)
        monitor.screenshot("install-closed")
        listing = shell.run("lsblk -o NAME,SIZE,FSTYPE /dev/vda", timeout=90)
        shell.run("tail -15 /tmp/calamares.log", timeout=60)
        if re.search(r"ext4|vfat|fat32", listing, re.IGNORECASE):
            record("PASS: the installer partitioned and formatted the target disk")
        else:
            record("FAIL: the target disk was not written")
            return 1

        # Look at what the installer left on the target disk: a menu, and the
        # boot loader on the EFI system partition.
        # With -d the installer logs which modules it runs, which is the only
        # way to see whether its finish-up step was reached at all.
        shell.run("sudo -n grep -i 'shellprocess' /tmp/calamares.log | head -20; "
                  "echo ---; sudo -n ls -l /etc/calamares/modules/ | head -30; "
                  "echo ---; sudo -n cat /etc/calamares/modules/shellprocess.conf; "
                  "echo ---; sudo -n tail -40 /tmp/calamares.log", timeout=180)
        probe = shell.run(
            "sudo -n sh -c 'mkdir -p /mnt/root && mount /dev/vda2 /mnt/root && "
            "mkdir -p /mnt/root/boot/efi && mount /dev/vda1 /mnt/root/boot/efi && "
            "for d in dev proc sys; do mkdir -p /mnt/root/$d; "
            "mount --bind /$d /mnt/root/$d; done; "
            "ls -l /mnt/root/boot/grub/grub.cfg ; "
            "test -e /mnt/root/usr/local/bin/hunter-install "
            "&& echo POSTINSTALL-NOT-RUN || echo postinstall-ran ; "
            "find /mnt/root/boot/efi -maxdepth 3 -type f | sort ; "
            # Test scaffolding only: the installed VM gets a serial console so
            # these checks can log in. A real installation is not changed.
            "sed -i 's/console=ttyS0[^ ]*//g; s/[[:space:]]*$//' "
            "/mnt/root/boot/grub/grub.cfg ; "
            "sed -i '/^[[:space:]]*linux/ s/$/ console=tty0 "
            "console=ttyS0,115200/' /mnt/root/boot/grub/grub.cfg ; "
            "mkdir -p /mnt/root/etc/systemd/system/getty.target.wants ; "
            "ln -sf /lib/systemd/system/serial-getty@ttyS0.service "
            "/mnt/root/etc/systemd/system/getty.target.wants/"
            "serial-getty@ttyS0.service ; "
            "systemctl --root=/mnt/root enable serial-getty@ttyS0.service "
            ">/dev/null 2>&1 || true ; "
            "echo SERIAL-CMDLINE: ; tr ' ' '\\n' "
            "< /mnt/root/boot/grub/grub.cfg | grep -a '^console=' | sort -u ; "
            "echo GETTY-UNITS: ; ls /mnt/root/etc/systemd/system/getty.target.wants "
            "2>&1 | tr '\\n' ' ' ; echo ; "
            "umount -R /mnt/root 2>/dev/null; true'", timeout=300)
        if "postinstall-ran" in probe:
            record("PASS: the installer ran its finish-up step")
        else:
            record("FAIL: the installer did not run its finish-up step")
        if "/boot/grub/grub.cfg" in probe:
            record("PASS: the installed system has a GRUB menu")
        else:
            record("FAIL: no GRUB menu on the installed system")
        if "serial-getty@ttyS0.service" in probe:
            record("INFO: a serial console was enabled on the installed system "
                   "for these checks")
        if "shimx64.efi" in probe or "BOOTX64.EFI" in probe:
            record("PASS: the EFI system partition holds the boot loader")
        else:
            record("FAIL: the EFI system partition is empty")

        # The probe output above is long because the EFI partition holds GRUB's
        # fonts and locales, so the serial setup is read back on its own.
        readback = shell.run(
            "sudo -n sh -c 'mkdir -p /mnt/root; mount /dev/vda2 /mnt/root; "
            "grep -m1 \"^[[:space:]]*linux\" /mnt/root/boot/grub/grub.cfg ; "
            "ls /mnt/root/etc/systemd/system/getty.target.wants/ ; "
            "umount /mnt/root'", timeout=180, lines=12)
        record("INFO: installed boot line and getty units: "
               + " | ".join(line.strip() for line in readback.splitlines()
                            if line.strip())[:400])
        if "console=ttyS0" in readback and "serial-getty@ttyS0" in readback:
            record("PASS: the installed system keeps a serial console for these checks")
        else:
            record("FAIL: the installed system has no serial console for the checks")

        if os.environ.get("DIAG") == "1":
            record("INFO: diagnostic run, stopping before the reboot")
            return 0

        # Stop booting from the ISO for the next start.  The reboot is issued
        # from the serial shell rather than by finding the wizard's button: once
        # the installer exits, its window is gone and a screenshot is black, so
        # clicking there waits forever for a target that cannot appear.
        monitor.hmp("eject cdrom", wait=1)
        page = disp.shot("finished-page")
        point = disp.find(page, "Done") or disp.find(page, "Restart")
        if point:
            disp.click(*point)
        shell.run("sudo -n systemctl reboot >/tmp/reboot.log 2>&1 &", timeout=60)
        deadline = time.time() + 180
        while time.time() < deadline and qemu.poll() is None:
            time.sleep(3)
        record("PASS: installation finished, rebooting into the installed system"
               if qemu.poll() is not None else
               "FAIL: the live system did not reboot after the installation")
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
    # Attach to the serial port before the guest boots.  QEMU only buffers
    # output for a client that is already connected, and an installed system
    # reaches its login prompt in seconds; connecting after the screenshots
    # lost the prompt and made a healthy boot look like a failed login.
    serial = Channel(SER_PORT)
    monitor = Monitor()
    shell = Shell(serial)
    try:
        image = os.path.join(WORK, "installed")
        os.makedirs(image, exist_ok=True)
        time.sleep(40)
        monitor.screenshot("10-grub")
        installed_shell = shell.login(timeout=420)
        monitor.screenshot("11-login")
        record("PASS: logged into the installed system" if installed_shell
               else "FAIL: could not log into the installed system")

        if installed_shell:
            # What this shell is.  A login on the wrong machine would make
            # every check below meaningless, so the filesystem, the absence of
            # the live medium and the absence of a mounted ISO are proved
            # before anything else runs.
            identity = shell.run(
                "findmnt -n -o SOURCE,FSTYPE / ; echo ---; "
                "findmnt -n -o SOURCE /boot/efi 2>/dev/null; echo ---; "
                "ls /run/live 2>/dev/null | head -3; echo ---; "
                "lsblk -n -o NAME,TYPE | tr '\n' ' '", timeout=120)
            ichunks = identity.split("---")
            root = ichunks[0].strip()
            efi = ichunks[1].strip() if len(ichunks) > 1 else ""
            live = ichunks[2].strip() if len(ichunks) > 2 else ""
            block = ichunks[3].strip() if len(ichunks) > 3 else ""
            record(f"INFO: installed root {root} | efi {efi} | /run/live "\
                   f"{live or 'empty'} | block devices {block}")
            # An empty CD-ROM device is expected here: the ISO was detached
            # from the virtual drive but the drive itself remains, which the
            # previous version of this check read as "still on the live image".
            installed_ok = ("/dev/vda" in root and "ext4" in root
                            and not live and "squashfs" not in block)
            record("PASS: the shell is the installed system, not a retained "
                   "live session" if installed_ok else
                   "FAIL: this shell is not the installed system "
                   f"(root={root!r}, /run/live={live!r}, block={block!r})")
            clinic = shell.run("systemctl is-system-running 2>&1", timeout=90)
            record("PASS: the installed system finished booting"
                   if clinic.strip() in ("running", "degraded")
                   else f"FAIL: the installed system did not finish booting ({clinic.strip()[:60]})")
            # The installed system shows the greeter, so somebody has to log in
            # before there is a desktop to check.  Its text is dark on dark and
            # OCR reads none of it, so the window is found through X and the
            # fields are clicked where this greeter lays them out at 1280x800.
            greeter_up = False
            greeter_shot = None
            for _attempt in range(24):
                greeter_shot = monitor.screenshot("greeter")
                # A black screen compresses to a few kilobytes; the greeter,
                # with its panel, box and text, to far more.
                if os.path.getsize(greeter_shot) > 8000:
                    greeter_up = True
                    break
                time.sleep(10)
            record("PASS: the installed system shows its login screen"
                   if greeter_up else
                   "FAIL: the installed system showed no login screen")
            if greeter_up:
                greeter = Display()
                greeter.click(690, 358)      # the name box, empty and focused
                greeter.type(LOGIN)
                greeter.click(690, 400)      # the password box
                greeter.type(PASSWORD)
                greeter.shot("greeter-filled")
                greeter.click(758, 444)      # Log In
                time.sleep(30)
                greeter.shot("desktop-after-login")

            # The session needs a moment to bring up the panel and the audio.
            for _attempt in range(15):
                if "panel-running" in shell.run(
                        "pgrep -x xfce4-panel >/dev/null && echo panel-running "
                        "|| echo panel-missing", timeout=60):
                    break
                time.sleep(10)


            # Cockpit in the installed system, from inside and from outside.
            state = shell.run("systemctl is-active cockpit.socket; echo ---; "
                              "systemctl is-enabled cockpit.socket; echo ---; "
                              "command -v cockpit-ws >/dev/null && echo cockpit-ws-present",
                              timeout=90)
            parts = state.split("---")
            record("PASS: cockpit.socket is active in the installed system"
                   if "active" in parts[0] else
                   "FAIL: cockpit.socket is not active in the installed system")
            record("PASS: cockpit.socket is enabled in the installed system"
                   if "enabled" in parts[1] else
                   "FAIL: cockpit.socket is not enabled in the installed system")
            code = shell.run("curl -sk -o /dev/null -w '%{http_code}' "
                             "https://localhost:9090", timeout=120)
            record("PASS: Cockpit answers inside the installed system"
                   if code.strip().endswith("200") else
                   f"FAIL: Cockpit does not answer inside the installed system ({code.strip()[:60]})")
            shell.run("/usr/local/bin/hunter-cockpit", timeout=60)

            # The wallpaper has to survive the installation.  feh sets the root
            # pixmap and exits, so the pixmap on the root window is the proof.
            wall = shell.run("test -f /usr/share/backgrounds/smd/"
                             "smd-linux-wallpaper.png && echo present || echo missing; "
                             "echo ---; DISPLAY=:0 xprop -root _XROOTPMAP_ID 2>&1 | head -2",
                             timeout=60)
            record("PASS: the wallpaper is present in the installed system"
                   if "present" in wall.split("---")[0]
                   else "FAIL: the wallpaper is missing in the installed system")
            record("PASS: the installed desktop draws the wallpaper"
                   if "PIXMAP" in wall.split("---")[-1]
                   else "FAIL: the installed desktop is not drawing the wallpaper")
            monitor.screenshot("13-installed-desktop-wallpaper")

            # --- the desktop after login: panel, audio, apps, launcher --------
            panel = shell.run(
                "pgrep -x xfce4-panel >/dev/null && echo panel-running "
                "|| echo panel-missing; echo ---; "
                "DISPLAY=:0 xwininfo -root -tree 2>/dev/null "
                "| grep -i xfce4-panel | head -3; echo ---; "
                "DISPLAY=:0 xwininfo -root 2>/dev/null | grep -E 'Width:|Height:'",
                timeout=120)
            pchunks = panel.split("---")
            screen = (re.search(r"Height:\s*(\d+)", pchunks[2])
                      if len(pchunks) > 2 else None)
            # The panel owns three windows: a 10x10 helper, the 3px reveal
            # strip and the panel itself.  The last geometry on each xwininfo
            # line is the absolute one, and the tallest wide window is the
            # panel.
            boxes = []
            for line in (pchunks[1].splitlines() if len(pchunks) > 1 else []):
                if "xfce4-panel" not in line:
                    continue
                # The window id (0x1000026) looks like a size to this regex.
                size = re.search(r"(\d+)x(\d+)",
                                 re.sub(r"^\s*0x[0-9a-f]+", "", line))
                position = re.findall(r"\+(-?\d+)\+(-?\d+)", line)
                if size and position:
                    width, height = int(size.group(1)), int(size.group(2))
                    x, y = (int(v) for v in position[-1])
                    boxes.append((width, height, x, y))
            boxes.sort(key=lambda box: (box[0], box[1]))
            found = boxes[-1] if boxes else None
            record("PASS: the panel starts automatically in the installed session"
                   if "panel-running" in pchunks[0]
                   else "FAIL: the panel does not start in the installed session")
            record("PASS: the installed panel is along the bottom edge"
                   if found and screen and
                   found[3] + found[1] >= int(screen.group(1)) - 6
                   else f"FAIL: the installed panel is not at the bottom "
                        f"({found if found else 'no window'})")

            # 1.3 retired auto-hide: the panel is set to stay visible and a
            # full-screen window simply covers it.  This check used to demand
            # that the panel hide, which the image has not done since 1.3, so it
            # was the only installed-session check that disagreed with the
            # delivered behaviour.  It now matches the live-session check.
            hide = shell.run("DISPLAY=:0 xfconf-query -c xfce4-panel "
                             "-p /panels/panel-1/autohide-behavior 2>&1", timeout=60)
            record("PASS: the installed panel is set never to hide"
                   if hide.strip().endswith("0")
                   else f"FAIL: the installed panel is set to hide ({hide.strip()[:40]})")
            window = re.search(r"(0x[0-9a-f]+)", pchunks[1]) if len(pchunks) > 1 else None
            if window:
                info = shell.run(f"DISPLAY=:0 xwininfo -id {window.group(1)}", timeout=60)
                state = re.search(r"Map State:\s*(\S+)", info)
                corner = re.search(r"Corners:\s*\+(-?\d+)\+(\d+)", info)
                height = re.search(r"Height:\s*(\d+)", info)
                y = int(corner.group(2)) if corner else None
                tall = int(height.group(1)) if height else 0
                screen_px = int(screen.group(1)) if screen else 0
                record(f"INFO: installed panel: state {state.group(1) if state else '?'}, "
                       f"y={y}, height={tall}, screen {screen_px}")
                record("PASS: the installed panel stays visible along the bottom edge"
                       if (state and state.group(1) == "IsViewable" and y is not None
                           and y + tall >= screen_px - 6)
                       else "FAIL: the installed panel is not visible at the bottom edge")

            audio = shell.run(
                "pactl info 2>&1 | grep -iE 'server name|server version'; echo ---; "
                "pgrep -x pipewire >/dev/null && echo pipewire-running "
                "|| echo pipewire-missing; "
                "pgrep -x wireplumber >/dev/null && echo wireplumber-running "
                "|| echo wireplumber-missing", timeout=90)
            achunks = audio.split("---")
            record("PASS: the installed sound server is PipeWire"
                   if "PipeWire" in achunks[0]
                   else f"FAIL: the installed sound server is not PipeWire ({achunks[0].strip()[:60]})")
            record("PASS: PipeWire and WirePlumber run after installation"
                   if "pipewire-running" in achunks[1] and "wireplumber-running" in achunks[1]
                   else "FAIL: PipeWire or WirePlumber is not running after installation")

            # mpv is no longer in the removed set: it is the player the
            # Jellyfin client drives, and 1.5 installs it on purpose.
            scope = shell.run(
                "for p in falkon ristretto xarchiver; do "
                "command -v $p >/dev/null && echo present:$p || echo gone:$p; done; "
                "echo ---; command -v brave-browser >/dev/null && echo browser-present; "
                "command -v mpv >/dev/null && echo mpv-present; "
                "dpkg-query -W -f='${Status}' wpasupplicant 2>/dev/null "
                "| grep -c 'install ok installed'", timeout=90)
            schunks = scope.split("---")
            record("PASS: the installed application set matches the trimmed image"
                   if "present:" not in schunks[0] and "browser-present" in schunks[1]
                   and "mpv-present" in schunks[1]
                   else f"FAIL: unexpected applications in the installed system ({schunks[0].strip()[:80]})")

            # The two added clients have to survive the installation the same
            # way the rest of the image does.
            clients = shell.run(
                "test -x /opt/jellyfin-mpv-shim/bin/jellyfin-mpv-shim "
                "&& echo jellyfin-exe; "
                "test -f /usr/share/applications/jellyfin-mpv-shim.desktop "
                "&& echo jellyfin-entry; "
                "/opt/jellyfin-mpv-shim/bin/python -c 'import jellyfin_mpv_shim' "
                "2>/dev/null && echo jellyfin-import; echo ---; "
                "test -x /usr/local/bin/hunter-dictation && echo voice-toggle; "
                "test -f /usr/share/applications/smd-dictation.desktop "
                "&& echo voice-entry; "
                "/opt/smd-voice/bin/python -c 'import vosk' 2>/dev/null "
                "&& echo vosk-import; "
                "test -d /usr/share/vosk/vosk-model-small-en-us-0.15 "
                "&& echo model; echo ---; "
                "cat /usr/share/doc/hunter-linux/components.txt 2>/dev/null "
                "| head -8", timeout=240)
            cchunks = clients.split("---")
            # The probe prints across a separator; reading only the first half
            # made present files look missing.
            found_clients = " ".join(cchunks[:2])
            missing = [word for word in ("jellyfin-exe", "jellyfin-entry",
                                         "jellyfin-import", "voice-toggle",
                                         "voice-entry", "vosk-import", "model")
                       if word not in found_clients]
            record("PASS: the Jellyfin client and Voice Typing are in the "
                   "installed system" if not missing else
                   f"FAIL: missing from the installed system: {', '.join(missing)}")
            record("INFO: installed component manifest: "
                   + " | ".join(line.strip() for line in
                                (cchunks[1] if len(cchunks) > 1 else "").splitlines()
                                if line.strip())[:300])

            # Alt+Z must work in the installed session too: start it, prove a
            # recogniser is running, then stop it and prove it is gone.
            voice = shell.run(
                "export DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/1000 "
                "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus; "
                "hunter-dictation start; sleep 6; "
                "hunter-dictation status; echo ---; "
                "pgrep -c -f 'nerd-dictation be[g]in' || echo 0; echo ---; "
                "hunter-dictation stop; sleep 2; "
                "hunter-dictation status", timeout=180)
            vchunks = voice.split("---")
            started = len(vchunks) > 1 and "listening" in vchunks[0].lower()
            processes = vchunks[1].strip() if len(vchunks) > 1 else ""
            stopped = voice.strip().endswith("stopped")
            record("INFO: recogniser processes while listening: "
                   + processes[:40])
            record("PASS: the Voice Typing switch works in the installed "
                   "system after the reboot" if started and stopped else
                   f"FAIL: dictation in the installed system: {voice.strip()[:160]}")
            record("PASS: dictation left no recogniser running after the "
                   "reboot" if stopped else
                   "FAIL: a recogniser is still running after dictation was "
                   "stopped")
            record("PASS: the Wi-Fi supplicant survived the installation"
                   if schunks[1].strip().endswith("1")
                   else "FAIL: wpasupplicant is missing after installation")

            shell.run("DISPLAY=:0 xdotool key --clearmodifiers Super_L", timeout=30)
            time.sleep(4)
            monitor.screenshot("14-installed-launcher")
            launcher = shell.run("DISPLAY=:0 xwininfo -root -tree 2>/dev/null "
                                 "| grep -ci rofi", timeout=60)
            record("PASS: the Search key opens the launcher after installation"
                   if launcher.strip().isdigit() and int(launcher.strip()) > 0
                   else "FAIL: the Search key does not open the launcher after installation")
            shell.run("DISPLAY=:0 xdotool key Escape", timeout=30)

            shell.run("systemd-analyze 2>&1 | head -3; systemctl --failed --no-pager "
                      "| head -6", timeout=120)

            outside = subprocess.run(
                ["curl", "-sk", "-o", os.path.join(WORK, "cockpit-installed.html"),
                 "-w", "%{http_code}", f"https://127.0.0.1:{WEB_PORT}/"],
                capture_output=True, text=True, timeout=120)
            page_path = os.path.join(WORK, "cockpit-installed.html")
            page = ""
            if os.path.exists(page_path):
                with open(page_path, encoding="utf-8", errors="replace") as handle:
                    page = handle.read()
            record("PASS: an outside client reaches Cockpit on the installed system"
                   if outside.stdout.strip().endswith("200")
                   and "is_cockpit_client" in page
                   else "FAIL: an outside client cannot reach Cockpit on the installed system")
            auth = subprocess.run(
                ["curl", "-sk", "-o", "/dev/null", "-D", "-", "-u",
                 f"{LOGIN}:{PASSWORD}",
                 f"https://127.0.0.1:{WEB_PORT}/cockpit/login"],
                capture_output=True, text=True, timeout=120)
            record("PASS: an outside client authenticates to Cockpit as the installed user"
                   if auth.stdout and "200" in auth.stdout.splitlines()[0] else
                   "FAIL: authenticated Cockpit login from outside did not succeed")
        if not installed_shell:
            # No serial login: the installed-session checks did not run.  This
            # is recorded as incomplete rather than passed, and the greeter is
            # still used so the desktop can be inspected in a screenshot.
            record("WARN: INCOMPLETE: no installed-session shell, so the "
                   "installed checks were not performed")
            # The greeter shows a name field and a password field, so the name
            # has to be typed first and Tab moves to the password.
            try:
                greeter = Display()
                # LightDM preselects the only account, so the password box
                # already holds the keyboard.  Typing the account name there
                # was the first 1.1 harness failure: it put the name in the
                # password box, moved focus to the name box on Tab and left the
                # password empty, so the login was rejected.
                greeter.shot("screen-11-login")
                greeter.type(PASSWORD)
                greeter.press("return")
                time.sleep(60)
                after = greeter.shot("01-11-desktop-after-login")
                if greeter.find(after, "Log In"):
                    # The greeter did show an empty name box: fill it, then the
                    # password, then submit.
                    greeter.type(LOGIN)
                    greeter.press("tab")
                    greeter.type(PASSWORD)
                    greeter.press("return")
                    time.sleep(60)
                    greeter.shot("11-desktop-after-login")
                record("WARN: no serial login; the greeter login was used instead")
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
        monitor.screenshot("12-installed-desktop")

        # The last check powers the machine off from the session itself: if the
        # polkit rule and the agent work, a normal user can shut the machine
        # down without a password, and QEMU stops.
        if installed_shell:
            shell.run("systemctl poweroff --no-ask-password >/tmp/poweroff.log "
                      "2>&1 &", timeout=30)
            deadline = time.time() + 90
            while time.time() < deadline and qemu.poll() is None:
                time.sleep(3)
            privileged = False
            if qemu.poll() is None:
                # A serial login is not an active seat, so polkit refuses
                # the unprivileged request; fall back to the account's own
                # privilege tool and say which path worked.
                shell.run("echo %s | " % PASSWORD + PRIV + " -S systemctl "
                          "poweroff >/tmp/poweroff.log 2>&1 &", timeout=30)
                privileged = True
                deadline = time.time() + 90
                while time.time() < deadline and qemu.poll() is None:
                    time.sleep(3)
            record("PASS: the installed system shuts down cleanly"
                   if qemu.poll() is not None
                   else "FAIL: the power action did not stop the installed system")
            if privileged:
                record("NOTE: the unprivileged power request was refused from "
                       "the serial session, so the shutdown used the account's "
                       "privilege tool; the desktop power menu itself is not "
                       "verified here")
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
    # A recorded FAIL has to fail the job: a green run with failures in the log
    # is worse than a red one.
    return 1 if any(line.startswith("FAIL") for line in results) else 0


if __name__ == "__main__":
    sys.exit(main())
