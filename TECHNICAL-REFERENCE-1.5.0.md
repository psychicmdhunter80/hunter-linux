# SMD Linux 1.5.0 - technical reference

**Status: candidate.** This documents a built, tested image that has not yet
been accepted on Craig's hardware. Nothing here is a claim about a public
download; the files are in the delivery folder described in `README.md`.

---

## 1. Identity

| | |
| --- | --- |
| Distribution | SMD Linux 1.5.0 |
| Base | Debian 13 "trixie", amd64 |
| Image | `SMD-Linux-v1.5.0-amd64.iso` (hybrid live ISO, BIOS + UEFI) |
| SHA-256 | `74017efe2828d31c34cc3dab216e62f135746db27c6d7225ee7cb47953bb5ee8` |
| Build | Actions run `44192636526`, job "Build ISO", 7m53s |
| Source commit | `ad8679f5834fe7f23cb52dd6ebfec9cd0c397b63` |
| Builder | `debian:trixie` container, `live-build` 1:20250505+deb13u1, Dockerfile in this project |
| Build inputs | this repository at that commit (source archive `SMD-Linux-Build-v1.5.0.zip`) |

The image name, the installer branding, `/etc/issue`, `/etc/os-release`,
`/etc/lsb-release`, the GRUB theme title, the shortcut sheet, the README on the
disc and the artwork are all generated to one version string, and
`tools/verify-project.py` fails the build if any of them disagrees.

## 2. Repositories and provenance

| Source | What comes from it |
| --- | --- |
| `deb.debian.org/debian` trixie - `main contrib non-free non-free-firmware` | the whole base system, desktop, installer, firmware |
| `security.debian.org` trixie-security | security updates after installation |
| `brave-browser-apt-release.s3.brave.com` (`stable main`), signing key `brave-browser-archive-keyring.gpg` | Brave Browser 157.1.99.57 |
| PyPI, pinned | `jellyfin-mpv-shim==3.3.0`, `vosk==0.3.45` |
| `github.com/ideasman42/nerd-dictation` at `41f3727` | the dictation engine, shipped in this repository |
| `alphacephei.com/vosk/models` | `vosk-model-small-en-us-0.15`, checksum-verified at build time |

Package indices are not shipped (`--apt-indices false`); the first `apt update`
after installation fetches them, and both the Brave source and its key stay so
Brave keeps updating.

## 3. Components and dependencies

| Component | Version | Installed by | Depends on |
| --- | --- | --- | --- |
| Jellyfin MPV Shim (client) | 3.3.0 | `0360-smd-clients.hook.chroot`, virtualenv `/opt/jellyfin-mpv-shim` | `mpv`, `libmpv2`, `python3-venv` |
| Vosk runtime | 0.3.45 | same hook, virtualenv `/opt/smd-voice` | `python3-venv` |
| English speech model | `vosk-model-small-en-us-0.15` | same hook, fetched and checksum-verified | - |
| nerd-dictation | commit `41f3727` | shipped in `config/includes.chroot/usr/share/nerd-dictation/` | `/opt/smd-voice`, `parec` (`pulseaudio-utils`), `xdotool` |
| Brave Browser | from Brave's repository | `0350-smd-browser.hook.chroot` | `libavcodec-extra` |
| VLC | Debian | package list | `libavcodec-extra` |

The two PyPI programs are installed into their own virtualenvs rather than into
the system interpreter: Debian marks `/usr/lib/python3` externally managed, and
a pip-installed library there would shadow the distribution's copy for every
other program on the machine. The build fails if either does not import, if
`/opt/jellyfin-mpv-shim/bin/jellyfin-mpv-shim` is missing, if `libmpv.so.2`
cannot actually be loaded, or if Vosk cannot load the model.

The client is a client only: no Jellyfin server, no saved server address, no
account, no credentials, no autostart entry. Its hardware decoding setting
(`hwdec=auto-safe`) is unchanged.

## 4. Installed layout

| Path | Purpose |
| --- | --- |
| `/opt/jellyfin-mpv-shim` | Jellyfin client virtualenv (`bin/jellyfin-mpv-shim`) |
| `/opt/smd-voice` | Vosk virtualenv (`bin/python3`) |
| `/usr/share/vosk/vosk-model-small-en-us-0.15` | offline English model |
| `/usr/share/nerd-dictation/nerd-dictation` | dictation engine, unmodified, mode 0755 |
| `/usr/share/doc/nerd-dictation/copyright` | engine and model provenance, licences, checksums |
| `/usr/local/bin/hunter-dictation` | the Alt+Z switch (`toggle`, `start`, `stop`, `status`) |
| `/usr/share/applications/jellyfin-mpv-shim.desktop` | Jellyfin menu entry |
| `/usr/share/applications/smd-dictation.desktop` | Voice Typing menu entry |
| `/etc/skel/.config/jellyfin-mpv-shim/mpv.conf` | `hwdec=auto-safe`, nothing else |
| `/usr/share/doc/hunter-linux/components.txt` | manifest written at build time: versions, model checksum, engine checksum |
| `/usr/share/doc/hunter-linux/shortcuts.html` | the shortcut sheet, on the desktop and Alt+F1 |

