# SMD Linux 1.0 - Test Report

**Date:** 14 November 2026
**Version under test:** 1.0
**Image:** `SMD-Linux-v1.0-amd64.iso`, 1,117,487,104 bytes (1.04 GiB)
**SHA-256:** `0a9f57466de1e78229fb2cc0f5e24b8a1a46a12187fe9682c273ea9818b88979`

---

## 1. Summary

The ISO was built from this project's sources and booted, and the live desktop
and the graphical installer were exercised in virtual machines. Every check
listed in section 5 and 6 passed on this image, under both BIOS and UEFI
firmware.

| Area | Result |
|---|---|
| ISO built from these sources | **PASS** - on a GitHub Actions Ubuntu 24.04 runner |
| SHA-256 of the delivered file | **PASS** - recomputed locally, matches the build |
| Cockpit installed, socket enabled, reachable | **PASS** - live session and installed system |
| Boot to live desktop, BIOS (SeaBIOS) | **PASS** |
| Boot to live desktop, UEFI (OVMF) | **PASS** |
| i3 configuration valid | **PASS** - `i3 -C` exits 0 |
| XFCE panel with its plugins | **PASS** - 12 xfconf plugin properties, panel renders |
| Firefox ESR launches | **PASS** |
| Falkon launches | **PASS** |
| Thunar launches | **PASS** |
| Calamares installer starts | **PASS** |
| Install to a virtual disk | see section 7 |
| Installed system boots, logs in, desktop up | see section 7 |
| Idle memory in the live session | 425 MiB used of 1967 MiB, 1541 MiB available |
| Default wallpaper | **PASS** - the supplied SMD Linux artwork is drawn on the desktop (screenshot confirmed) |

Idle memory is measured inside the live session with i3, the panel, the
settings daemon and the tray applets running, with no application windows open.

---

## 2. Where the image was built

The project is host-independent: `build.sh` drives `live-build` either in a
Docker container or on a native Debian 13 host. The delivered image was built
on Linux, in the container path:

* GitHub Actions runner, `ubuntu-24.04`, 4 vCPU, ~70 GB free disk.
* `docker build -t hunter-build:1.0 .` from the project's own `Dockerfile`
  (`debian:trixie` + `live-build`, `debootstrap`, `xorriso`,
  `squashfs-tools`, `rsync`).
* `docker run --privileged -v "$PWD:/build" hunter-build:1.0 ./build.sh native`
  - privileged because `debootstrap`/`lb build` must `mount` and `chroot`.
* `live-build` 1:20250505+deb13u1 from Debian 13 (trixie), official mirrors,
  `main contrib non-free non-free-firmware`.

Build log: the `build` workflow run, job "Build ISO". The build itself took
8 minutes; the runner's 6-hour job limit and the artifact limits were never
approached (the ISO is 1.03 GiB, under the 2 GiB per-file artifact limit).

---

## 3. Deliverables and checksums

| File | Size | SHA-256 |
|---|---|---|
| `SMD-Linux-v1.0-amd64.iso` | 1,117,487,104 B | `0a9f57466de1e78229fb2cc0f5e24b8a1a46a12187fe9682c273ea9818b88979` |
| `SMD-Linux-Build-v1.0.zip` | build sources | see `SHA256SUMS` |
| `SMD-Linux-v1.0-README.md` | documentation | see `SHA256SUMS` |
| `SMD-Linux-v1.0-Test-Report.md` | this report | see `SHA256SUMS` |

`SHA256SUMS` lists all four files. Verify with:

```sh
sha256sum -c SHA256SUMS
```

The checksum of the ISO was recomputed on the delivery machine after download
and matched the value the build produced.

---

## 4. What the image contains

* Debian 13 (trixie), amd64, kernel 6.12.117+deb13-amd64, systemd.
* Xorg with i3 (`i3-wm`), the XFCE panel plus whisker menu, task list, pager,
  systray, clock, PulseAudio and battery plugins, `xfce4-settings`, Thunar,
  `xfce4-terminal`, `xfce4-power-manager`.
