# Hunter Linux 1.0 - Test Report

**Date:** 14 November 2026
**Version under test:** 1.0 (project sources, no ISO built)
**Build host available at the time of writing:** Windows 11 with MSYS2 bash.
No Linux kernel, no `debootstrap`, no root inside a Linux namespace, no
Docker, no WSL, no QEMU.

---

## 1. Summary - read this first

**No ISO was built and no live or installation test was performed.** The
build host cannot run `debootstrap`/`live-build`, so `Hunter-Linux-v1.0-amd64.iso`
does not exist in this delivery.

What *is* delivered is the complete build project, and it has been checked as
far as is possible without a Linux build host:

| Area | Status |
|---|---|
| Build configuration (`auto/config`) | 31 options, every one verified against live-build 1:20250505+deb13u1 |
| Package names (120) | Verified present in the trixie `main`, `contrib`, `non-free`, `non-free-firmware` indexes |
| Calamares modules (26) | Verified present in calamares 3.3.14-1; branding assets cross-checked |
| YAML / XML / desktop / shell syntax | All parsed or syntax-checked, no errors |
| Bootloader menus and splash assets | Present and cross-referenced |
| ISO build, boot, install, hardware, performance | **Not run** - see section 5 |

Every row above is a static check of the source files. None of it is a
substitute for building and booting the image.

---

## 2. Why the ISO could not be built here

Building a Debian live image is not a cross-compilation: `live-build` runs
`debootstrap` to install ~1,200 packages into a directory and then `chroot`s
into it to run their maintainer scripts. That requires:

* a Linux kernel (for `chroot`, `mount`, `mknod`),
* root privileges,
* `debootstrap`, `live-build`, `xorriso`, `mksquashfs`,
* ~10 GB of free disk and about 1.5 GB of package downloads.

The host provides none of the first four (MSYS2 is a POSIX emulation layer on
Windows: `chroot` and `mount` do not exist there), and installing WSL requires
administrator rights and a reboot of the machine, which is outside the scope of
this task. Consequently the ISO could not be produced, and anything that
depends on a built image (booting it, installing from it, measuring memory)
could not be tested.

The remaining work is a single command on a suitable host - section 6.

---

## 3. What was verified, and how

### 3.1 Package names against the real archive

All 120 package names in `config/package-lists/*.list.chroot` were checked
against the Packages indexes of Debian 13 (trixie) for amd64, all four archive
areas (69,908 packages):

```
result: 0 missing names
```

Four candidates were rejected during development and replaced:
`dmenu` (not in trixie - rofi is used instead), `garcon` (no such binary
package), `policykit-1` (superseded by `polkitd`), `firmware-rtlwifi` (does
not exist; `firmware-realtek` covers it).

### 3.2 live-build options

The 31 options in `auto/config` were checked against the option parser of
live-build 1:20250505+deb13u1 (the version in trixie, taken from the Debian
source package):

```
result: every option is supported
```

Two naming details were confirmed in the source rather than assumed:
`--binary-images` (not `--image-type`) and no `--union-filesystem` option
(overlay is the default).

### 3.3 Calamares integration

* The 26 modules used in `settings.conf` all exist in `calamares` 3.3.14-1
  (verified against the module directory of the Debian package).
* `efiBootLoader: "sb-shim"` is accepted by that build: the string is present
  in `bootloader/main.py`.
* `unpackfs.conf` uses `/run/live/medium/live/filesystem.squashfs`, the path
  Debian's own live installer uses.
* Every image named in `branding.desc` exists, and `show.qml` references only
  files that ship with it.

One real defect was found by these checks and fixed: the `displaymanager`
module was missing from the installer sequence.

### 3.4 Static project verification

`tools/verify-project.py` (run with PyYAML on the host) reports:

```
XML files parsed:        2
desktop entries checked: 6
shell scripts checked:   10
packages listed:         120
calamares modules used:  26
lb config options:       31   (all checked against live-build)
All static checks passed.
```

It checks: YAML syntax of every Calamares config and the branding file, XML
syntax of the xfconf files, `.desktop` required keys, `bash -n` on every shell
script and hook, package-list formatting and duplicates, the isolinux/GRUB
menus and their splash files, cross-references from scripts and desktop
entries to files that must exist in the image, and CRLF line endings.

