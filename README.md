# Hunter Linux 1.0

A small, general-purpose Debian 13 desktop distribution: **Xorg + i3 + the
XFCE4 panel**, two browsers, PipeWire audio, NetworkManager, and a Calamares
installer, all on one BIOS/UEFI hybrid live ISO.

This directory is the complete, reproducible build project. It builds with
Debian's own `live-build`; it does not depend on any external service.

**Build status:** the ISO has not been built yet. This project was produced on
a host without a Linux build environment, so the configuration is complete and
statically verified, but the image itself has never been compiled, booted or
measured. `Test-Report.md` states exactly what was and was not checked, and
how to finish the job.

```
 ./build.sh            # builds Hunter-Linux-v1.0-amd64.iso in this directory
```

---

## 1. What is in the box

| Layer | Choice |
|---|---|
| Base | Debian 13 "trixie", amd64, official repositories only |
| Kernel | Debian stable `linux-image-amd64` |
| Display | Xorg (X11), no Wayland, no compositor |
| Window manager | i3 (`i3-wm`), Super-key modifier, no i3bar |
| Panel / taskbar | `xfce4-panel` with whisker menu, task list, pager, systray, clock, volume, battery, power menu |
| File manager | Thunar (+ `thunar-volman`, `udisks2`, `gvfs`) |
| Terminal | `xfce4-terminal` |
| Editor | Mousepad |
| Browsers | Firefox ESR (primary), Falkon (secondary) |
| Network | NetworkManager + `nm-applet`, `iw`, `wireless-regdb`, BlueZ + Blueman |
| Audio | PipeWire + WirePlumber + `pavucontrol` |
| Media | mpv, Ristretto image viewer, Xarchiver |
| Installer | Calamares 3.3 |
| Live system | `live-boot` + `live-config`, autologin, no persistence |
| Boot | isolinux (BIOS/CSM) and GRUB EFI (UEFI), signed Debian shim when available |
| Build | Debian `live-build` 1:20250505, `debootstrap`, `xorriso`, squashfs + xz |

No GNOME, KDE, Cinnamon, MATE or full XFCE desktop is installed: only the
panel, its settings daemon, the power manager and the applications listed
above.

---

## 2. System requirements

| | Minimum | Comfortable |
|---|---|---|
| CPU | 64-bit x86, dual core | any 64-bit x86 from the last decade |
| RAM | 1.5 GB to install, 2 GB to use the desktop | 4 GB |
| Disk | 8 GB | 20 GB |
| Graphics | VGA capable of 1024x768; KMS drivers for Intel/AMD/NVIDIA | any |
| Boot | BIOS/CSM **or** UEFI (Secure Boot supported) | |

The live system can also run entirely from RAM (Advanced Boot Options ->
"entirely in RAM"), which needs about 2 GB.

---

## 3. Building the ISO

### Requirements

Either:

* Docker (any host OS) — `./build.sh` uses it automatically, and it is the
  recommended path; or
* a Debian 13 host with `live-build`, `debootstrap`, `xorriso`,
  `squashfs-tools` and root privileges.

Install those on Debian with:

```
apt-get install live-build debootstrap xorriso squashfs-tools
```

### Build

```
./build.sh              # Docker if available, otherwise native
./build.sh docker       # force Docker
./build.sh native       # force a native build (must be root, on Debian 13)
./build.sh clean        # delete chroot/, binary/, cache/ and any ISO
```

The build downloads roughly 1.5 GB of Debian packages and takes 20-60 minutes
depending on the machine and mirror. The result is:

```
Hunter-Linux-v1.0-amd64.iso          the bootable hybrid image
Hunter-Linux-v1.0-amd64.iso.sha256   its checksum
```

Use a different mirror without editing anything:

```
HUNTER_MIRROR=http://ftp.de.debian.org/debian/ ./build.sh
```

`lb build` writes intermediate files into `chroot/`, `binary/`, `cache/` and
`.build/`. Only `auto/config`, `config/` and `tools/` are source.

The release archive stores the script permissions (0755). If you unzip the
project with a tool that drops file modes, restore them before building:

```
chmod +x build.sh auto/config config/hooks/live/*.hook.chroot \
    tools/*.py config/includes.chroot/usr/local/bin/* \
    config/includes.chroot/usr/local/sbin/*
```

### Rebuilding after a change

`build.sh` always starts with `lb clean --purge`, so every build is from
scratch and reproducible from the configuration in this directory. Debian
security updates flow in automatically at build time because the package lists
name packages, not versions.

---

## 4. Writing the ISO to a USB device

The image is a hybrid ISO: it works when written with `dd`/Etcher/Rufus *and*
when simply copied to a FAT32 stick, but writing the raw image is the reliable
method (it preserves both boot paths).

Linux:

```
sudo dd if=Hunter-Linux-v1.0-amd64.iso of=/dev/sdX bs=4M status=progress oflag=sync
```