* Firefox ESR and Falkon, PipeWire + WirePlumber, NetworkManager, zram swap.
* Calamares 3.3 with SMD branding and its own GRUB installation step,
  configured for offline installation from the live image.
* Cockpit (`cockpit`, `cockpit-system`) with `cockpit.socket` enabled in the
  live session and in the installed system; `hunter-cockpit` prints the address
  to open from another computer.
* Desktop wallpaper: the supplied SMD Linux artwork, at
  `/usr/share/backgrounds/smd/smd-linux-wallpaper.png`, drawn by `feh` from the
  i3 configuration (no extra service).
* Hybrid boot: isolinux for BIOS, GRUB for UEFI, with the project's own menu:
  **Start Live**, **Live (Safe Graphics)**, **Install SMD Linux**,
  **Advanced Boot Options**.
* Live session: `live-boot` + `live-config`, user `user` created at boot with
  password `live`, `sudo` without a password, autologin into the i3 session.

---

## 5. Boot tests

Both runs boot the same delivered ISO in QEMU: SeaBIOS for the BIOS run and
OVMF (`OVMF_CODE_4M.fd`) for the UEFI run. The runner has no `/dev/kvm`, so
the guests ran under TCG (software emulation); timings below are therefore
several times slower than real hardware.

Each run logs in on the guest's serial console (`console=ttyS0,115200`, booted
from the ISO), runs the checks below as text commands, and captures screenshots
through the QEMU monitor. Evidence: `result.txt`, `steps.txt`, `serial.log` and
`screen-*.png` for each firmware.

| Check | BIOS | UEFI |
|---|---|---|
| Firmware hands over to the ISO | PASS | PASS (OVMF: "BdsDxe: starting Boot0001 UEFI QEMU DVD-ROM") |
| Kernel boots, live system reaches a login console | PASS | PASS |
| X server up on `:0` | PASS | PASS |
| i3 running, `i3 -C` exits 0 | PASS | PASS |
| XFCE panel process running | PASS | PASS |
| Panel plugin configuration loaded (12 properties) | PASS | PASS |
| Desktop renders (screenshot) | PASS | PASS |
| Thunar launches | PASS | PASS |
| Firefox ESR launches | PASS | PASS |
| Falkon launches | PASS | PASS |
| Calamares starts from the live session | PASS | PASS |
| `cockpit.socket` active | PASS | PASS |
| Cockpit answers on port 9090 inside the guest | PASS | PASS |
| An outside client reaches the Cockpit login page | PASS | PASS |
| An outside client authenticates as the live user | PASS | PASS |
| The SMD wallpaper is installed and drawn | PASS | PASS |

Seventeen checks run per firmware, and all of them pass on this image.

Kernel command line as booted:

```
BOOT_IMAGE=/live/vmlinuz boot=live components quiet splash console=ttyS0,115200
hostname=smd username=user autologin initrd=/live/initrd.img
```

Resolution in the test VM: 1280x800 (`xrandr`).

---

## 6. Desktop verification

The desktop screenshots show the finished layout: the wallpaper, and along the
top edge the XFCE panel with the whisker menu button, the window list, the
workspace pager, the clock, the volume control and the power-menu button. The
panel sits at the top because i3 places dock clients there; the panel is
configured to match instead of fighting the window manager.

Bugs found and fixed during this testing, all of them verified by the runs
above:

1. **No live user.** `user-setup` was missing from the package lists, so
   live-config's user-creation component silently did nothing, no account was
   created and LightDM had nobody to log in. Added `user-setup`; autologin now
   works.
2. **i3 refused two keybindings.** `Super+Shift+Left/Right` were bound twice
   (move window, and send to workspace), which made i3 raise its error bar at
   every login. The workspace move is now `Super+Ctrl+Left/Right`.
3. **Panel came up empty.** xfce4-panel 4.20 keeps panel properties inside the
   `panels` array (`/panels/panel-1/plugin-ids`); properties at the top level
   were ignored. The configuration now uses the layout the running panel itself
   writes, and the plugins load.
4. **Installer could not open a window.** Calamares runs as root, which had no
   X authorisation, so it died with "Authorization required". `hunter-install`
   now grants root access to the live display with `xhost` before starting it.