### 3.5 Generated artwork

`tools/make-assets.py` produced 8 PNGs (wallpaper, two boot splashes, logo,
icon, welcome image, two slideshow slides). All were re-opened and their
headers and dimensions verified; the wallpaper and logo were visually
inspected.

---

## 4. Test matrix (all image-dependent tests)

| # | Test | Result | Reason |
|---|---|---|---|
| 1 | ISO builds without errors | **NOT RUN** | no Linux build host |
| 2 | ISO boots in a VM (BIOS) | **NOT RUN** | no ISO |
| 3 | ISO boots in a VM (UEFI) | **NOT RUN** | no ISO |
| 4 | Desktop loads, panel appears | **NOT RUN** | no image |
| 5 | Application menu opens | **NOT RUN** | no image |
| 6 | Firefox ESR starts | **NOT RUN** | no image |
| 7 | Falkon starts | **NOT RUN** | no image |
| 8 | Thunar opens, USB stick mounts | **NOT RUN** | no image |
| 9 | Terminal starts | **NOT RUN** | no image |
| 10 | NetworkManager connects (Ethernet/Wi-Fi) | **NOT RUN** | no image |
| 11 | PipeWire produces sound | **NOT RUN** | no image |
| 12 | Calamares launches from the icon and menu entry | **NOT RUN** | no image |
| 13 | Full installation (BIOS) | **NOT RUN** | no image |
| 14 | Full installation (UEFI) | **NOT RUN** | no image |
| 15 | Installed system boots without the ISO | **NOT RUN** | no image |
| 16 | Login screen appears after install | **NOT RUN** | no image |
| 17 | Panel and applications work after install | **NOT RUN** | no image |
| 18 | APT works after install | **NOT RUN** | no image |
| 19 | Idle RAM / CPU, disk usage, ISO size | **NOT RUN** | no image |
| 20 | Browser memory comparison | **NOT RUN** | no image |
| 21 | Physical hardware (Wi-Fi, GPU, battery, suspend) | **NOT RUN** | no image, no hardware |

No performance figure in this report is a measurement. The sizes quoted in
`README.md` section 8 come from the Debian package index and are estimates.

---

## 5. Deviations from the brief, and why

These are deliberate, documented choices rather than oversights:

1. **Application launcher: rofi, not dmenu.** `dmenu` is not in Debian 13
   (checked against the archive). rofi provides the same `-dmenu` interface,
   plus an application list and a window switcher, and is used for the launcher
   and the power menu.
2. **Panel power menu: a launcher icon running `hunter-power`, not the XFCE
   `actions` plugin.** The `actions` plugin calls `xfce4-session-logout`, which
   needs the XFCE session manager; that is part of the full XFCE desktop the
   brief excludes. `hunter-power` uses systemd-logind, which works under i3.
3. **`xfce4-panel` starts from `hunter-session`, not from the i3 config.** This
   keeps one panel process across i3 restarts and lets the panel wait for the
   window manager instead of quitting.
4. **No live persistence.** Not requested; adds a second boot-menu branch and
   a writable partition requirement.
5. **Falkon is included as requested, not as an optimisation.** It pulls Qt6
   WebEngine and is not lighter than Firefox ESR; the brief asks for its
   resource use to be *measured*, which is what an ISO build is for.

---

## 6. How to finish the testing (exact steps)

On a Debian 13 machine, or any machine with Docker:

```
cd hunter-linux
./build.sh docker          # or: sudo ./build.sh native
```

The build prints `lb build` output and ends with the ISO and its SHA-256.
Expect 20-60 minutes. Typical failures and their causes:

| Symptom | Cause |
|---|---|
| `Could not resolve` / 404 on a package | mirror or archive-area problem; retry with `HUNTER_MIRROR=...` |
| `E: Unable to locate package <name>` | a package was removed from trixie since this report; replace it in `config/package-lists/` |
| Calamares branding errors | a PNG in `etc/calamares/branding/hunter/` is missing; rerun `tools/make-assets.py` |
| No `isolinux/isolinux.bin` in `binary/` | the `isolinux` package was not installed in the chroot; check the build log |

