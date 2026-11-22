# SMD Linux 1.7.1 - technical reference

**Status: implemented, image built, verified in the virtual machine; hardware
confirmation pending.** This document supersedes
`TECHNICAL-REFERENCE-1.7.0.md` for everything it covers; the 1.7.0 reference
and `../delivery-1.7.0/` stay as they are.

---

## 1. Identity

| | |
| --- | --- |
| Distribution | SMD Linux 1.7.1 |
| Base | Debian 13 "trixie", amd64 |
| Image | `SMD-Linux-v1.7.1-amd64.iso` (hybrid live ISO, BIOS + UEFI) |
| SHA-256 | `2f01b48302287b5c55a3780f6981ec58af75985afc5766204e4447763b4a96bb` |
| Build | Actions run `44978338982`, commit `1c03f74` |
| Builder | `debian:trixie` container, `live-build` 1:20250505+deb13u1, Dockerfile in this repository |
| Packages | 945 - 1.7.0's 944 plus `plymouth-label` (manifest run `44980929191`) |

The image contains source at commit `1c03f74`. Commits after it change only
test harnesses and documentation and are **not** part of the image; the
verified image is the one whose SHA-256 is above. Two earlier candidates,
`3b2183b4...` (run `44971257028`, no startup fix) and `54ae04bd...` (run
`44976421460`, panel only), are superseded and kept for the record.

## 2. What changed in 1.7.1

| Area | 1.7.0 | 1.7.1 |
| --- | --- | --- |
| Startup feedback | theme packaged, splashed nothing on screen | serial-console and label-plugin faults fixed; gradient, wording and activity dots visible, measured (section 3) |
| Panel workspaces | four buttons plus a text menu for 5-10 | ten buttons, each showing empty / occupied / current / both |
| Test rigor | "something was drawn while booting" | a splash-shaped frame is required, plus initramfs contents |
| Stability evidence | 20 seconds idle | repeated interaction cycles plus 15 minutes idle |
| Window policy | — | unchanged |

## 3. Boot, loading screen and installer configuration

### 3.1 Kernel command line

| Medium | Command line |
| --- | --- |
| Live (BIOS and UEFI) | `boot=live components quiet splash plymouth.ignore-serial-consoles console=ttyS0,115200 hostname=smd username=user autologin` |
| Live failsafe | `... nosplash nomodeset xforcevesa noapic noapm nodma nolapic nosmp vga=788 ...` |
| Installed | `GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"` |

`console=ttyS0` is deliberate: it is what lets the harness drive a login shell
and read kernel output. It is also what made Plymouth force its text renderer
onto the serial line, so `plymouth.ignore-serial-consoles` accompanies it on
the live line and on both installed GRUB entries. Every issued workspace command
carries `--no-auto-back-and-forth` because `workspace_auto_back_and_forth yes`
is set.

### 3.2 Plymouth

* Theme `smd` (`/usr/share/plymouth/themes/smd/`), module `script`, generated
  by `tools/make-assets.py` from `VERSION`: gradient background, `SMD LINUX`,
  `VERSION 1.7.1`, "SMD Linux is loading...", three dots cycling via
  `Plymouth.SetRefreshFunction`.
* **Two faults made the splash invisible, and both are fixed.** (1) Plymouth
  saw the serial console and forced the text `details` plugin onto it -
  `serial consoles detected, managing them with "details" forced` - so the
  graphical theme was never created. `plymouth.ignore-serial-consoles` now
  makes it log `ignoring all consoles but default console because explicitly
  told to`. (2) `plymouth-label` was absent, so `label-pango.so` could not load
  and every `Image.Text` drew nothing; the log said `Could not load module ...
  label-pango.so`. The package is now installed, and the hook refuses to build
  an initramfs without `label-pango.so` and `libpango-1.0.so`.
