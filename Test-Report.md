# Hunter Linux 1.0 - Test Report

**Date:** 14 November 2026
**Version under test:** 1.0
**Image:** `Hunter-Linux-v1.0-amd64.iso`, 1,109,803,008 bytes (1.03 GiB)
**SHA-256:** `379a72be3b211d3fbf441a330de0eb77d7eac0d099b00821227b01dacaa426c3`

---

## 1. Summary

The ISO was built from this project's sources and booted, and the live desktop
and the graphical installer were exercised in virtual machines. Every check
listed in section 5 and 6 passed on this image, under both BIOS and UEFI
firmware.

| Area | Result |
|---|---|
| ISO built from these sources | **PASS** - 8m01s on a GitHub Actions Ubuntu 24.04 runner |
| SHA-256 of the delivered file | **PASS** - recomputed locally, matches the build |
| Boot to live desktop, BIOS (SeaBIOS) | **PASS** |
| Boot to live desktop, UEFI (OVMF) | **PASS** |
| i3 configuration valid | **PASS** - `i3 -C` exits 0 |
| XFCE panel with its plugins | **PASS** - 12 xfconf plugin properties, panel renders |
| Firefox ESR launches | **PASS** |
| Falkon launches | **PASS** |
| Thunar launches | **PASS** |
| Calamares installer starts | **PASS** |
| Install to a virtual disk | see section 7 |
| Idle memory in the live session | 417 MiB used of 1973 MiB, 1555 MiB available |

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
| `Hunter-Linux-v1.0-amd64.iso` | 1,109,803,008 B | `379a72be3b211d3fbf441a330de0eb77d7eac0d099b00821227b01dacaa426c3` |
| `Hunter-Linux-Build-v1.0.zip` | build sources | see `SHA256SUMS` |
| `Hunter-Linux-v1.0-README.md` | documentation | see `SHA256SUMS` |
| `Hunter-Linux-v1.0-Test-Report.md` | this report | see `SHA256SUMS` |

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
* Calamares 3.3 with Hunter branding, configured for offline installation from
  the live image.
* Hybrid boot: isolinux for BIOS, GRUB for UEFI, with the project's own menu:
  **Start Live**, **Live (Safe Graphics)**, **Install Hunter Linux**,
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

Kernel command line as booted:

```
BOOT_IMAGE=/live/vmlinuz boot=live components quiet splash console=ttyS0,115200
hostname=hunter username=user autologin initrd=/live/initrd.img
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

## 7. Installation test

<!-- INSTALL-SECTION -->

---

## 8. Limitations and what is not tested

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

## 9. Reproducing this test

Everything used here is in the project:

```sh
# build the ISO (Linux, root or Docker)
./build.sh                 # auto-detects Docker, falls back to native
./build.sh docker          # force the container path
./build.sh native          # force the native Debian 13 path

# boot the ISO and check the live desktop
python3 tools/ci/boot-test.py Hunter-Linux-v1.0-amd64.iso bios out-bios

# install to a virtual disk and boot the installed system
python3 tools/ci/install-test.py Hunter-Linux-v1.0-amd64.iso out-install uefi
```

The CI workflows in `.github/workflows/` do exactly this: `build.yml` builds
the ISO, `boot-test.yml` runs the live checks under BIOS and UEFI,
`install-test.yml` performs the installation, and `inspect-iso.yml` unpacks a
built ISO to show what is inside it.