### Boot tests (BIOS and UEFI)

```
# BIOS
qemu-system-x86_64 -m 2048 -enable-kvm -cdrom Hunter-Linux-v1.0-amd64.iso -boot d

# UEFI (Debian: apt install ovmf)
qemu-system-x86_64 -m 2048 -enable-kvm \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE.fd \
  -cdrom Hunter-Linux-v1.0-amd64.iso -boot d
```

Verify: the four menu entries are present and readable; "Start Hunter Linux
Live" reaches the i3 desktop with the panel at the bottom; `Super+D`, the
launcher, Thunar and the terminal work; both browsers start; the network icon
connects; `pavucontrol` shows a PipeWire sink; the desktop icon "Install
Hunter Linux" starts Calamares; the internal disk is untouched
(`lsblk` before/after).

### Installation test

Boot the ISO with a second, empty qcow2 disk attached:

```
qemu-img create -f qcow2 target.qcow2 12G
qemu-system-x86_64 -m 2048 -enable-kvm -cdrom Hunter-Linux-v1.0-amd64.iso \
  -drive file=target.qcow2,if=virtio -boot d
```

Install to the empty disk, then restart the same command with
`-boot c -drive file=target.qcow2,if=virtio` and without `-cdrom`. Verify the
login screen, the login, the panel, both browsers, `sudo apt update`, and:

```
systemctl status lightdm NetworkManager zramswap bluetooth
dpkg -l live-boot live-config calamares     # must all be absent
ls /etc/lightdm/lightdm.conf.d/             # 50-hunter-live.conf must be gone
```

### Performance measurements

```
# idle RAM and CPU after 5 minutes on the desktop, no applications open
free -m
top -bn1 | head -5

# per-process memory
ps -eo rss,comm --sort=-rss | head -15

# installed disk usage
df -h /

# ISO size
ls -lh Hunter-Linux-v1.0-amd64.iso

# browser comparison, same page, 60 seconds after load
firefox-esr https://en.wikipedia.org & sleep 60
ps -o rss= -C firefox-esr | awk '{s+=$1} END {print s/1024 " MB"}'
```

Record all of these in a table here before calling the build tested.

### Hardware

Wi-Fi, Bluetooth, audio, battery, brightness keys, suspend/resume and GPU
drivers can only be tested on real machines. Nothing in this report claims
they work.

---

## 7. Known risks in the untested build

Ordered by how likely they are to need a fix on the first real build:

1. **XFCE panel layout.** The plugin list and properties in
   `xfce4-panel.xml` are hand-written. If a plugin id or property name is
   wrong, the panel shows fewer plugins than intended (the desktop itself
   still works). Check `xfce4-panel -q` output and the panel's
   "Add new items" dialog first.
2. **Live autologin.** It relies on live-config's autologin plus a LightDM
   drop-in. If it fails, the greeter still accepts `user` / `live`.
3. **Secure Boot on the installed system.** `sb-shim` is configured and the
   signed packages are installed, but no firmware test was run. Fallback: set
   `efiBootLoader: "grub"` in `modules/bootloader.conf`, or disable Secure
   Boot.
4. **Calamares module sequence.** Configs were written against 3.3.14 and
   validated for module names, but an unexpected option name produces a
   warning, not a failed install. Watch `/var/log/calamares.log` during the
   first install.
5. **Package set resolution with `--apt-recommends false`.** Everything needed
   is named explicitly, but a missing runtime package would only appear at
   boot (for example a absent icon theme or GTK engine).
6. **ISO size.** Firefox ESR + Falkon/Qt6 WebEngine + Calamares/Qt6 put the
   image in the 1.4-1.8 GB range, larger than "ultra-lightweight" suggests.
   Removing Falkon and Calamares would cut roughly 400 MB; both are required
   by the brief.

---

## 8. Statement

The project in this archive is complete as a build project and is
self-consistent: every package name, option, module and file it references was
checked against the real Debian 13 archive, the real live-build source and the
real Calamares package.

It has **not** been built, booted, installed or measured. The distribution
should not be described as tested until the ISO has been built and the matrix
in section 4 has been filled in with actual results.
