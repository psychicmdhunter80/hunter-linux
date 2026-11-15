# SMD Linux 1.1

A small, lightweight Debian 13 desktop distribution for low-power machines:
**Xorg + i3 + the XFCE4 panel**, one browser with working codecs, PipeWire
audio, NetworkManager with Wi-Fi, and a Calamares installer, all on one
BIOS/UEFI hybrid live ISO.

This directory is the complete, reproducible build project. It builds with
Debian's own `live-build` on GitHub Actions and does not depend on any external
service.

**Version 1.1** repairs the faults reported on the Acer Chromebook 11 CB3-111:
Wi-Fi (missing `wpasupplicant`), the panel that never started after installation,
the `load_video` error on both boot entries, PipeWire being pinned explicitly,
and a much smaller application set. The panel is now at the bottom edge and
auto-hides, the Search key opens the launcher on its own, and **Left Alt** is the
modifier for everything else. Details, root causes and what is still unverified
are in `REPAIR-REPORT.md`; measurements are in `Test-Report.md`.

```
 ./build.sh            # builds SMD-Linux-v1.1-amd64.iso in this directory
```

---

## 1. What is in the box

| Layer | Choice |
|---|---|
| Base | Debian 13 "trixie", amd64, official repositories only |
| Kernel | Debian stable `linux-image-amd64` |
| Display | Xorg (X11), no Wayland, no compositor |
| Window manager | i3 (`i3-wm`), **Left Alt** modifier, no i3bar; the **Search** key alone opens the launcher |
| Panel / taskbar | `xfce4-panel` on the **bottom edge, auto-hiding**, with whisker menu, task list, pager, systray, clock, volume, battery, power menu |
| File manager | Thunar (+ `udisks2`, `gvfs`) |
| Terminal | `xfce4-terminal` |
| Editor | `nano` (console); no graphical editor |
| Browser | Firefox ESR, with the full audio/video codec set |
| Network | NetworkManager + `nm-applet` + `wpasupplicant`, `iw`, `wireless-regdb`, BlueZ (audio only, no Bluetooth GUI) |
| Audio | PipeWire + `pipewire-pulse` + WirePlumber + `pavucontrol` (no PulseAudio daemon) |
| Authentication agent | `xfce-polkit`, started with the session |
| Installer | Calamares 3.3 |
| Remote administration | Cockpit (`cockpit`, `cockpit-system`) on port 9090, enabled in the live session and in the installed system |
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
SMD-Linux-v1.1-amd64.iso          the bootable hybrid image
SMD-Linux-v1.1-amd64.iso.sha256   its checksum
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
sudo dd if=SMD-Linux-v1.1-amd64.iso of=/dev/sdX bs=4M status=progress oflag=sync
```

Use the whole device (`/dev/sdX`), never a partition (`/dev/sdX1`). This
destroys the contents of that device.

macOS:

```
diskutil list                                  # find the disk number
sudo dd if=SMD-Linux-v1.1-amd64.iso of=/dev/rdiskN bs=4m
```

Windows: use [Rufus](https://rufus.ie) in **DD mode**, or balenaEtcher, and
select the ISO file.

---

## 5. Booting the live system

The boot menu offers:

| Entry | What it does |
|---|---|
| Start SMD Linux Live | Boots the full desktop from the USB device. Nothing on the internal drive is touched. |
| Start SMD Linux Live (Safe Graphics) | Same, with `nomodeset` and the VESA/framebuffer driver. Use it when the screen stays black. |
| Install SMD Linux | Boots the same live system and opens the installer automatically. |
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

Start the installer from the desktop icon **Install SMD Linux**, the
application menu, or the "Install SMD Linux" boot entry.

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

The **Search** key (where Caps Lock sits on this Chromebook; the Windows key on
other keyboards) opens the application menu **on its own**. Every other shortcut
uses **Left Alt**, so the browser keeps `Ctrl` and `Alt`+`Left/Right` for
itself. A one-page reference is on the desktop ("Keyboard Shortcuts") and on
`Alt+F1`.

| Shortcut | Action |
|---|---|
| `Search` alone | Application launcher |
| `Alt+D` | Application launcher (same thing, as a combination) |
| `Alt+Tab` | Switch windows |
| `Alt+Enter` | Terminal |
| `Alt+E` | File manager |
| `Alt+P` | Display settings (second monitor, resolution) |
| `Alt+F4`, `Alt+Shift+Q` | Close the focused window |
| `Alt+H` `J` `K` `L` | Move the focus left, down, up, right |
| `Alt+Shift+H` `J` `K` `L` | Move the window |
| `Alt+1` … `Alt+0` | Workspaces 1-10 |
| `Alt+Shift+1` … `Alt+Shift+0` | Move window to workspace |
| `Alt+R` | Resize mode |
| `Alt+Shift+E` | Power menu (lock, log out, restart, shut down) |
| `Alt+Shift+X` | Lock the screen |
| Volume / brightness keys | Work as labelled (PipeWire via `wpctl`) |

Arrow keys are deliberately **not** bound to window focus: `Alt+Left/Right` is
back and forward in Firefox. Use `Alt+H/J/K/L` instead.

The panel holds the application menu, the window list, workspaces, network and
Bluetooth status, the clock (hover for the date), volume, battery percentage on
laptops, and the power menu. It sits along the **bottom edge and hides itself**;
move the pointer to the bottom of the screen to bring it back. It is started by
the i3 configuration (`hunter-panel`), not by the session wrapper, so it comes up
in the live session and on an installed system alike.

---

## 8. Administering this computer from another one (Cockpit)

Every image ships Cockpit, the browser-based administration tool: a terminal,
services, logs, storage and account management from a web page. It is the same
Cockpit used on other machines to open a shell on a remote computer.

Cockpit starts by itself in the live session and in the installed system
(`cockpit.socket` is enabled in both). It listens on port 9090 on this computer
and is meant for a browser on another computer on the same trusted network.

**Find this computer's address.** In the live session or on the installed
system run:

```
hunter-cockpit
```

It prints the address to open, for example `https://192.168.1.42:9090`, and
whether the socket is running. `ip -4 addr show` and `hostname -I` show the
address as well.

