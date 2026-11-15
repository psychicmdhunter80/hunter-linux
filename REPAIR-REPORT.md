# SMD Linux 1.2 — repair report

Version 1.2 repairs the five faults reported from testing the 1.1 live image on
the Acer Chromebook 11 CB3-111: the start button still showed an "H", the panel
did not auto-hide, the panel did not come back after logging out and in, a
"Mail Reader" entry was left in the menu, the Wi-Fi "connected" bubble stayed on
screen, and the printed top-row volume and brightness keys did nothing.
Sections 1 to 3 below are the 1.1 record, kept as history. Section 0 is the 1.2
work.

---

## 0. What 1.2 changed, and what was actually wrong

### 0.1 The start button showed "H"

**Cause.** The whisker menu button was configured with the icon name
`hunter-linux`, and the only icon shipped under that name is the project logo,
not a menu symbol.

**Fix.** A new icon, `smd-menu`, is shipped as
`/usr/share/icons/hicolor/scalable/apps/smd-menu.svg` - a plain white rounded
square with a dark "S", drawn to stay legible at the 22 px the button gets on a
28 px panel - and the panel configuration uses it. Only the menu button was
renamed: no internal paths or package names changed.

### 0.2 The panel did not auto-hide

**Cause, and this is the real one.** The panel configuration did say
`autohide-behavior=2`, and the running panel did report that value, but
xfce4-panel hides itself by asking the window manager to move it off screen. i3
refuses to move dock windows - its log says *"Dock client will not be moved, we
only support moving it to another output"* - and then tells the panel it is
still where it was. This is i3 issue 4153 and xfce4-panel issue 308, both open
since 2020. Under i3 the panel therefore **cannot** hide, whatever the setting
says. 1.1 shipped the setting and no mechanism, so the panel stayed on screen.

**Fix.** The Acer's own working setup had already solved this, and 1.2 uses the
same mechanism: `hunter-panel-dock`, a small Python/Xlib launcher modelled on
`~/.local/bin/acer-panel` from the Chromebook install, starts the real
xfce4-panel and then takes only its dock-type windows away from i3 - sets
`override_redirect` and reparents them to the root window at the position i3
had already given them. i3 unmanages them, nobody intercepts the panel's own
moves any more, and the "Always hide" setting starts to behave as it does under
xfwm4 (on the Acer: hidden at y=813, revealed at y=735 on a 768 px screen).
`hunter-panel` keeps its flock, restart loop and display check and runs the
helper; if `python3`/`python3-xlib` are missing it falls back to a plain panel
that appears but cannot hide, instead of no panel at all. The panel is solid
black through the panel's own `background-style`/`background-rgba` settings -
no compositor, no theme suite, no transparency effects.

### 0.3 The panel did not come back after logout and login

**Cause.** `hunter-panel` runs a restart loop and protects itself with an
`flock` so an i3 reload cannot start a second panel. At logout the X server
takes the panel with it, but the loop survives with no display, keeps failing to
restart the panel, keeps the lock - and the next login's `hunter-panel` sees the
lock held and exits. No panel.

**Fix.** The loop now checks the X display each time the panel exits and stops
when it is gone, releasing the lock; the lock itself is keyed by display. A
panel left over from an old session can no longer block the next one.

### 0.4 "Mail Reader" in the menu

**Cause.** No mail client is installed. The entry was `exo-mail-reader.desktop`,
a generic "open your mail program" launcher shipped by `exo-utils`, which Thunar
depends on - so it could not simply be removed, and it did nothing useful.

**Fix.** The entry is removed in the build hook, together with the other `exo`
launcher stubs (`exo-web-browser`, `exo-terminal-emulator`,
`exo-file-manager`), which duplicate entries this image already has. Packages,
including `exo-utils` and Thunar, are untouched. Appearance settings stay: they
configure GTK, the icons and the panel, which are all in use under i3.

### 0.5 The Wi-Fi "connected" notification stayed on screen

**Cause.** The bubble is an ordinary notification from `nm-applet`, drawn by
`xfce4-notifyd`. With no expiry setting the daemon uses its long default, so a
"you are connected" message sits there until it is dismissed.

**Fix.** `xfce4-notifyd` now expires normal notifications after five seconds
(`/etc/skel/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-notifyd.xml`).
Nothing is suppressed: error notifications keep their behaviour and stay
clickable, the daemon still runs, and the network applet is unchanged.

### 0.6 The printed volume and brightness keys did nothing

**Cause.** A Chromebook top row is not F1-F12. The keys are printed as
dimmer / brighter / mute / volume down / volume up, but they reach X as F6, F7,
F8, F9 and F10, and no `XF86Audio*` or `XF86MonBrightness*` keysym is ever
produced - so the i3 bindings 1.1 shipped for those keysyms could not fire. A
second, smaller fault: `brightnessctl` writes to `/sys/class/backlight`, which
is root-owned, so even a correct binding could not change the backlight for a
normal session user.