* Verified chain on the delivered image (diagnostic run `44980208086`, debug
  stream on the serial line): default console only, `/dev/dri/card0`,
  `renderers/drm.so`, `drm driver: bochs-drm`, preferred mode 1280x800,
  `Creating 1280x800 renderer head`, `executing script file`, then
  `label-pango: Text 'SMD LINUX' has dimensions 90x19`, `'VERSION 1.7.1'
  117x19`, `'SMD Linux is loading...' 178x19` and `'.' 5x19`.
* Measured on screen: the splash occupies about 63 s of the ~85 s pre-desktop
  interval under TCG (frames at 1 s intervals; the same gradient frame repeats
  from 85 s to 22 s before X). The boot test requires a bluish frame with at
  least 300 bright pixels, so the boot menu can no longer be mistaken for it.
* **Residual gap:** roughly 13 s between Plymouth quitting and the greeter
  drawing show black with a text cursor (frames at 19-6 s before X). That is
  LightDM startup, is measured, and is not hidden by the splash. Because the
  wording is drawn by the label plugin its size is fixed (19 px tall at
  1280x800); making it larger would require rendering the strings as images.
* `/etc/plymouth/plymouthd.conf`: `Theme=smd`, `ShowDelay=0`, `DeviceTimeout=8`.
* **`config/hooks/live/0390-smd-plymouth.hook.chroot`** (new in 1.7.1) runs
  after packages and artwork: `plymouth-set-default-theme smd`;
  `/etc/initramfs-tools/modules` listing `i915 amdgpu radeon nouveau virtio_gpu
  bochs`; `/etc/initramfs-tools/conf.d/smd-framebuffer.conf` with
  `FRAMEBUFFER=y`; `update-initramfs -u -k all`; then `lsinitramfs` on every
  produced initrd, failing the build if `plymouthd` or the theme is absent.
* Verified contents of the shipped initramfs (read out of the ISO with
  `lsinitramfs`, and independently by decompressing the image): 29 plymouth
  entries including `/bin/plymouth`, `/scripts/init-premount/plymouth`,
  `/scripts/init-bottom/plymouth`, `renderers/drm.so`, `script.so`,
  `usr/share/plymouth/themes/smd/smd.script`, and 631 display-driver entries.
* Read the initramfs correctly: it is an **uncompressed early cpio followed by
  a gzip payload**. Grepping the raw file for strings reports "absent" for
  everything in the payload - that mistake produced a wrong diagnosis during
  this release and is why the check above decompresses.
* Fallbacks kept: `Esc` shows boot messages, the failsafe entry uses
  `nosplash`, and `plymouth.enable=0` disables the graphical screen. No
  resident process: plymouth runs from the initramfs and quits at handover.

### 3.3 Installer

Calamares, branding in `/etc/calamares/branding/hunter/` (product name,
version, welcome and slide artwork, all drawn from `VERSION`). The installer
window is floated and centred by a `for_window` rule at 1010x700 so the wizard
is not squeezed into an i3 column. `hunter-postinstall` removes the installer
launcher and its favourite from the target, writes the bootloader, and leaves
no dangling shortcut.

## 4. Panel and workspace presentation

`xfce4-panel`, bottom edge, 28px, always visible, `plugin-ids` order: menu (1),
separator (10), Brave (11), File Manager (12), tasklist (2), expanding
separator (3), ten workspace launchers (`plugin-20`...`plugin-29`, one item
each), systray (5), clock (6), volume (7), battery (8), power (9). Plugin 13
(the 1.7.0 "5-10" control) and the first attempt's single multi-item launcher
(`plugin-4`) are gone.

**Why ten plugins, not ten items.** XFCE draws one button per launcher
plugin. Ten items in one plugin render as a single button plus an overflow
arrow, which is exactly what the 1.7.0 text menu looked like from a distance;
the first 1.7.1 build still showed one button for that reason. Ten single-item
plugins draw ten buttons, and the boot test now checks that all ten plugin ids
are loaded rather than counting item names (XFCE stores items under internal
ids, which made the earlier count read zero).