Use the whole device (`/dev/sdX`), never a partition (`/dev/sdX1`). This
destroys the contents of that device.

macOS:

```
diskutil list                                  # find the disk number
sudo dd if=Hunter-Linux-v1.0-amd64.iso of=/dev/rdiskN bs=4m
```

Windows: use [Rufus](https://rufus.ie) in **DD mode**, or balenaEtcher, and
select the ISO file.

---

## 5. Booting the live system

The boot menu offers:

| Entry | What it does |
|---|---|
| Start Hunter Linux Live | Boots the full desktop from the USB device. Nothing on the internal drive is touched. |
| Start Hunter Linux Live (Safe Graphics) | Same, with `nomodeset` and the VESA/framebuffer driver. Use it when the screen stays black. |
| Install Hunter Linux | Boots the same live system and opens the installer automatically. |
| Advanced Boot Options | Verbose boot, run entirely in RAM, check the medium's checksums, UEFI firmware settings, boot from the first hard disk. |

The menu counts down for 30 seconds and then starts the live system.

The live session logs in automatically as:

```
user / live
```

That account has passwordless `sudo` **in the live session only**. The
installed system has no autologin and no passwordless sudo.

The live system is fully usable offline; only browsing, updates and installing
extra software need the network.

---

## 6. Installing

Start the installer from the desktop icon **Install Hunter Linux**, the
application menu, or the "Install Hunter Linux" boot entry.

The installer asks for language, keyboard, disk, user account, and a summary
that must be confirmed before anything is written. It supports:

* automatic partitioning of a whole disk,
* manual partitioning ("Something else"),
* installing alongside an existing Windows installation,
* BIOS and UEFI installation, with LUKS full-disk encryption optional,
* time zone and keyboard selection,
* boot loader installation (GRUB on BIOS, signed shim + GRUB on UEFI).

**Nothing is written to any disk before the summary page is confirmed.**

The installed system is the live system: the installer unpacks the same
squashfs image, then removes the live-only pieces (live-boot, live-config,
the autologin rule, the live sudo rule, the installer itself), rebuilds the
initramfs and enables LightDM, NetworkManager, Bluetooth and zram.

Installation works without a network connection.

### After the first boot

Log in with the account you created, and refresh the package lists once:

```
sudo apt update
sudo apt full-upgrade
```

The image ships without APT indices (they cost about 60 MB) so that the ISO
stays small; Debian security and point-release repositories are already
configured.

---

## 7. Using the desktop

Super (the Windows key) is the modifier. A one-page reference is on the
desktop ("Keyboard Shortcuts") and on `Super+F1`.

| Shortcut | Action |
|---|---|
| `Super+D` | Application launcher |
| `Super+Tab` | Switch windows |
| `Super+Enter` | Terminal |
| `Super+E` | File manager |
| `Super+P` | Display settings (second monitor, resolution) |
| `Super+Q` (`Super+Shift+Q`) | Close the focused window |
| `Super+arrows` | Move the focus |
| `Super+Shift+arrows` | Move the window |
| `Super+1` … `Super+0` | Workspaces 1-10 |
| `Super+Shift+1` … `Super+Shift+0` | Move window to workspace |
| `Super+R` | Resize mode |
| `Super+Shift+E` | Power menu (lock, log out, restart, shut down) |
| `Super+Shift+L` | Lock the screen |
| Volume / brightness keys | Work as labelled |

The bottom panel holds the application menu, the window list, workspaces,
network and Bluetooth status, the clock (hover for the date), volume, battery
percentage on laptops, and the power menu.

---

## 8. Resources and performance

Design decisions that keep the system small, all of them deliberate:

* **No compositor.** i3 draws no shadows, transparency or animation; the GPU
  is idle when the desktop is idle.
* **No i3bar.** The XFCE panel is the only taskbar, so there is one status
  process instead of two.
* **No desktop environment.** No `xfce4-session`, `xfwm4`, GNOME or KDE
  stacks, no session daemon, no tracker/indexing service, no software centre,
  no printing stack, no office suite, no Avahi, no ModemManager.
* **APT recommends disabled.** Every installed package is named explicitly in
  `config/package-lists/`; nothing arrives as an optional recommendation.
* **zram instead of disk swap.** `zram-tools` gives a quarter of RAM as
  zstd-compressed swap, with `vm.swappiness=100` and `vm.page-cluster=0`.
  On a 2 GB machine this is the difference between usable and unusable.
  Disable with `sudo systemctl disable --now zramswap`.
* **No animations, no thumbnails.** GTK animations are off and no thumbnailer
  daemon is installed.
* **Filesystem:** `defaults,noatime` on installed systems.

Rough installed sizes (from the Debian package index, not measured on a built
image): Firefox ESR ~260 MB, Falkon with Qt6 WebEngine ~230 MB, Calamares with
Qt6 ~150 MB (removed at install time), the rest of the desktop ~200 MB. The
ISO is expected in the 1.4-1.8 GB range.

**Idle RAM has not been measured** — see `Test-Report.md`. The 400 MB target is
plausible for this stack but unproven; the report explains exactly how to
measure it.

---

## 9. Secure Boot

* **Live ISO:** supported when Debian's signed shim and signed GRUB are
  available (`--uefi-secure-boot auto`). live-build then boots via
  `shimx64.efi` → `grubx64.efi`, both signed by Debian and by Microsoft's UEFI
  CA. If the signed packages are not installable at build time, the ISO still
  builds and boots with Secure Boot **disabled**; the build log says so.
* **Installed system:** the installer uses Calamares' `sb-shim` mode and the
  same signed chain (`shim-signed`, `grub-efi-amd64-signed` are installed), so
  an installed system should keep booting with Secure Boot enabled.

Neither path has been tested on real firmware (see `Test-Report.md`). If a
machine refuses to boot, disable Secure Boot in the firmware settings; the
system works normally without it.

---

## 10. Known limitations

* **amd64 only.** A single x86-64 ISO cannot support ARM machines or every
  proprietary hardware configuration.
* **NVIDIA:** the open `nouveau` driver plus firmware is installed. The
  proprietary driver is not bundled; install `nvidia-driver` afterwards if you
  need full performance. Optimus laptops use the Intel/AMD GPU by default.
* **Falkon is not actually lighter than Firefox.** It pulls Qt6 WebEngine
  (~230 MB) and typically uses *more* memory than Firefox ESR for the same
  page. It is included because the brief asks for a second engine, not as a
  performance win.
* **No printing stack** (CUPS is ~40 MB of dependencies and several resident
  services). `sudo apt install cups system-config-printer` adds it.
* **No office suite, no PDF viewer, no screenshot tool, no archive password
  manager** — all installable with APT.
* **No persistence** for the live session: changes are lost on shutdown.
* **No suspend-on-lid guarantee** on all hardware; it depends on firmware and
  the backlight driver. xfce4-power-manager handles it where supported.
* **Mobile broadband (WWAN)** is not supported: ModemManager is deliberately
  not installed.
* **Emoji fonts and CJK fonts** are not included; install
  `fonts-noto-color-emoji` / `fonts-noto-cjk` if needed.
* The panel layout lives in `/etc/skel/.config/xfce4/...`, so changes apply to
  newly created accounts. Existing accounts keep their own copy.

---

## 11. Project layout

```
auto/config                     every live-build option, in one place
build.sh                        build driver (Docker or native)
Dockerfile                      Debian 13 build container
config/
  package-lists/                what gets installed, grouped by purpose
  bootloaders/
    isolinux/                   BIOS menu, style sheet, splash
    grub-pc/                    UEFI menu (GRUB), theme, splash
  hooks/live/                   chroot hooks: wiring, services, APT, cleanup
  includes.chroot/              files copied verbatim into the image
    etc/                        i3, XFCE panel/xsettings, LightDM, Calamares,
                                os-release, zram, APT sources, skel
    usr/local/bin/              hunter-session, hunter-power, hunter-install
    usr/local/sbin/             hunter-postinstall (runs inside the target)
    usr/share/                  backgrounds, icons, .desktop entries, docs
  includes.binary/README.txt    readme at the root of the ISO
tools/
  make-assets.py                regenerates every PNG (wallpaper, splashes, art)
  verify-project.py             static checks: YAML, XML, desktop files, shell,
                                package lists, Calamares cross-references
Test-Report.md                  build and test status, measurements, risks
```

### Common changes

* **Wallpaper / splashes / installer art:** edit `tools/make-assets.py`, run
  `python3 tools/make-assets.py`, rebuild.
* **Boot menu entries:** `config/bootloaders/isolinux/live.cfg.in` (BIOS) and
  `config/bootloaders/grub-pc/grub.cfg` (UEFI). Kernel command line lives in
  `auto/config` (`--bootappend-live`).
* **Packages:** add a line to a file in `config/package-lists/`. Check the name
  exists with `apt-cache show <package>` on a Debian 13 machine.
* **i3 bindings:** `config/includes.chroot/etc/skel/.config/i3/config`
  (copied to `/etc/i3/config` at build time by a hook).
* **Panel layout:** `config/includes.chroot/etc/skel/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml`.
* **Installer:** `config/includes.chroot/etc/calamares/`.

After any change, run the static checks:

```
python3 tools/verify-project.py
python3 tools/verify-project.py --live-build /usr/share/live/build
```

### License

Hunter Linux consists of configuration files, shell scripts and generated
artwork from this project, plus unmodified Debian packages. The configuration
and scripts are released under the MIT license; the included Debian software
keeps its own licenses.
