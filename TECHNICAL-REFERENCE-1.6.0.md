# SMD Linux 1.6.0 - technical reference

**Status: candidate.** This documents a built, tested image that has not yet
been accepted on Craig's hardware. Nothing here is a claim about a public
download; the files are in the delivery folder described in `README.md`.

---

## 1. Identity

| | |
| --- | --- |
| Distribution | SMD Linux 1.6.0 |
| Base | Debian 13 "trixie", amd64 |
| Image | `SMD-Linux-v1.6.0-amd64.iso`, 1,207,959,552 bytes (hybrid live ISO, BIOS + UEFI) |
| Installed packages | 944 (exact list in `PACKAGE-MANIFEST-1.6.0.txt`) |
| SHA-256 | `94a3856560ad99cc9674730939591b5e731afbad11542b30feee25e108a05141` |
| Build | Actions run `44550560639`, job "Build ISO" |
| Source commit | `41f79bf048e7522d74803d90a3d7c61010e10578` |
| Builder | `debian:trixie` container, `live-build` 1:20250505+deb13u1, Dockerfile in this project |
| Build inputs | this repository at that commit (source archive `SMD-Linux-Build-v1.6.0.zip`) |

## 2. Version handling (new in 1.6)

`VERSION` is the only place the release number is written. Everything that used
to repeat it now reads it:

| Reader | What it derives |
| --- | --- |
| `auto/config` | `--image-name "SMD-Linux-v${VERSION}"`, `--iso-volume "SMD_LINUX_${VOLUME}"`, `--iso-application` |
| `build.sh` | the ISO file name it reports and checks |
| `tools/make-assets.py` | the version printed on the installer logo, the wallpaper and the loading screen; `SMD_ASSET_ROOT` overrides the output tree |
| `tools/package-release.py` | the source archive name and the checksum file |
| every workflow | the ISO glob (`SMD-Linux-v*-amd64.iso`) |
| the build itself | a step regenerates the artwork from `VERSION` into the image before the squashfs is made |

The artwork is *regenerated* rather than compared byte for byte: two machines
with different zlib builds produce different PNG bytes for the same picture, so
a byte comparison rejects valid output and proves nothing about what the picture
says. 1.5.0 shipped an installer heading that read 1.5.0 above artwork that
still read 1.4.1; that class of defect is now impossible, because the picture is
drawn from the same string during the build.

`tools/verify-project.py` still checks the committed assets and the text files
that carry the version (`/etc/issue`, `/etc/os-release`, `/etc/lsb-release`,
Calamares branding, `README.txt` on the disc, the shortcut sheet) and fails if
any of them disagrees with `VERSION`.

## 3. Repositories and provenance

| Source | What comes from it |
| --- | --- |
| `deb.debian.org/debian` trixie - `main contrib non-free non-free-firmware` | the whole base system, desktop, installer, firmware, **plymouth** |
| `security.debian.org` trixie-security | security updates after installation |
| `brave-browser-apt-release.s3.brave.com` (`stable main`), signing key `brave-browser-archive-keyring.gpg` | Brave Browser |
| PyPI, pinned | `jellyfin-mpv-shim==3.3.0`, `vosk==0.3.45` |
| `github.com/ideasman42/nerd-dictation` at `41f3727` | the dictation engine, shipped in this repository |
| `alphacephei.com/vosk/models` | `vosk-model-small-en-us-0.15`, checksum-verified at build time |

Package indices are not shipped (`--apt-indices false`); the first `apt update`
after installation fetches them, and both the Brave source and its key stay so
Brave keeps updating. 1.6 adds no repository: plymouth is a Debian package.

## 4. Components and dependencies

| Component | Version | Installed by | Depends on |
| --- | --- | --- | --- |
| Jellyfin MPV Shim (client) | 3.3.0 | `0360-smd-clients.hook.chroot`, virtualenv `/opt/jellyfin-mpv-shim` | `mpv`, `libmpv2`, `python3-venv` |
| Vosk runtime | 0.3.45 | same hook, virtualenv `/opt/smd-voice` | `python3-venv` |
| English speech model | `vosk-model-small-en-us-0.15` | same hook, fetched and checksum-verified | - |
| nerd-dictation | commit `41f3727` | shipped in `config/includes.chroot/usr/share/nerd-dictation/` | `/opt/smd-voice`, `parec` (`pulseaudio-utils`), `xdotool` |
| Brave Browser | from Brave's repository | `0350-smd-browser.hook.chroot` | `libavcodec-extra` |
| VLC | Debian | package list | `libavcodec-extra` |
| zenity | Debian | package list | dialogs, including the one the tiling test opens |
| plymouth | Debian trixie | `hunter-base.list.chroot` | the initramfs; `initramfs-tools` regenerates it |