**Measured footprint.** On the running desktop the tiles are 24 px wide on a
32 px pitch: the ten occupy x=829-1140, **312 px**, at 1280 wide, and 320 px at
Craig's 1366x768. The earlier "roughly 220 px" was an estimate and was wrong.
Pinned Brave and File Manager, the task list, systray, clock, volume, battery
and power controls are unchanged and unclipped at 1280x800 and 1366x768.

`hunter-workspaces` (one subscriber, started from the i3 config) writes ten
`.desktop` files into `~/.local/share/applications/`, each `Exec=i3-msg -q
"workspace number N"`, and picks the icon from the state i3 reports:

| Icon | State |
| --- | --- |
| `smd-ws-N` | empty |
| `smd-ws-N-occupied` | holds a window |
| `smd-ws-N-active` | current workspace |
| `smd-ws-N-occupied-active` | current and holding a window |

Icons are generated (`tools/make-assets.py`, 32x32, four states per number),
not drawn by hand. The subscriber reacts to `workspace` and `window` events and
does nothing in between; it keeps the 1.7.0 rule that only a workspace
`focus`/`init` event moves the highlight.

## 5. Window policy (unchanged from 1.7.0)

Two tiled windows per workspace; first fills, second splits into equal
left/right halves; a third goes to the next empty workspace 1-10 (wrapping) and
that workspace is shown; a move into a full workspace, or exhaustion of all
ten, leaves the window floating with `smd-overflow`, centred, and a
notification; nothing is redistributed on close; `Ctrl+Alt+Left/Right` walk
occupied workspaces numerically with wrap; `Ctrl+Alt+Shift+Left/Right` move a
window; `Alt+1..0` and `Alt+Shift+1..0` stay. Dialogs float, the scratchpad
keeps its slot, fullscreen only toggles i3's own state. `hunter-autotile`,
`hunter-workspaces-nav` and the i3 config are unchanged in this release.

## 6. Desktop startup, wallpaper, audio

* i3 is the session (`exec` chain): `hunter-panel`, `hunter-applets` (which
  starts `hunter-autotile`), `hunter-workspaces`, `hunter-toprow`,
  `feh --no-fehbg --bg-fill /usr/share/backgrounds/smd/smd-linux-wallpaper.png`
  and `xrandr --auto`. The wallpaper is set once per session by `feh` and
  lives in the X root pixmap; there is no wallpaper daemon. 1.7.1 keeps the
  existing artwork (no new wallpaper; the owner has not chosen one).
* `hunter-audio-hw` runs before the display manager (live and installed) and
  corrects one mixer default: the Chromebook's `chtmax98090` codec ships its
  speaker at raw 10 (-14 dB). Only that codec is touched, and the UCM file is
  backed up first. PipeWire/`wpctl` handles volume keys.

## 7. Brave, Jellyfin, dictation

* Brave from Brave's signed repository. Managed policy
  `/etc/brave/policies/managed/10-smd-extensions.json` installs the two
  existing extensions (`aleakchihdccplidncghkekgioiakgal`,
  `iaddfgegjgjelgkanamleadckkpnjpjc`) with
  `installation_mode: normal_installed`. No extension was added or removed.
* Jellyfin MPV Shim in `/opt/jellyfin-mpv-shim` (not a Debian package); the
  known missing-PyGObject message at start-up is unchanged and does not affect
  playback or the window. End-to-end playback is not exercised: no server
  exists in the test environment.
* Offline dictation: nerd-dictation in `/opt/smd-voice` with the Vosk
  `vosk-model-small-en-us-0.15` model, checksum-verified at build time and
  refused if it differs. `Alt+Z` toggles; `Ctrl+Z/X/A` are left to the
  application.

## 8. Installation and rẹlevant paths

