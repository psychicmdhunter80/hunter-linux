# SMD Linux 1.1 — repair report

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

<!-- RESULTS -->

---

## 3. What is still not verified, and what Hunter should check

<!-- REMAINING -->