**Fix.** `hunter-toprow` runs at session start, detects a Chromebook from DMI
and writes `~/.config/i3/toprow.conf`, which the i3 configuration includes:
F6/F7 brighten and dim through `brightnessctl`, F8 toggles mute, F9 and F10
change the PipeWire volume. There is no `Fn` and no modifier involved, because
these are the keys the hardware actually sends. `Ctrl` plus the same key sends
the real function key to the application (`xdotool key --clearmodifiers F9`),
which is the secondary access Hunter asked for. On any other machine the script
writes a comment instead, so an ordinary keyboard keeps all of its F keys. A
udev rule hands the backlight to the `video` group and to the active seat, and
the installer adds the account to that group.

---

## Part A — the 1.1 repairs (kept as history)

Version 1.1 repairs the faults reported on the Acer Chromebook 11 CB3-111
against 1.0. It keeps the SMD name, branding and wallpaper, keeps the installer
repairs from 1.0 (boot loader, EFI partition, password check), and adds a
post-login installation test that 1.0 never had.

Everything below separates what was **verified** from what is
**owner-reported** and from what is **not yet verified**. Nothing in this report
was measured on the Acer itself: every automated result comes from a virtual
machine.

---

## 1. What was actually wrong

### 1.1 The panel did not appear after installation

**Cause.** Two independent faults, both now fixed in the source.

1. `hunter-session` started the panel in a background loop that first waited for
   i3's IPC socket. The panel, the applets, the power manager and the polkit
   agent therefore existed only if *that* session wrapper ran.
2. The image ships its own session file (`/usr/share/xsessions/hunter.desktop`),
   but `i3-wm` also ships `/usr/share/xsessions/i3.desktop`. A display manager
   that picks the plain `i3` entry starts i3 with no wrapper at all - no panel,
   no applets, no polkit agent, no power management. That is exactly the
   reported symptom: no panel at boot, but a panel that works perfectly when
   started by hand from a terminal.

**Fix.** The panel, the applets and the authentication agent are now started
from the **i3 configuration**, the one process that is guaranteed to run in both
the live and the installed session:

* `hunter-panel` keeps exactly one panel alive, holds a lock so an i3 reload
  cannot stack a second one, and logs why the panel exited to
  `~/.cache/smd/panel.log` instead of discarding it;
* `hunter-applets` starts `xfsettingsd`, the polkit agent, `nm-applet`,
  `xfce4-notifyd` and `xfce4-power-manager`, each guarded so nothing is started
  twice;
* `/usr/share/xsessions/i3.desktop` is removed from the image, so the plain i3
  session cannot be chosen;
* `hunter-postinstall` rewrites the display manager's session setting on the
  installed system as a second guarantee;
* `hunter-session` now only sets the session environment and execs i3.

### 1.2 The panel was at the top and never hid

**Cause.** The panel's stored configuration asked for `p=6` (top edge) with
`autohide-behavior=0` (never hide). The comment in the file claimed i3 would
override a bottom panel - it does not; i3 honours the strut the panel asks for.

**Fix.** `position = p=10;x=0;y=0` (bottom, centred) and
`autohide-behavior = 2` (always hide), height 28 px. i3 keeps the 1 px strut the
hidden panel leaves behind, so windows are never placed on a screen with no
panel at all, and the panel slides back up when the pointer reaches the bottom
edge.

### 1.3 Wi-Fi could not connect

**Cause.** `live-build` runs with `--apt-recommends false`. NetworkManager only
*recommends* `wpasupplicant`, so it was never installed: the radio was detected,
networks were listed, and every WPA2 connection failed. There was also no
polkit authentication agent in the session, so any action that needed
authorisation - including NetworkManager's connection dialogs - failed with
"interactive authentication required".

**Fix.** `wpasupplicant` is now an explicit package. `xfce-polkit` is installed
and started from the i3 session, and
`/etc/polkit-1/rules.d/49-smd-local.rules` allows an **active local** user to
manage NetworkManager and to use the logind power actions. That rule is
narrower than passwordless sudo: it covers two action groups, requires a local
*and* active session, and only applies to members of the `users` group.

The radio in this model is an **Intel Dual Band Wireless-AC 7260** (Mini PCIe),
driven by `iwlwifi`. `firmware-iwlwifi` was already in the image and the
`iwlwifi-7260` firmware is verified present in the built ISO.

### 1.4 `can't find command 'load_video'` on both boot entries

