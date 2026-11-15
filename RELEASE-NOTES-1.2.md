# SMD Linux 1.2

The 1.2 test image for the Acer Chromebook 11 CB3-111. It keeps everything 1.1
repaired (Wi-Fi supplicant, PipeWire, panel startup, GRUB/ESP, TearFree) and
answers the faults found while testing 1.1's live session.

## What changed

* **Start button shows an "S".** A new `smd-menu` icon is installed and the
  panel uses it; nothing else was renamed.
* **The panel is black.** Solid `background-style` / `background-rgba` on the
  panel itself - no compositor, no theme suite.
* **The panel's own auto-hide is now reachable.** i3 refuses to move dock
  windows (i3 issue 4153), so xfce4-panel's "Always hide" could never work here.
  `hunter-panel-dock` uses the same method as the Acer's own `acer-panel`:
  it takes only the panel's dock windows away from i3 (override-redirect plus
  reparent to root), after which the panel hides and reveals itself.
  **This did not work at the published revision and is unverified - see below.**
* **The panel comes back after logout.** The panel watchdog used to survive the
  session, keep its lock with no display and leave the next login with no panel.
  It now stops when the display is gone, and its lock is per display.
* **Mail Reader is gone.** It was the `xfce4-mail-reader.desktop` stub from
  `exo-utils` - a launcher, not a mail client. Every other application stays.
* **The Wi-Fi "connected" bubble expires.** `xfce4-notifyd` now drops normal
  notifications after five seconds; errors keep their behaviour and stay
  clickable.
* **The printed top-row keys work without a modifier.** On a Chromebook those
  keys send F6-F10, never the XF86 media keysyms, which is why 1.1's bindings
  could not fire. Each key is now bound and dispatched: the printed action on a
  Chromebook, the real F key on any other keyboard, plus `Ctrl` + the key as the
  secondary route. The backlight is handed to the session user by a udev rule
  and the `video` group, so brightness can actually change.

## Verified in a virtual machine (BIOS and UEFI, 36 checks pass)

S menu icon in use, black panel, bottom edge, notification expiry, Mail Reader
absent with the other applications kept, PipeWire and WirePlumber running, Wi-Fi
supplicant and Intel 7260 firmware present, Search alone opens the launcher,
exactly one panel after an i3 restart, F6-F10 bound and dispatched.

## Failed or unverified - read this before testing

* **Panel auto-hide FAILED in the VM at this revision.** The detach helper found
  no window because xfce4-panel did not publish `_NET_WM_PID`; it now matches the
  window class as well, and that build had not been boot-tested when this ISO was
  published. Treat auto-hide as **unverified**, not fixed.
* **Volume-key check failed in the harness** because it could not read the
  volume before and after the key; the binding itself is present.
* **Not tested on the Acer:** real Wi-Fi association and browsing, audible audio,
  battery percentage, screen tearing, the actual top-row key events and
  brightness change, and whether the panel's hide/reveal looks right on the real
  display.

## Files

* `SMD-Linux-v1.2-amd64.iso` - 869 MiB (911,212,544 bytes), the bootable image.
* `SHA256SUMS` - checksums and sizes; `sha256sum -c SHA256SUMS`.
* `SMD-Linux-Build-v1.2.zip` - the source of this build.
* `SMD-Linux-v1.2-README.md`, `SMD-Linux-v1.2-Test-Report.md` - documentation.
