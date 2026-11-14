#!/usr/bin/env python3
"""Drive the Hunter Linux installer (Calamares) in a QEMU guest over VNC.

The guest desktop is reached through QEMU's VNC server.  Clicks are located by
OCR on a screenshot rather than hard-coded coordinates, so a change of theme or
resolution does not silently click the wrong button.  Every step saves a
screenshot, and a full OCR dump is written when a step fails, so the run is
diagnosable from the uploaded artefacts.

Usage:
    install-test.py <phase> <work-dir>
where <phase> is "install" (boot live, install to disk) or "verify"
(boot the disk that was just installed).
"""

import os
import subprocess
import sys
import time

from PIL import Image
from pytesseract import Output
import pytesseract
from vncdotool import api

VNC = os.environ.get("VNC_ADDRESS", "127.0.0.1::5901")
WORK = sys.argv[2] if len(sys.argv) > 2 else "install-out"
PASSWORD = os.environ.get("HUNTER_PASSWORD", "huntertest")
USERNAME = os.environ.get("HUNTER_USER", "hunter")


class Guest:
    def __init__(self):
        os.makedirs(WORK, exist_ok=True)
        self.client = api.connect(VNC, password=None)
        self.step = 0
        self.log = []

    # ---------------------------------------------------------------- output
    def note(self, message):
        line = f"[{time.strftime('%H:%M:%S')}] {message}"
        print(line, flush=True)
        self.log.append(line)

    def shot(self, name):
        self.step += 1
        path = os.path.join(WORK, f"{self.step:02d}-{name}.png")
        self.client.captureScreen(path)
        self.note(f"screenshot {os.path.basename(path)}")
        return path

    def dump_ocr(self, path, name):
        text = pytesseract.image_to_string(Image.open(path))
        out = os.path.join(WORK, f"ocr-{name}.txt")
        with open(out, "w", encoding="utf-8") as handle:
            handle.write(text)
        self.note(f"ocr dump {os.path.basename(out)}")

    # -------------------------------------------------------------- clicking
    def words(self, path):
        data = pytesseract.image_to_data(
            Image.open(path), output_type=Output.DICT
        )
        found = []
        for i, word in enumerate(data["text"]):
            word = (word or "").strip()
            if not word:
                continue
            try:
                conf = int(float(data["conf"][i]))
            except ValueError:
                continue
            if conf < 35:
                continue
            found.append(
                {
                    "text": word,
                    "x": data["left"][i],
                    "y": data["top"][i],
                    "w": data["width"][i],
                    "h": data["height"][i],
                    "conf": conf,
                }
            )
        return found

    @staticmethod
    def centroid(word):
        return (
            word["x"] + word["w"] // 2,
            word["y"] + word["h"] // 2,
        )

    def click(self, x, y):
        self.client.mouseMove(x, y)
        time.sleep(0.3)
        self.client.mousePress(1)
        time.sleep(0.6)

    def click_word(self, text, screenshot, dx=0, dy=0, region=None, timeout=20):
        """Click the centre of a word found by OCR, retrying while it settles."""
        deadline = time.time() + timeout
        target = text.lower()
        while time.time() < deadline:
            for word in self.words(screenshot):
                if target not in word["text"].lower():
                    continue
                x, y = self.centroid(word)
                if region and not region(x, y):
                    continue
                self.click(x + dx, y + dy)
                self.note(f"clicked '{word['text']}' at {x + dx},{y + dy}")
                return True
            time.sleep(2)
            screenshot = self.shot("retry-" + text.split()[0])
        self.dump_ocr(screenshot, "failed-" + text.split()[0])
        raise RuntimeError(f"could not find text: {text}")

    def has_text(self, text, screenshot):
        target = text.lower()
        return any(target in w["text"].lower() for w in self.words(screenshot))

    def wait_for(self, text, name, timeout=180):
        deadline = time.time() + timeout
        while time.time() < deadline:
            path = self.shot(name)
            if self.has_text(text, path):
                self.note(f"found '{text}'")
                return path
            time.sleep(5)
        self.dump_ocr(path, "timeout-" + name)
        raise RuntimeError(f"timed out waiting for: {text}")

    def key(self, name):
        self.client.keyPress(name)
        time.sleep(0.4)

    def type(self, text):
        self.client.typewrite(text)
        time.sleep(0.5)


def page_next(guest, label, screenshots):
    """Click Next/Continue on a wizard page and wait for the page to change."""
    path = guest.shot(label)
    guest.click_word("Next", path, region=lambda x, y: x > 400 and y > 400)
    time.sleep(2)
    screenshots.append(guest.shot(label + "-after"))


def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else "install"
    guest = Guest()
    shots = []

    if phase == "install":
        guest.note("waiting for the live desktop")
        guest.wait_for("HUNTER", "live-desktop", timeout=300)

        # Start the installer from a terminal so its debug output is captured.
        guest.key("meta_l-enter")
        time.sleep(6)
        guest.shot("terminal")
        guest.type("sudo calamares -d >/tmp/calamares.log 2>&1\n")
        guest.note("launched calamares")
        time.sleep(20)
        shots.append(guest.wait_for("Welcome", "welcome", timeout=180))

        # welcome -> locale
        page_next(guest, "welcome-next", shots)
        page_next(guest, "locale-next", shots)
        page_next(guest, "keyboard-next", shots)

        # partition: choose "Erase disk" explicitly
        path = guest.shot("partition")
        guest.click_word("Erase", path, dx=-18, dy=0)
        time.sleep(2)
        shots.append(guest.shot("partition-erase"))
        page_next(guest, "partition-next", shots)

        # users: fill in name, login and password
        path = guest.shot("users")
        guest.click_word("name", path, dy=0)
        guest.type("Hunter Tester")
        guest.key("tab")
        guest.key("tab")
        guest.type(PASSWORD)
        guest.key("tab")
        guest.type(PASSWORD)
        time.sleep(1)
        shots.append(guest.shot("users-filled"))
        page_next(guest, "users-next", shots)

        # summary -> install
        path = guest.wait_for("Summary", "summary", timeout=120)
        guest.click_word("Install", path, region=lambda x, y: y > 400)
        guest.note("installation started")
        time.sleep(10)
        shots.append(guest.shot("installing"))

        # the finished page appears when everything has been written
        path = guest.wait_for("Finish", "finished", timeout=2400)
        guest.dump_ocr(path, "finished")
        shots.append(path)

        # boot the installed system instead of the ISO on the next start
        subprocess.run(
            ["socat", "-", "UNIX-CONNECT:" + os.path.join(WORK, "monitor.sock")],
            input="eject cdrom\nquit\n",
            text=True,
            check=False,
        )
        guest.note("ejected the ISO and stopped the guest")
        return

    if phase == "verify":
        guest.note("waiting for the installed system")
        guest.wait_for("Hunter", "boot", timeout=300)
        shots.append(guest.shot("boot-early"))
        time.sleep(20)
        shots.append(guest.shot("boot-late"))
        guest.note("verification screenshots captured")
        return


if __name__ == "__main__":
    try:
        main()
    finally:
        try:
            api.disconnect()
        except Exception:
            pass