The two PyPI programs are installed into their own virtualenvs rather than into
the system interpreter: Debian marks `/usr/lib/python3` externally managed, and
a pip-installed library there would shadow the distribution's copy for every
other program on the machine. The build fails if either does not import, if
`/opt/jellyfin-mpv-shim/bin/jellyfin-mpv-shim` is missing, if `libmpv.so.2`
cannot actually be loaded, or if Vosk cannot load the model.

The client is a client only: no Jellyfin server, no saved server address, no
account, no credentials, no autostart entry. Its hardware decoding setting
(`hwdec=auto-safe`) is unchanged.

## 5. Installed layout

| Path | Purpose |
| --- | --- |
| `/opt/jellyfin-mpv-shim` | Jellyfin client virtualenv (`bin/jellyfin-mpv-shim`) |
| `/opt/smd-voice` | Vosk virtualenv (`bin/python3`) |
| `/usr/share/vosk/vosk-model-small-en-us-0.15` | offline English model |
| `/usr/share/nerd-dictation/nerd-dictation` | dictation engine, unmodified, mode 0755 |
| `/usr/share/doc/nerd-dictation/copyright` | engine and model provenance, licences, checksums |
| `/usr/local/bin/hunter-dictation` | the Alt+Z switch (`toggle`, `start`, `stop`, `status`) |
| `/usr/local/bin/hunter-workspaces` | **new in 1.6**: keeps the four numbered workspace buttons in step with i3, mode 0755 |
| `/usr/share/plymouth/themes/smd/` | **new in 1.6**: `smd.plymouth` and the script that draws the loading screen |
| `/usr/share/icons/hicolor/32x32/apps/smd-ws-{1..4}[-active].png` | **new in 1.6**: the eight button icons |
| `/etc/skel/.config/gtk-3.0/gtk.css` | **new in 1.6**: panel-only styling (flat background, hover tile, active accent) |
| `/etc/plymouth/plymouthd.conf` | **new in 1.6**: `Theme=smd`, `ShowDelay=0`, `DeviceTimeout=8` |
| `/usr/share/applications/jellyfin-mpv-shim.desktop` | Jellyfin menu entry |
| `/usr/share/applications/smd-dictation.desktop` | Voice Typing menu entry |
| `/etc/skel/.config/jellyfin-mpv-shim/mpv.conf` | `hwdec=auto-safe`, nothing else |
| `/usr/share/doc/hunter-linux/components.txt` | manifest written at build time: versions, model checksum, engine checksum |
| `/usr/share/doc/hunter-linux/shortcuts.html` | the shortcut sheet, on the desktop and Alt+F1 |

Voice Typing keeps its state in the user's own `~/.local/share/smd-dictation/`
(log, engine cookie). The workspace buttons keep theirs in
`~/.local/share/applications/smd-workspace-{1..4}.desktop` and the helper's log
in `~/.cache/smd/workspaces.log`, so a failure is on disk rather than swallowed.
Nothing is written to `/etc` by either, and no account name is hardcoded.

## 6. Panel, workspace buttons and loading screen (new in 1.6)

### Panel

| Setting | Value | Where |
| --- | --- | --- |
| `show-labels` (task list) | `false` - icons only, every window keeps its button | `xfce4-panel.xml`, plugin-2 |
| `show-tooltips` | `true` - the window title lives here now | same |
| Pinned launchers | Brave, then **File Manager** (`thunar.desktop`) | launcher plugins |
| Workspace previews | **removed**; four launcher buttons instead | plugin-9 (`launcher`) |
| Favourites | Browser, File Manager, Terminal, **Install SMD Linux** | plugin-1 (whisker menu) |
| Style | `~/.config/gtk-3.0/gtk.css`, panel scope only | no compositor, no shadows |

