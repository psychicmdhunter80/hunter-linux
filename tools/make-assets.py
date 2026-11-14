#!/usr/bin/env python3
"""Generate the SMD Linux 1.0 image assets.

Everything visual in SMD Linux is produced by this script, so the artwork
is reproducible from source with no drawing tools and no binary blobs:

  usr/share/backgrounds/hunter/wallpaper.png        desktop wallpaper
  isolinux/splash.png                               BIOS boot menu background
  grub-pc/splash.png                                UEFI boot menu background
  calamares branding: logo, icon, welcome, slides    installer artwork

Run from the project root:  python3 tools/make-assets.py
"""

import os
import struct
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROOT = os.path.join(ROOT, "config", "includes.chroot")
BRANDING = os.path.join(CHROOT, "etc", "calamares", "branding", "hunter")

# Palette - a neutral dark theme that stays readable on cheap panels.
BG_TOP = (20, 24, 29)
BG_BOTTOM = (32, 40, 50)
INK = (230, 230, 230)
MUTED = (150, 163, 178)
ACCENT = (61, 90, 128)
PANEL = (29, 35, 43)

# 5x7 bitmap font: each glyph is seven rows of five characters.
FONT = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01110"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "11011", "10001"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    "6": ("00110", "01000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00010", "01100"),
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
    ".": ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    ":": ("00000", "01100", "01100", "00000", "01100", "01100", "00000"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    "/": ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    "!": ("00100", "00100", "00100", "00100", "00100", "00000", "00100"),
}

GLYPH_W = 5
GLYPH_H = 7