**Log in.** Open the printed address in a browser on the other computer. The
browser warns once about the self-signed certificate that Cockpit generates for
this machine; accept it. Then log in with the normal account of this computer:

| Where | Account | Password |
|---|---|---|
| Live session | `user` | `live` |
| Installed system | the account created by the installer | the password chosen there |

Cockpit authenticates through PAM against the accounts of this computer, so
the credentials are the ones that already exist on the machine. No password,
key or certificate is stored in the image, no administrative session is opened
automatically, and nothing is exposed outside the local network unless you
forward port 9090 yourself.

The **Terminal** page gives a shell as the account you logged in with; commands
that need root ask for the same account's password through `sudo`, exactly as
the desktop does.

No firewall is installed in this image, so nothing has to be opened. If you add
one, allow 9090 on the trusted network only, for example with
`sudo ufw allow from 192.168.1.0/24 to any port 9090 proto tcp`. Do not forward
9090 from the internet: Cockpit is an administrative interface for a local
network.

---

## 9. Resources and performance

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
image): Firefox ESR ~260 MB, Calamares with Qt6 ~150 MB (removed at install
time), the rest of the desktop ~200 MB. The ISO is expected in the 1.0-1.3 GB
range.

**Idle RAM has not been measured** — see `Test-Report.md`. The 400 MB target is
plausible for this stack but unproven; the report explains exactly how to
measure it.

---

## 10. Secure Boot

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

## 11. Known limitations

* **amd64 only.** A single x86-64 ISO cannot support ARM machines or every
  proprietary hardware configuration.
* **NVIDIA:** the open `nouveau` driver plus firmware is installed. The
  proprietary driver is not bundled; install `nvidia-driver` afterwards if you
  need full performance. Optimus laptops use the Intel/AMD GPU by default.
* **One browser only.** Falkon was removed in 1.1: Qt6 WebEngine cost ~230 MB
  and used more memory than Firefox ESR for the same page. `sudo apt install
  falkon` brings it back if a second engine is ever needed.
* **Video tearing on Intel graphics.** i3 runs without a compositor, so
  tearing is possible. `hunter-graphics.service` installs the TearFree
  configuration automatically - but only on Intel Bay Trail / ValleyView
  graphics (`8086:0f31`, `0f32`, `0f33`), the hardware this release was
  prepared for. On every other machine the file is removed, so the Intel
  driver is never forced onto unrelated hardware. Remove
  `/etc/X11/xorg.conf.d/20-intel.conf` and restart the display manager to roll
  it back.
* **Battery percentage is whatever UPower reports.** The 10-15 % sudden
  power-off seen on the older installation is a hardware/gauge behaviour; the
  image neither fakes the percentage nor forces a cutoff.
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

## 12. Project layout

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

SMD Linux consists of configuration files, shell scripts and generated
artwork from this project, plus unmodified Debian packages. The configuration
and scripts are released under the MIT license; the included Debian software
keeps its own licenses.