The window title used to take half the bar on this machine; with labels off the
task list stays a row of icons, and the tooltip still names the window. The
panel keeps its positions, the S menu, the spacers and the status plugins.

### The four numbered buttons

i3 discards an empty workspace when you leave it, so the old pager could only
ever show the workspaces that happened to hold a window. Four launcher buttons
(`smd-workspace-1..4.desktop`) always exist instead:

* `hunter-workspaces` writes the four `.desktop` files at session start and
  rewrites only the icons that changed;
* it subscribes to i3's `workspace` event stream - no polling - and reads the
  new workspace number **from the event itself**. It deliberately does not ask
  i3 for anything inside that loop: i3 answers requests and delivers events on
  the same socket, and a subscriber blocked on a reply can wedge the session;
* each file's `Exec` is `i3-msg -q "workspace number N"`, so clicking a button
  switches workspace without moving any window;
* `Alt+1` … `Alt+4` were already bound to the same thing (`$mod` is Mod1) and
  are unchanged, as is `Alt+Z` for voice typing.

### Loading screen

`plymouth` with a generated theme (`smd`): "SMD LINUX", the version, "SMD Linux
is loading…" and three dots that light in turn. `ShowDelay=0` means it appears
at once instead of after the default pause; `DeviceTimeout=8` gives a slow USB
stick time to bring the display up before plymouth falls back to its own text
screen. It runs from the initramfs, stops when the session starts
(`plymouth-quit-wait`), and is not a resident service: after boot `pgrep -x
plymouthd` finds nothing and the journal mentions plymouth zero times. Escape
shows the boot messages on either path.

## 7. Scripts, services and hooks

### Shipped programs (`/usr/local`)

| Program | Role |
| --- | --- |
| `hunter-autotile` | the balanced 1 / 2 / 3 / 4 window layout, driven over i3's IPC (unchanged in 1.6) |
| `hunter-workspaces` | **new in 1.6**: the four workspace buttons |
| `hunter-panel`, `hunter-applets` | start the panel, tray applets, polkit agent, PipeWire, tiling helper |
| `hunter-session` | the session entry point (`/usr/share/xsessions/hunter.desktop`) |
| `hunter-media`, `hunter-toprow` | Chromebook top-row dispatch |
| `hunter-volume`, `hunter-power`, `hunter-cockpit`, `hunter-install` | speaker level, power menu, Cockpit, installer launcher |
| `hunter-dictation` | Voice Typing switch (1.5) |
| `hunter-audio-hw`, `hunter-graphics`, `hunter-bootloader`, `hunter-postinstall` | boot-time hardware fixes, GRUB installation, post-install cleanup |

`hunter-workspaces` is started by the i3 configuration with `exec_always`, so it
comes back after `i3-msg restart` and starts in the live session and on an
installed system alike. It holds a lock per display, so a second copy exits
instead of rewriting the same files.

### Services (image)

`hunter-audio-hw.service`, `hunter-graphics.service`, plus enabled
`NetworkManager`, `bluetooth`, `lightdm`, `zramswap`, `systemd-timesyncd`,
`cockpit.socket`, `serial-getty@ttyS0` (skipped on machines without `ttyS0`),
and `plymouth-start`/`plymouth-quit-wait`, which systemd pulls in from the
initramfs and which finish and stop during boot.

### Build hooks (run in the chroot, in order)

| Hook | Does |
| --- | --- |
| `0100-hunter-desktop` | files, desktop entries, session wiring |
| `0200-hunter-services` | systemd enable/mask, user PipeWire units |
| `0300-hunter-apt` | writes Debian sources |
| `0350-smd-browser` | Brave repository and package |
| `0360-smd-clients` | Jellyfin client, Vosk, model, manifest |
| `0400-hunter-cleanup` | machine-id, caches, logs |

1.6 adds no hook: the artwork is regenerated by a build step before live-build
runs, and the plymouth theme is a file in `config/includes.chroot/`.

## 8. Browser

Brave from Brave's signed repository, two extensions installed through a
managed policy (`/etc/brave/policies/managed/10-smd-extensions.json`):

| Extension | ID |
| --- | --- |
| h264ify | `aleakchihdccplidncghkekgioiakgal` |
| Auto Quality for YouTube | `iaddfgegjgjelgkanamleadckkpnjpjc` |