class Canvas:
    def __init__(self, width, height, alpha=False):
        self.width = width
        self.height = height
        self.alpha = alpha
        self.channels = 4 if alpha else 3
        self.pixels = bytearray(width * height * self.channels)

    # -- painting ---------------------------------------------------------
    def _blend(self, index, colour, opacity):
        if opacity >= 1.0:
            self.pixels[index] = colour[0]
            self.pixels[index + 1] = colour[1]
            self.pixels[index + 2] = colour[2]
        else:
            for channel in range(3):
                base = self.pixels[index + channel]
                self.pixels[index + channel] = int(
                    base + (colour[channel] - base) * opacity + 0.5
                )
        if self.alpha:
            self.pixels[index + 3] = 255

    def fill(self, colour, opacity=1.0):
        row = bytearray()
        for _ in range(self.width):
            row += bytes(colour)
            if self.alpha:
                row += b"\xff"
        for y in range(self.height):
            start = y * self.width * self.channels
            if opacity >= 1.0:
                self.pixels[start:start + len(row)] = row
            else:
                for x in range(self.width):
                    self._blend(start + x * self.channels, colour, opacity)

    def gradient(self, top, bottom):
        span = max(self.height - 1, 1)
        for y in range(self.height):
            ratio = y / span
            colour = tuple(
                int(top[i] + (bottom[i] - top[i]) * ratio + 0.5) for i in range(3)
            )
            row = bytes(colour) * self.width
            if self.alpha:
                row = b"".join(row[i:i + 3] + b"\xff" for i in range(0, len(row), 3))
            start = y * self.width * self.channels
            self.pixels[start:start + len(row)] = row

    def rect(self, x, y, width, height, colour, opacity=1.0):
        x0 = max(0, int(x))
        y0 = max(0, int(y))
        x1 = min(self.width, int(x + width))
        y1 = min(self.height, int(y + height))
        for py in range(y0, y1):
            for px in range(x0, x1):
                self._blend((py * self.width + px) * self.channels, colour, opacity)

    def round_rect(self, x, y, width, height, radius, colour, opacity=1.0):
        x0, y0 = int(x), int(y)
        x1, y1 = int(x + width), int(y + height)
        for py in range(max(0, y0), min(self.height, y1)):
            for px in range(max(0, x0), min(self.width, x1)):
                dx = min(px - x0, x1 - 1 - px)
                dy = min(py - y0, y1 - 1 - py)
                if dx < radius and dy < radius:
                    if (radius - dx) ** 2 + (radius - dy) ** 2 > radius ** 2:
                        continue
                self._blend((py * self.width + px) * self.channels, colour, opacity)

    # -- text -------------------------------------------------------------
    @staticmethod
    def text_width(text, scale, tracking=1):
        return len(text) * (GLYPH_W + tracking) * scale - tracking * scale

    def text(self, x, y, text, scale, colour, opacity=1.0, tracking=1):
        cursor = x
        for char in text.upper():
            glyph = FONT.get(char)
            if glyph is None:
                cursor += (GLYPH_W + tracking) * scale
                continue
            for row_index, row in enumerate(glyph):
                for column_index, bit in enumerate(row):
                    if bit == "1":
                        self.rect(
                            cursor + column_index * scale,
                            y + row_index * scale,
                            scale,
                            scale,
                            colour,
                            opacity,
                        )
            cursor += (GLYPH_W + tracking) * scale

    def centered_text(self, y, text, scale, colour, opacity=1.0):
        width = self.text_width(text, scale)
        self.text((self.width - width) // 2, y, text, scale, colour, opacity)

    # -- logo -------------------------------------------------------------
    def mark(self, centre_x, centre_y, size, colour, opacity=1.0, underline=True):
        """The SMD Linux mark: the initial of the name with an accent rule."""
        scale = max(1, int(round(size / 7.0)))
        height = 7 * scale
        width = self.text_width("S", scale)
        left = int(round(centre_x - width / 2.0))
        top = int(round(centre_y - height / 2.0))
        self.text(left, top, "S", scale, colour, opacity)
        if underline:
            rule_y = top + height + max(2, int(round(size * 0.12)))
            self.rect(left, rule_y, width, max(2, int(round(size * 0.06))),
                      ACCENT, opacity)

    # -- output -----------------------------------------------------------
    def save(self, path):
        raw = bytearray()
        stride = self.width * self.channels
        for y in range(self.height):
            raw.append(0)
            raw += self.pixels[y * stride:(y + 1) * stride]

        colour_type = 6 if self.alpha else 2

        def chunk(tag, data):
            return (
                struct.pack(">I", len(data))
                + tag
                + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
            )

        png = b"\x89PNG\r\n\x1a\n"
        png += chunk(b"IHDR", struct.pack(">IIBBBBB", self.width, self.height, 8,
                                          colour_type, 0, 0, 0))
        png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        png += chunk(b"IEND", b"")

        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(png)
        print("  %-64s %6d x %-5d %6.1f kB"
              % (os.path.relpath(path, ROOT), self.width, self.height,
                 len(png) / 1024.0))


def wallpaper():
    canvas = Canvas(1920, 1080)
    canvas.gradient(BG_TOP, BG_BOTTOM)
    canvas.mark(1460, 520, 300, INK, 0.09)
    canvas.text(140, 830, "SMD LINUX", 8, INK, 0.92)
    canvas.text(142, 910, "1.0", 4, ACCENT, 0.95)
    canvas.rect(140, 960, 420, 4, ACCENT, 0.9)
    canvas.save(os.path.join(CHROOT, "usr", "share", "backgrounds", "hunter",
                             "wallpaper.png"))


def boot_splash(width, height, path):
    canvas = Canvas(width, height)
    canvas.gradient(BG_TOP, BG_BOTTOM)
    # The boot menu draws its own text, so the background stays quiet and the
    # mark sits out of the way in the bottom right corner.
    canvas.mark(int(width * 0.88), int(height * 0.84), int(height * 0.13),
                INK, 0.35)
    canvas.rect(int(width * 0.06), int(height * 0.90), int(width * 0.14),
                max(2, height // 220), ACCENT, 0.85)
    canvas.save(path)


def installer_logo(path):
    canvas = Canvas(480, 120, alpha=True)
    canvas.mark(52, 58, 64, INK, 1.0)
    canvas.text(112, 44, "SMD LINUX", 4, INK, 1.0)
    canvas.text(114, 82, "VERSION 1.0", 2, MUTED, 1.0)
    canvas.save(path)


def installer_icon(path):
    canvas = Canvas(256, 256, alpha=True)
    canvas.round_rect(0, 0, 256, 256, 48, PANEL, 1.0)
    canvas.mark(128, 116, 104, INK, 1.0)
    canvas.save(path)


def installer_welcome(path):
    canvas = Canvas(800, 300)
    canvas.fill(PANEL)
    canvas.mark(400, 108, 96, INK, 1.0)
    canvas.centered_text(196, "SMD LINUX", 5, INK, 1.0)
    canvas.centered_text(240, "1.0", 3, MUTED, 1.0)
    canvas.save(path)


def slide(path, headline, subline):
    canvas = Canvas(1280, 720)
    canvas.fill(PANEL)
    canvas.mark(190, 360, 170, INK, 0.9)
    canvas.text(300, 300, headline, 7, INK, 1.0)
    canvas.text(302, 390, subline, 3, MUTED, 1.0)
    canvas.rect(302, 450, 420, 4, ACCENT, 1.0)
    canvas.save(path)


def main():
    print("SMD Linux 1.0 - generating image assets")
    wallpaper()
    boot_splash(640, 480, os.path.join(ROOT, "config", "bootloaders", "isolinux",
                                       "splash.png"))
    boot_splash(800, 600, os.path.join(ROOT, "config", "bootloaders", "grub-pc",
                                       "splash.png"))
    installer_logo(os.path.join(BRANDING, "hunter-logo.png"))
    installer_icon(os.path.join(BRANDING, "hunter-icon.png"))
    installer_welcome(os.path.join(BRANDING, "hunter-welcome.png"))
    slide(os.path.join(BRANDING, "slide-1.png"), "LIGHTWEIGHT", "DEBIAN 13 - 400 MB OF RAM IS ENOUGH")
    slide(os.path.join(BRANDING, "slide-2.png"), "SIMPLE", "I3 WINDOW MANAGER - XFCE PANEL - TWO BROWSERS")
    print("done")


if __name__ == "__main__":
    main()