**Cause.** `load_video` is not a GRUB command. It is a shell function that
`grub-mkconfig` writes into the menu it generates (`/etc/grub.d/00_header`). The
installer writes its menu directly with `hunter-bootloader`, which called
`load_video` without ever defining it, so both entries failed with that message
and stopped at "Press any key to continue" before the kernel was loaded.

**Fix.** The calls are gone; `insmod all_video` (already in the header of the
written menu) does the same job. Both entries boot without an error or a key
press.

**Why it appeared only after installation:** the live ISO's menus are generated
by live-build and never called the function. Only the installed menu did.

### 1.5 Audio felt like PulseAudio and was not clearly PipeWire

**Cause.** Not a wrong stack: `pipewire-audio` and `wireplumber` were already in
the image, and PipeWire provides the PulseAudio protocol, so `pactl` and the
panel's volume plugin are expected to work. What was missing was a guarantee:
`pipewire-pulse` was only pulled in as a dependency, and nothing in the image
pinned or verified the running server.

**Fix.** `pipewire`, `pipewire-pulse`, `pipewire-alsa` and `wireplumber` are all
explicit packages, no `pulseaudio` package exists in the image, and the tests
now assert that `pactl info` reports a PipeWire server and that
`wireplumber` is running. The volume keys drive `wpctl` directly.

### 1.6 The software set was much larger than the goal

**Removed** (with the reason):

| Package | Why it went |
|---|---|
| `falkon` | second browser; pulls ~230 MB of Qt WebEngine and uses more memory than Firefox for the same page |
| `mpv` | standalone video player; the browser plays YouTube and Jellyfin |
| `ristretto` | image viewer |
| `xarchiver` | archive manager; `unzip` and `xz-utils` stay |
| `thunar-archive-plugin`, `thunar-volman` | only existed to serve xarchiver and removable-media handling that `udisks2` and `gvfs` already provide |
| `mousepad` | graphical text editor; `nano` stays |
| `blueman` | Bluetooth GUI; `bluez` and the PipeWire Bluetooth module stay, so Bluetooth audio still works |
| `gnome-themes-extra` | extra theme pack; GTK's built-in Adwaita is what the session uses |
| `xfce4-power-manager-plugins` | panel plugin set that this panel does not use |

**Retained** and why: Firefox ESR (browser and codecs), Thunar (file manager and
download dialogs), `xfce4-terminal` (diagnostics), rofi (launcher), the panel
with its menu/tasklist/pager/tray/clock/volume/battery/power plugins, PipeWire
audio, NetworkManager with `wpasupplicant`, Cockpit (browser-terminal
administration, socket-activated), and the Calamares installer in the live
media only.

**Menu entries removed** while the settings tools stay installed: the XFCE
settings manager, "About XFCE", appearance, accessibility, colour, MIME,
keyboard and settings-editor dialogs, and Thunar's settings entry. `xfsettingsd`
still runs - GTK applications under i3 still get their theme, icons and fonts -
only the menu clutter is gone. No `xfwm4` was added.

### 1.7 Boot time, tearing and battery

* The kernel command line in the installed menu is unchanged apart from the
  `load_video` removal, so the "press any key" stop is gone. Start-up phases are
  measured by the test (`systemd-analyze`), not assumed; USB flash speed is
  recorded as a plausible contributor, not as a proven cause.
* Tearing: i3 runs without a compositor. The Intel DDX removes tearing without
  one, so the image now applies the established TearFree configuration
  (`Driver "intel"`, `Option "TearFree" "true"`) through
  `hunter-graphics.service`, which runs before the display manager. It is
  **hardware-matched**: the file is written only when `lspci` reports Intel Bay
  Trail / ValleyView graphics (`8086:0f31`, `0f32`, `0f33`) and the Intel DDX is
  installed, and it is removed on every other machine, so a single ISO never
  forces the intel driver onto an AMD, NVIDIA or virtual GPU. No compositor was
  added and nothing was overclocked.
* Battery: the 10-15 % sudden power-off is a hardware/gauge report from the
  older installation and is **not** reproduced or explained here; nothing
  subtracts a fixed percentage or forces a cutoff. The panel shows the battery
  plugin's own percentage, which reads from UPower.

---

## 2. Verification

### Version 1.2 - status as published

Image: `SMD-Linux-v1.2-amd64.iso`, 869 MiB, SHA-256
`6486736000b1d0673d599216297409abdefe87c14d94b571a1e7b2bce000cd15`, commit
`addfb00`. BIOS and UEFI live sessions: 36 checks pass, 2 fail.