Voice Typing keeps its state in the user's own `~/.local/share/smd-dictation/`
(log, engine cookie). Nothing is written to `/etc`, and no account name is
hardcoded anywhere in it.

## 5. Shortcuts

Navigation uses **Left Alt**; the **Search** key alone opens the launcher.
Full sheet: `shortcuts.html` (also Alt+F1).

| Keys | Action |
| --- | --- |
| `Search` / `Alt+D` | application launcher (rofi) |
| `Alt+Z` | **voice typing on and off** |
| `Alt+Enter` | terminal |
| `Alt+E` | file manager |
| `Alt+P` | display settings |
| `Alt+F1` | shortcut sheet |
| `Alt+Tab` | window switcher |
| `Alt+F4`, `Alt+Shift+Q` | close window |
| `Alt+F` | fullscreen |
| `Alt+H/J/K/L`, `Alt+Shift+H/J/K/L` | focus / move |
| `Alt+R` then H/J/K/L | resize mode |
| `Alt+Space` | tiling / floating |
| `Alt+S`, `Alt+W` | stacking, tabbed |
| `Alt+1..0`, `Alt+Shift+1..0` | workspaces |
| `Alt+Shift+E` | power menu |
| `Alt+Shift+X` | lock (i3lock) |
| `Ctrl+Z`, `Ctrl+X`, `Ctrl+A` | **not bound** - Undo, Cut, Select All stay the application's |

## 6. Scripts, services and hooks

### Shipped programs (`/usr/local`)

| Program | Role |
| --- | --- |
| `hunter-autotile` | the balanced 1 / 2 / 3 / 4 window layout, driven over i3's IPC |
| `hunter-panel`, `hunter-applets` | start the panel, tray applets, polkit agent, PipeWire, tiling helper |
| `hunter-session` | the session entry point (`/usr/share/xsessions/hunter.desktop`) |
| `hunter-media`, `hunter-toprow` | Chromebook top-row dispatch |
| `hunter-volume`, `hunter-power`, `hunter-cockpit`, `hunter-install` | speaker level, power menu, Cockpit, installer launcher |
| `hunter-dictation` | **new in 1.5**: Voice Typing switch |
| `hunter-audio-hw`, `hunter-graphics`, `hunter-bootloader`, `hunter-postinstall` | boot-time hardware fixes, GRUB installation, post-install cleanup |

### Services (image)

`hunter-audio-hw.service`, `hunter-graphics.service`, plus enabled
`NetworkManager`, `bluetooth`, `lightdm`, `zramswap`, `systemd-timesyncd`,
`cockpit.socket`, `serial-getty@ttyS0` (skipped on machines without `ttyS0`).

### Build hooks (run in the chroot, in order)

| Hook | Does |
| --- | --- |
| `0100-hunter-desktop` | files, desktop entries, session wiring |
| `0200-hunter-services` | systemd enable/mask, user PipeWire units |
| `0300-hunter-apt` | writes Debian sources |
| `0350-smd-browser` | Brave repository and package |
| `0360-smd-clients` | **new in 1.5**: Jellyfin client, Vosk, model, manifest |
| `0400-hunter-cleanup` | machine-id, caches, logs |

## 7. Browser

Brave from Brave's signed repository, two extensions installed through a
managed policy (`/etc/brave/policies/managed/10-smd-extensions.json`):

| Extension | ID |
| --- | --- |
| h264ify | `aleakchihdccplidncghkekgioiakgal` |
| Auto Quality for YouTube | `iaddfgegjgjelgkanamleadckkpnjpjc` |

`libavcodec-extra` supplies the codecs Brave and VLC use.

## 8. Hardware settings

| Setting | Where | Applies when |
| --- | --- | --- |
| Intel TearFree | `/usr/share/smd/xorg/20-intel-tearfree.conf`, installed by `hunter-graphics` | only on Intel Bay Trail/ValleyView graphics (PCI 8086:0f31/0f32/0f33) with the Intel DDX present; removed elsewhere |
| PipeWire quantum | `/etc/pipewire/pipewire.conf.d/50-hunter-quantum.conf` | always |
| zram swap | `zram-tools` + `/etc/default/zramswap`, `/etc/sysctl.d/99-hunter-zram.conf` | always |
| Backlight for the `video` group | `/etc/udev/rules.d/90-smd-backlight.rules`; `hunter-postinstall` adds every human account to `video` | machines with `/sys/class/backlight` |
| Chromebook top row | `hunter-toprow` decides at session start; `hunter-media` dispatches F6-F10 | Chromebook keyboards |
| Speaker level 125 % | `hunter-volume`, once per session, internal speaker only | when the level is untouched |