| Path | Purpose |
| --- | --- |
| `/usr/local/bin/hunter-autotile` | window rule |
| `/usr/local/bin/hunter-workspaces` | panel occupancy + highlight |
| `/usr/local/bin/hunter-workspaces-nav` | walk, move, menu, `state` |
| `/usr/local/sbin/hunter-bootloader` | writes the target's bootloader |
| `/usr/local/sbin/hunter-postinstall` | target cleanup, installer removal |
| `/usr/local/sbin/hunter-audio-hw` | codec mixer correction |
| `/usr/local/sbin/hunter-graphics` | graphics session preparation |
| `~/.cache/smd/autotile.log`, `~/.cache/smd/workspaces.log` | helper logs |
| `/usr/share/doc/hunter-linux/shortcuts.html` | one-page shortcut sheet |

## 9. Tests

| Job | What it proves |
| --- | --- |
| `build` | static checks; artwork regenerated from `VERSION`; the image builds; the initramfs hook verifies its own output |
| `boot-test` (`mode=both`) | live boot under BIOS and UEFI; a bluish splash frame with bright wording (run `44980323313`: 128 passed, 0 failed on each firmware); initramfs contains plymouth, theme and the label plugin; all ten workspace launcher plugins loaded; panel bottom edge; wallpaper; applications |
| `tile-brave` (`helper=image`) | the two-window policy with real Brave windows at 1366x768 |
| `tile-brave` with `stability=1` | repeated cycles plus 15 minutes of idle observation: focus, layout, helper count, self-triggered rearrangements, i3 responsiveness, helper CPU/memory |
| `install-test` | install to a disposable disk, detach the ISO, boot the disk, log in, check the installed desktop (run `44979098657`: 54 passed, 0 failed) |
| `voice-apps`, `installer-label`, `manifest` | dictation and the Jellyfin client; installer labelling; the package list |

A `FAIL` line fails its job. A check that could not run is reported as
incomplete, never as a pass.

## 10. Known limitations

* **Startup feedback is verified in the virtual machine only.** Gradient,
  wording and dots are drawn and were measured (section 3.2). Craig's panel is
  the only place that can confirm the same on his hardware; that confirmation
  is separate and still pending.
* **A residual black interval remains at handover:** about 13 s with a text
  cursor between Plymouth quitting and the greeter drawing. It is LightDM
  startup, measured, and not attributed to the theme.
* The splash wording is drawn by the label plugin at its fixed size (19 px
  tall at 1280x800): legible, but modest. Enlarging it would require rendering
  the strings as images, which this release does not do.
* The boot test's splash check is a colour and brightness measurement, not
  OCR: it proves bluish background plus bright content, not the exact glyphs.
* Hardware-only, untestable here: speaker/headphone loudness, panel tearing on
  the Bay Trail screen, printed top-row keys, Wi-Fi against real access points,
  suspend/lid, battery percentage, dictation accuracy in a room.
* 1366x768 is emulated through the virtual VGA's EDID; it matches the geometry
  and panel height, not the physical panel.
* Jellyfin playback needs a server that the test environment does not have.
* The wallpaper is unchanged; choosing new artwork is the owner's decision.

## 11. Rebuilding, reproducing, rolling back

```
./build.sh                      # -> SMD-Linux-v1.7.1-amd64.iso
python3 tools/verify-project.py  # static checks before any build
python3 tools/make-assets.py     # regenerate artwork from VERSION
```

Tests reuse one image: `gh workflow run boot-test.yml -f run_id=<build run>`,
`tile-brave.yml -f run_id=<build run> -f helper=image -f stability=1`,
`install-test.yml -f run_id=<build run>`. Rollback points, untouched:

| Tag | Contents |
| --- | --- |
| `pre-1.7.1-rollback` (`f2e8316`) | 1.7.0 exactly as delivered |
| `v1.7.0` | the delivered 1.7.0 release |
| `v1.6.0`, `v1.5.0` | earlier releases and their delivery folders |