`libavcodec-extra` supplies the codecs Brave and VLC use. 1.6 adds no third
extension and no blocker: there is no measurement that says one would help on
this machine, and it has little memory to spare.

## 9. Hardware settings

| Setting | Where | Applies when |
| --- | --- | --- |
| Intel TearFree | `/usr/share/smd/xorg/20-intel-tearfree.conf`, installed by `hunter-graphics` | only on Intel Bay Trail/ValleyView graphics (PCI 8086:0f31/0f32/0f33) with the Intel DDX present; removed elsewhere |
| PipeWire quantum | `/etc/pipewire/pipewire.conf.d/50-hunter-quantum.conf` | always |
| zram swap | `zram-tools` + `/etc/default/zramswap`, `/etc/sysctl.d/99-hunter-zram.conf` | always |
| Backlight for the `video` group | `/etc/udev/rules.d/90-smd-backlight.rules`; `hunter-postinstall` adds every human account to `video` | machines with `/sys/class/backlight` |
| Chromebook top row | `hunter-toprow` decides at session start; `hunter-media` dispatches F6-F10 | Chromebook keyboards |
| Speaker level 125 % | `hunter-volume`, once per session, internal speaker only | when the level is untouched |

## 10. Installer and boot loader

* Calamares 3.3 with branding `hunter` (product name and version read from the
  same `VERSION` string as everything else).
* Partitioning: erase disk, manual, or side-by-side with an existing Windows
  installation (`os-prober`). Nothing is written until the summary is confirmed.
* Boot loader: `hunter-bootloader` installs GRUB directly instead of relying on
  `grub-mkconfig`, which aborts in this image's chroot. UEFI gets Debian's
  signed shim + GRUB with `--no-nvram`, the removable-media fallback
  `/EFI/BOOT/BOOTX64.EFI`, and a best-effort firmware entry; BIOS gets GRUB in
  the MBR. The menu does not call `load_video`.
* `GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"` on the installed system, so the
  loading screen appears there too; the live medium sets its own kernel command
  line in `auto/config`.
* After unpacking, `hunter-postinstall` removes the live-session configuration,
  purges `live-boot`, `live-config`, `live-tools` and Calamares, regenerates the
  initramfs (which is what puts the plymouth theme into it for the installed
  system), removes the live account, re-enables the services, keeps the SMD
  session as LightDM's `user-session`, and adds human accounts to `video`.
  The purge is best-effort and does not stop the installation if APT refuses:
  the installed test found `/usr/bin/calamares` still on disk, with no menu
  entry, favourite or shortcut pointing at it. That is recorded rather than
  claimed otherwise.
* **New in 1.6:** it also removes "Install SMD Linux" from the installed
  system - the `.desktop` file and the favourites entry, in `/etc/skel` and in
  every existing home directory - so nothing points at an installer that is no
  longer there.

## 11. Branding, assets and licences

* Artwork is generated, not hand-drawn: `tools/make-assets.py` draws the
  wallpaper, boot splashes, logo, icon, installer welcome image, slideshow, the
  eight workspace button icons and the plymouth theme, from `VERSION`.
* Licence of this project: `LICENSE` in the source archive.
* Third-party licences: Debian packages keep their own copyright files
  (including plymouth, GPL-2.0-or-later); Brave is proprietary;
  `jellyfin-mpv-shim` is GPL-3.0-or-later (MIT for parts); `vosk` and the model
  are Apache-2.0; `nerd-dictation` is GPL-2.0-or-later and ships its headers and
  `/usr/share/doc/nerd-dictation/copyright` unchanged.

## 12. Speech model provenance

| | |
| --- | --- |
| Model | `vosk-model-small-en-us-0.15` |
| Source | `https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip` |
| Archive SHA-256 | `30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498` |
| Archive size | 41,205,931 bytes |
| Runtime | `vosk` 0.3.45 (PyPI wheel, bundles `libvosk`), Python 3.13 |
| Licence | Apache-2.0 |
| Engine | nerd-dictation `41f3727`, SHA-256 `9e782539337affde7c858eaf6f9b173d429a86434b6392ed11ad862de294d10d` |

The model is data, so it is fetched at build time and refused if the checksum
differs; the engine is source, so it is part of this repository and the archive.