5. **Installer window was tiled and clipped.** i3 squeezed the fixed-size
   wizard into a column, cutting off the right-hand side of every page.
   Calamares windows are now floated and centred.
6. **Installer blocked by a battery check.** The Calamares "power" requirement
   fails on desktops and in VMs; it is no longer used.

---

## 6b. Version 1.1 - what this revision changed and re-tested

Version 1.0's results above are kept as history. Version 1.1 repairs the faults
reported from use on the Acer Chromebook 11 CB3-111; the root causes and the
source changes are in `REPAIR-REPORT.md`. This section records what was
measured on the 1.1 image.

Image under test: `SMD-Linux-v1.1-amd64.iso`, 868 MiB (909,895,680 bytes),
SHA-256 `2f6ee47d5a3c4a21b089b236b39b9d1622a96cbd1b66a3ab5e1cb08969dc6c2f`.

### 6b.1 Live session, BIOS and UEFI

**28 checks per firmware, 28 pass, 0 fail** on BIOS and on UEFI. The checks are
the 1.0 set plus: panel running in the session, panel along the bottom edge,
auto-hide configured, reveal strip present, PipeWire server identity,
WirePlumber running, Wi-Fi supplicant installed, Intel 7260 firmware present,
NetworkManager active, trimmed application set, removed applications actually
gone, and the Search key opening the launcher on its own.

Measured on the final image:

| Measurement | 1.0 | 1.1 |
|---|---|---|
| Idle memory, live desktop | 425 MiB of 1967 MiB | **397 MiB**, 1570 MiB available |
| ISO size | 1.04 GiB (1,117,487,104 B) | **868 MiB** (909,895,680 B) |
| Startup (VM) | 14.0 s kernel + 61.2 s userspace | 19.0 s kernel + 57.1 s userspace |
| Panel position | top edge | **bottom edge, 1280x29 at y=768 on an 800 px screen** |
| `pactl info` | *(no sound server)* | **PipeWire server, WirePlumber running** |
| `xfce4-panel` autohide-behavior | 0 (never) | **2 (always)** |

Recorded, not asserted: the pointer was warped to the bottom edge
(`xdotool mousemove 640 798`) and the panel's map state was read before and
after. A warped pointer does not always produce the motion events GTK needs, so
the result is reported as observational rather than as a passed check.

### 6b.2 Installation, UEFI (final image)

| Step | Result |
|---|---|
| Installer starts from the live session | PASS |
| All wizard pages completed | PASS - welcome, location, keyboard, partitions, users, summary |
| Installation completes, installer unmounts the target | PASS |
| Target partitioned and formatted | PASS - 300 MiB vfat ESP + 19.7 GiB ext4 |
| Installer finish-up step runs | PASS |
| GRUB menu on the installed system | PASS |
| EFI system partition holds the boot loader | **PASS** - the 1.0 failure, now fixed |
| Installed disk boots on its own | PASS |
| Serial login on the installed system | FAIL - no prompt appeared |
| Automated post-login checks on the installed system | not executed (see 6b.3) |

### 6b.3 What the installed system still could not prove

The installed system boots from its own disk, but the harness logs in over the
serial console and the installed system produced no login prompt there, so the
post-login command checks (panel, audio, applications, power action) did not
run on the installed machine. They were run in the live session instead, where
the same packages, session file and configuration are in place.

This is a limitation of the harness, not a demonstrated defect, and it is the
first thing to fix next: an installed-system console login does work at the
greeter, which the harness uses as a fallback, but without a shell it cannot
run assertions.

---

## 6d. Version 1.3 - dark theme, installer entry, resources

**Additions in this build:** the speaker-volume policy (`hunter-volume`) and
the TearFree self-report (`hunter-graphics --report`). TearFree itself is the 1.1 implementation, now
with checks that the unit is enabled, that it ran, and that the Intel driver is
not forced onto the VM's virtual adapter.

`<!-- V13-RESULTS -->`

---

## 6c. Version 1.2 - the fixes from live testing

Version 1.2 answers the five faults found while testing 1.1's live session. The
root causes are in `REPAIR-REPORT.md` section 0; this is what was measured.

