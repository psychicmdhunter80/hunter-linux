# SMD Linux 1.7.1 - technical reference

**Status: implemented, image built, verification in progress.** This document
supersedes `TECHNICAL-REFERENCE-1.7.0.md` for everything it covers; the 1.7.0
reference and `../delivery-1.7.0/` stay as they are.

---

## 1. Identity

| | |
| --- | --- |
| Distribution | SMD Linux 1.7.1 |
| Base | Debian 13 "trixie", amd64 |
| Image | `SMD-Linux-v1.7.1-amd64.iso`, 1,207,959,552 bytes (hybrid live ISO, BIOS + UEFI) |
| SHA-256 | `3b2183b430d314d80018667c4fe977298f59179cdf31b18c4f5e784cb0e66642` |
| Build | Actions run `44971257028` (job 137051321789), commit `1014414` |
| Builder | `debian:trixie` container, `live-build` 1:20250505+deb13u1, Dockerfile in this repository |
| Build inputs | this repository at `1014414` plus the workflow commit that follows it |
| Packages | 944, unchanged from 1.7.0 (no package added or removed) |

Documentation commits made after the build are **not** part of the image; the
image contains source at commit `1014414` only.

## 2. What changed in 1.7.1

| Area | 1.7.0 | 1.7.1 |
| --- | --- | --- |
| Startup feedback | theme installed, splashed nothing on screen | initramfs rebuilt with the theme, early display drivers and a framebuffer fallback; **still not visible in the VM** (section 3) |
| Panel workspaces | four buttons plus a text menu for 5-10 | ten buttons, each showing empty / occupied / current / both |
| Test rigor | "something was drawn while booting" | a splash-shaped frame is required, plus initramfs contents |
| Stability evidence | 20 seconds idle | repeated interaction cycles plus 15 minutes idle |
| Window policy | — | unchanged |

## 3. Boot, loading screen and installer configuration

### 3.1 Kernel command line

| Medium | Command line |
| --- | --- |
| Live (BIOS and UEFI) | `boot=live components quiet splash console=ttyS0,115200 hostname=smd username=user autologin` |
| Live failsafe | `... nosplash nomodeset xforcevesa noapic noapm nodma nolapic nosmp vga=788 ...` |
| Installed | `GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"` |

`console=ttyS0` is deliberate: it is what lets the harness drive a login shell
and read kernel output. Every issued workspace command carries
`--no-auto-back-and-forth` because `workspace_auto_back_and_forth yes` is set.

### 3.2 Plymouth

* Theme `smd` (`/usr/share/plymouth/themes/smd/`), module `script`, generated
  by `tools/make-assets.py` from `VERSION`: gradient background, `SMD LINUX`,
  `VERSION 1.7.1`, "SMD Linux is loading...", three dots cycling via
  `Plymouth.SetRefreshFunction`.
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
* What is **not** established: whether the splash reaches the screen. The VM
  records `mean 0-1` frames for the whole boot. Either QEMU's `screendump`
  misses the DRM scanout, or plymouth still falls back to text. Open.
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
separator (3), ten workspace launchers (4), systray (5), clock (6), volume (7),
battery (8), power (9). Plugin 13 (the 1.7.0 "5-10" control) is gone.

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
| `boot-test` (`mode=both`) | live boot under BIOS and UEFI; a splash-shaped frame (new, and failing); initramfs contains plymouth, theme and drivers; ten workspace buttons matching i3's state; panel bottom edge; wallpaper; applications |
| `tile-brave` (`helper=image`) | the two-window policy with real Brave windows at 1366x768 |
| `tile-brave` with `stability=1` | repeated cycles plus 15 minutes of idle observation: focus, layout, helper count, self-triggered rearrangements, i3 responsiveness, helper CPU/memory |
| `install-test` | install to a disposable disk, detach the ISO, boot the disk, log in, check the installed desktop |
| `voice-apps`, `installer-label`, `manifest` | dictation and the Jellyfin client; installer labelling; the package list |

A `FAIL` line fails its job. A check that could not run is reported as
incomplete, never as a pass.

## 10. Known limitations

* **Startup feedback is not verified.** The splash does not appear in the
  virtual machine and the cause is narrowed, not proven (section 3.2). Craig's
  panel is the only place that can settle it.
* The boot test's panel assertions compare the written icons with i3's state;
  their first run on this image failed on a parser defect (CRLF line endings on
  the serial console), which is fixed in the source and needs the rerun to be
  quoted as evidence.
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