## 13. Tests

| Job | What it proves |
| --- | --- |
| `build` | static checks, then the image builds; the artwork is regenerated from `VERSION`; the 1.6 files are present in the squashfs; no CRLF inside the image |
| `boot-test` (`mode=both`) | live boot under BIOS and UEFI: login, **what is on screen while the machine boots**, the panel (bottom edge, never hides, icons only, tooltips, Brave and File Manager pinned, no black surround), **four workspace buttons that start on 1 and follow a switch without moving a window**, the loading screen installed and handed over, audio, applications, tiling helper, locking |
| `tile-brave` (`helper=image`, uefi) | real Brave windows at **1366x768**: 1 / 2 / 3 / 4 layout, idle stability, fullscreen, focus and typing, an ordinary dialog, close and reopen, one helper, and the panel's strip accounted for |
| `installer-label` | the installer drawn on the image names 1.6.0 in text and in the artwork, with a screenshot |
| `voice-apps` | Alt+Z start/stop, a known recording dictated into a real text field, Ctrl+Z/X/A reaching the application, notification feedback, the Jellyfin client starting with its configuration and no server or autostart |
| `install-test` | install to a disposable disk, remove the ISO, boot the disk, log in on the installed system, prove it is the installed system, then check Cockpit, panel, icons-only buttons, the four workspace buttons, the wallpaper, audio, applications, the two clients, Voice Typing - and that **no installer favourite or shortcut is left** |
| `manifest` | the exact package list and component manifest read from the image |

Results, measurements and the exact list of what passed are in
`Test-Report.md`. A `FAIL` line fails its job; a check that could not run is
reported as incomplete, never as a pass. The boot test reports one failure, not
forty, when the guest stops answering its serial console, and it records how
long the tiling helper took to settle instead of assuming a fixed pause.

## 14. Known limitations

* **Hardware-only, not testable in a VM:** loudness and quality through the
  real speakers and headphones, playback and tearing on the Bay Trail panel,
  the printed top-row keys, Wi-Fi against real access points, suspend/lid and
  the battery percentage. These are Craig's to confirm on each candidate.
* **The loading screen is proven in QEMU**, on the standard VGA device with KMS.
  On a machine whose graphics cannot hand over early it falls back to
  plymouth's own text screen by design; that fallback has not been seen on real
  hardware.
* **Dictation accuracy** is not measured: the automated test proves the switch,
  the microphone, the recogniser and the typing path with a known recording,
  not how well the small English model understands a particular voice in a
  particular room. Stopping dictation took 2.5 s, 5.5 s and 15.3 s on three
  runs of the same image; the number is recorded rather than smoothed.
* **Jellyfin playback** is not exercised end to end: there is no server in the
  test environment, so the client is proven to install, start, open a window and
  carry its configuration, not to play a specific file from Craig's server.
* **1366x768** is emulated through the virtual VGA's EDID. It matches his panel
  geometry and panel height, but it is not his panel.
* **The Jellyfin client logs a missing PyGObject** (`No module named 'gi'`)
  at start-up: it runs in its own virtual environment, which does not
  contain `python3-gi`. Playback, the window and the mpv child process are
  unaffected, but the client's own tray icon and desktop notifications stay
  inactive. Adding `python3-gi` to the virtual environment is the fix for a
  later build; it is recorded here rather than silently accepted.
* **A wallpaper with broader appeal has no design yet.** The image has no
  wallpaper-changing action of its own (i3 plus feh, no desktop manager), and
  adding one is not worth the memory; 1.6 keeps the current artwork.
* **The offline HTML beginner guide** is still deferred.

## 15. Rebuilding and reusing

```
./build.sh              # Docker when available, native Debian 13 otherwise
./build.sh docker       # force the container
./build.sh clean        # remove build output
```

Change the release number in `VERSION` and everything follows. Everything else
needed is in the source archive: `auto/`, `config/`, `tools/`,
`.github/workflows/`, the Dockerfile and the vendored dictation engine. The
speech model and the two PyPI packages are fetched during the build from the
locations in section 3 and verified by checksum where a checksum is known.
Individual components can be lifted straight out of `config/includes.chroot/`
(for example `usr/local/bin/hunter-autotile`) or out of the ISO's squashfs.