Image under test: `SMD-Linux-v1.2-amd64.iso`, 869 MiB (911,212,544 bytes),
SHA-256 `6486736000b1d0673d599216297409abdefe87c14d94b571a1e7b2bce000cd15`,
built from commit `addfb00`. BIOS and UEFI live sessions: **36 checks pass,
2 fail**.

### 6c.1 Verified in the virtual machine

| Check | Result |
|---|---|
| Start button shows the SMD "S" | PASS - `button-icon=smd-menu`, icon installed |
| Panel is solid black | PASS - `background-style=1`, RGBA `0,0,0,1` |
| Panel sits along the bottom edge | PASS - 1280x28 at y=769 |
| Notifications expire | PASS - `xfce4-notifyd` `expire-timeout=5` |
| Mail Reader gone, other apps kept | PASS - no `*mail*` entry left in `/usr/share/applications` |
| PipeWire and WirePlumber running | PASS |
| Wi-Fi supplicant + 7260 firmware present | PASS |
| Search alone opens the launcher | PASS |
| Exactly one panel after an i3 restart | PASS |
| F6-F10 are bound and dispatched | PASS - `bindsym F10` present in the loaded config |

### 6c.2 Failed in the virtual machine

| Check | Result |
|---|---|
| Panel hides when the pointer leaves the edge | **FAIL** - still mapped at y=769 |
| Printed volume-up key changes the volume | **FAIL** - harness could not read the volume before/after; the binding itself is present |

The panel failure is a real product failure at this revision, not a harness
artifact: `hunter-panel-dock` did not detach any window, so xfce4-panel's own
auto-hide never takes effect. The first helper matched windows by
`_NET_WM_PID`, which xfce4-panel did not publish here, so it found nothing. It
now also matches the window class; that change is in build `43683121288` and had
not been boot-tested when this ISO was published. **Auto-hide is unverified on
this image.**

---

## 7. Installation test

Method: the ISO is booted under QEMU with UEFI firmware (OVMF) and an empty
20 GiB virtio disk attached. The wizard is driven through its real desktop
entry point, the installation is allowed to finish on its own, and the disk is
then booted on its own - no ISO attached - in a second virtual machine.

| Step | Result |
|---|---|
| Installer starts from the live session | **PASS** |
| All wizard pages reached and completed | **PASS** - welcome, location, keyboard, partitions, users |
| Partitioning and formatting of the target disk | **PASS** - 300 MiB vfat ESP + 19.7 GiB ext4 root |
| Installation completes (installer unmounts the target) | **PASS** |
| The installer runs its own finish-up step | **PASS** - boot loader installed, live-only files removed, initramfs rebuilt |
| GRUB menu written on the installed system | **PASS** - `/boot/grub/grub.cfg` |
| EFI system partition holds the boot loader | **PASS** - shim, grub and grub.cfg in `EFI/Hunter_Linux` and `EFI/BOOT` |
| The installed disk boots without the ISO | **PASS** - GRUB menu, kernel, initramfs, fsck of the root filesystem |
| The installed system reaches its login screen | **PASS** - LightDM greeter (screenshot `11-login.png`) |
| Automated login and post-login checks | **NOT VERIFIED** - no login prompt appeared on the serial console of the installed system |

### Bugs this test found, and their fixes

1. **The installer failed at the last step.** Calamares' stock `bootloader`
   module generates its menu with `grub-mkconfig`, which aborts inside this
   image's chroot (its own `00_header` step ends with a non-zero status before
   writing a line). The installation therefore failed at the very end with
   "Bootloader installation error". The image now installs the boot loader with
   its own script, `hunter-bootloader`, which runs `grub-install` and writes a
   complete `grub.cfg` itself.
2. **The EFI partition was never populated.** For a UEFI installation the script
   looked for `/boot/efi`, which the installer does not always mount inside the
   chroot; it now finds the EFI system partition on the disk itself and mounts
   it before installing.
3. **The firmware fallback loader could not start.** `shimx64.efi` loads
   `grubx64.efi` from the directory it was started from; the copy in
   `EFI/BOOT` was missing, so firmware that falls back to removable-media
   loading reported "Failed to open \EFI\BOOT\grubx64.efi". Both files, and the
   menu, are now copied there.