## 9. Installer and boot loader

* Calamares 3.3 with branding `hunter` (product name and version read from the
  same version string as everything else).
* Partitioning: erase disk, manual, or side-by-side with an existing Windows
  installation (`os-prober`). Nothing is written until the summary is confirmed.
* Boot loader: `hunter-bootloader` installs GRUB directly instead of relying on
  `grub-mkconfig`, which aborts in this image's chroot. UEFI gets Debian's
  signed shim + GRUB with `--no-nvram`, the removable-media fallback
  `/EFI/BOOT/BOOTX64.EFI`, and a best-effort firmware entry; BIOS gets GRUB in
  the MBR. The menu does not call `load_video`, which produced a "can't find
  command" stop on every boot of an installed system.
* After unpacking, `hunter-postinstall` removes the live-session configuration,
  purges `live-boot`, `live-config`, `live-tools` and Calamares, regenerates the
  initramfs, removes the live account, re-enables the services, keeps the SMD
  session as LightDM's `user-session`, and adds human accounts to `video`.

## 10. Branding, assets and licences

* Artwork is generated, not hand-drawn: `tools/make-assets.py` draws the
  wallpaper, boot splashes, logo, icon, installer welcome image and slideshow
  from the version in `auto/config`.
* Licence of this project: `LICENSE` in the source archive.
* Third-party licences: Debian packages keep their own copyright files;
  Brave is proprietary; `jellyfin-mpv-shim` is GPL-3.0-or-later (MIT for parts);
  `vosk` and the model are Apache-2.0; `nerd-dictation` is GPL-2.0-or-later and
  ships its headers and `/usr/share/doc/nerd-dictation/copyright` unchanged.

## 11. Speech model provenance

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

## 12. Tests

| Job | What it proves |
| --- | --- |
| `build` | static checks, then the image builds; the six new files are present in the squashfs; no CRLF inside the image |
| `boot-test` (`mode=both`) | live boot under BIOS and UEFI, branding, panel, audio, applications, tiling helper, locking |
| `tile-brave` (`helper=image`, uefi) | real Brave windows at **1366x768**: 1 / 2 / 3 / 4 layout, idle stability, fullscreen, focus and typing, an ordinary dialog, close and reopen, one helper |
| `installer-label` | the installer drawn on the image names 1.5.0, with a screenshot |
| `voice-apps` | Alt+Z start/stop, a known recording dictated into a real text field, Ctrl+Z/X/A reaching the application, notification feedback, the Jellyfin client starting with its configuration and no server or autostart |
| `install-test` | install to a disposable disk, remove the ISO, boot the disk, log in on the installed system, prove it is the installed system, then check Cockpit, panel, audio, applications, the two new clients and the Voice Typing switch |
| `manifest` | the exact package list and component manifest read from the image |

Results, measurements and the exact list of what passed are in
`Test-Report.md`. A `FAIL` line fails its job; a check that could not run is
reported as incomplete, never as a pass.

## 13. Known limitations

* **Hardware-only, not testable in a VM:** loudness and quality through the
  real speakers and headphones, playback and tearing on the Bay Trail panel,
  the printed top-row keys, Wi-Fi against real access points, suspend/lid and
  the battery percentage. These are Craig's to confirm on each candidate.
* **Dictation accuracy** is not measured: the automated test proves the switch,
  the microphone, the recogniser and the typing path with a known recording,
  not how well the small English model understands a particular voice in a
  particular room.
* **Jellyfin playback** is not exercised end to end: there is no server in the
  test environment, so the client is proven to install, start, open a window and
  carry its configuration, not to play a specific file from Craig's server.
* **1366x768** is emulated through the virtual VGA's EDID. It matches his panel
  geometry and panel height, but it is not his panel.
* The dialog check uses `xmessage` from `x11-utils`; it is a real window but a
  plain one, not a file chooser from a specific application.

## 14. Rebuilding and reusing

```
./build.sh              # Docker when available, native Debian 13 otherwise
./build.sh docker       # force the container
./build.sh clean        # remove build output
```

Everything needed is in the source archive: `auto/`, `config/`, `tools/`,
`.github/workflows/`, the Dockerfile and the vendored dictation engine. The
speech model and the two PyPI packages are fetched during the build from the
locations in section 2 and verified by checksum where a checksum is known.
Individual components can be lifted straight out of `config/includes.chroot/`
(for example `usr/local/bin/hunter-autotile`) or out of the ISO's squashfs.