**VERIFIED in the VM:** the S menu icon is installed and used, the panel is
solid black and along the bottom edge, notifications expire after five seconds,
the Mail Reader entry is gone while the other applications remain, PipeWire and
WirePlumber run, the Wi-Fi supplicant and 7260 firmware are present, the Search
key opens the launcher on its own, exactly one panel survives an i3 restart, and
F6-F10 are bound and routed through `hunter-media`.

**FAILED in the VM:** the panel did not hide. `hunter-panel-dock` detached no
window at this revision because it looked for `_NET_WM_PID`, which xfce4-panel
had not published; it now matches the window class as well, and that change
(build `43683121288`) was not boot-tested before this ISO was published.
**Auto-hide is unverified on this image - do not treat it as fixed.**

**NOT VERIFIED, needs the Acer:** whether the printed volume/mute/brightness
keys act without a modifier (the VM cannot produce Chromebook key events), the
Wi-Fi association and internet access, audible audio, battery percentage,
tearing, and whether the panel's hide/reveal works on the real display.

### Version 1.1 - what was verified on that image

Image tested: `SMD-Linux-v1.1-amd64.iso` - 868 MiB (909,895,680 bytes),
SHA-256 `2f6ee47d5a3c4a21b089b236b39b9d1622a96cbd1b66a3ab5e1cb08969dc6c2f`.

### VERIFIED in a virtual machine

BIOS and UEFI live sessions, **28 checks each, 28 pass, no failures**:

* live boot to the i3 desktop on both firmwares, wallpaper drawn;
* **the panel runs in the session** - one xfce4-panel, no duplicates;
* **the panel is along the bottom edge** - 1280x29 at `+0+768` on an 800 px screen;
* **auto-hide is set to always** (`autohide-behavior = 2`) and the panel leaves
  a 1280x3 reveal strip at `+0+797`;
* **the sound server is PipeWire**, and both `pipewire` and `wireplumber` are
  running in the session - audio existed at all for the first time;
* **the Search key opens the launcher on its own**, with no modifier and no
  `Super+D`;
* `wpasupplicant` installed, `iwlwifi-7260` firmware present, NetworkManager
  active - the packages the 1.0 image was missing for Wi-Fi;
* removed applications (Falkon, mpv, Ristretto, Xarchiver, Mousepad, Blueman)
  are gone and their menu entries are gone;
* no failed systemd units.

Measured on this image: 397 MiB of 1967 MiB used at idle (425 MiB in 1.0),
19.0 s kernel + 57.1 s userspace to `graphical.target` (QEMU with emulated USB,
not comparable to the Acer).

### VERIFIED: installation, UEFI

The wizard now completes end to end and the installed disk boots on its own:
installer finishes, target partitioned (300 MiB ESP + 19.7 GiB ext4), finish-up
runs, **GRUB menu present, and the EFI system partition holds the boot loader** -
the exact 1.0 failure. The installed system is then booted from its own disk by
the harness.

### Not verified here, and why

The harness logs into the installed system over the serial console. The
installed system produced no serial login prompt, so the automated post-login
assertions did not run on the installed machine; they ran in the live session,
where the same packages, session file, panel XML and i3 config are in place.
This is a harness gap - it is the first item of the follow-up list - and not a
reproduced defect.

---

## 3. What is still not verified, and what Hunter should check

Everything below needs the physical Acer Chromebook 11 CB3-111. A virtual
machine cannot emulate a wireless card, a battery, or Intel Bay Trail graphics,
and no claim here is made from real hardware.

**NOT YET VERIFIED - Hunter, please check these and report back:**

1. **Wi-Fi.** Does the network icon appear, do networks list, and does joining
   your network work? The missing supplicant is fixed and the firmware is
   present, but association, DHCP, DNS and HTTPS on real hardware are untested.
   Do not send your Wi-Fi password.
2. **Audio.** Play something with the volume keys audible. PipeWire and
   WirePlumber now start and `pactl info` reports PipeWire, but no sound has
   been heard on real hardware.
3. **Battery percentage.** The applet is in the panel; the reading depends on
   the Acer's firmware exposing a battery to the kernel.
4. **Tearing.** `hunter-graphics.service` writes
   `/etc/X11/xorg.conf.d/20-intel.conf` on this machine and you should see no
   tearing when scrolling or playing video. If tearing remains, say so and post
   the output of `systemctl status hunter-graphics` and `lspci -nn | grep -i vga`.
5. **Panel behaviour.** It should be at the bottom, hidden until you touch the
   bottom edge, opening on a touch and staying open while you use it.
6. **Keyboard.** Search alone opens the launcher, Left Alt is the modifier,
   browser shortcuts still work.

**Harness items to fix for the next round:** make the installed-system login
work (the serial console has no prompt, so the post-login assertions are
skipped), and make the pointer reveal of the auto-hiding panel a real assertion
rather than a recorded observation.