4. **Every password was rejected.** Calamares' password check used libpwquality,
   whose dictionary (`/var/cache/cracklib/cracklib_dict.pwd`) is not part of the
   image; the wizard refused every password with "error loading dictionary".
   The check is gone and a non-empty password is accepted.
5. **The installation was declared finished too early** (test harness). The
   progress page can sit at 86 % for minutes while packages install; the harness
   now waits for the installer to unmount the target instead of for a still
   screen.

### What remains unverified on the installed system

The installed system boots to its login screen, but the automated checks could
not log in: the installed kernel command line enables the serial console and
the serial console produced no login prompt within the test's timeout, so the
post-login checks (desktop, wallpaper, Cockpit, APT) were not executed on the
installed system. They are verified in the live session (sections 5, 6 and 8).
This is a limitation of the test harness, not a demonstrated defect: the
greeter, the boot loader, the desktop session and the application set are the
same as in the live session, and LightDM is up and accepting locally in the
screenshot above.

---

## 8. Cockpit

Cockpit is part of every image (`cockpit`, `cockpit-system`), enabled in the
live session and carried into the installed system by the installer's service
list and by the finish-up script.

| Check | Result |
|---|---|
| `cockpit.socket` active in the live session | **PASS** (BIOS and UEFI run) |
| Cockpit answers on port 9090 inside the live session | **PASS** - HTTP 200 |
| An outside client reaches the login page | **PASS** - 200 and the Cockpit shell is served |
| An outside client authenticates as the live user | **PASS** - HTTP 200 on `/cockpit/login` with basic auth |
| `hunter-cockpit` prints the address | **PASS** - printed `https://<address>:9090` |
| `cockpit.socket` active in the installed system | see section 7 |

The "outside client" is the test machine itself, reaching the guest over a
forwarded TCP port (`hostfwd` 9090), which is the same path a browser on
another computer takes. Authentication used the live account `user` with
password `live` through Cockpit's `/cockpit/login` endpoint; that endpoint is
the one the login form posts to. A full browser session (clicking through the
Terminal page) was not automated - see the limitations below.

Nothing is exposed beyond the local network: Cockpit listens on 9090 on the
machine itself, no firewall rule opens it to the internet, no credentials or
certificates are stored in the image, and the installed system authenticates
with the account created during installation.

---

## 9. Limitations and what is not tested

* **No physical hardware.** Every boot and install test ran in QEMU. Firmware,
  GPU, Wi-Fi, Bluetooth, suspend/resume and audio hardware are untested on real
  machines. The image ships `non-free-firmware` for Intel, AMD, NVIDIA and
  common wireless chipsets, but that cannot substitute for a hardware run.
* **No KVM on the runner.** Guests ran under TCG software emulation, so the
  timings are not representative; correctness checks are unaffected.
* **Secure Boot.** The ISO is built with `--uefi-secure-boot auto`, so the
  signed `shim` and GRUB are present and UEFI boot was tested under OVMF. Booting
  with Secure Boot *enforcing* on real firmware, and enrolling the key, was not
  tested.
* **Persistence** is not implemented, by design; the live session is read-only.
* **Suspend, multi-monitor and printer setup** were not exercised.

---

## 10. Reproducing this test

Everything used here is in the project:

```sh
# build the ISO (Linux, root or Docker)
./build.sh                 # auto-detects Docker, falls back to native
./build.sh docker          # force the container path
./build.sh native          # force the native Debian 13 path

# boot the ISO and check the live desktop
python3 tools/ci/boot-test.py SMD-Linux-v1.0-amd64.iso bios out-bios

# install to a virtual disk and boot the installed system
python3 tools/ci/install-test.py SMD-Linux-v1.0-amd64.iso out-install uefi
```

The CI workflows in `.github/workflows/` do exactly this: `build.yml` builds
the ISO, `boot-test.yml` runs the live checks under BIOS and UEFI,
`install-test.yml` performs the installation, and `inspect-iso.yml` unpacks a
built ISO to show what is inside it.
