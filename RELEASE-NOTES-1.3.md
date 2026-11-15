# SMD Linux 1.3

Dark-theme and tidy-up release for the Acer Chromebook 11 CB3-111. Everything
1.2 repaired is kept; 1.2 stays published as rollback.

## What changed

* **One consistent dark theme.** The image always asked for `Adwaita-dark`, but
  the theme itself is shipped by `gnome-themes-extra`, which 1.1 removed as part
  of the size trim. GTK does not fail on a missing theme - it silently fell back
  to light Adwaita - so only the panel background was dark. The package is back,
  and the theme is set in GTK3, GTK4, XSettings, i3's own title-bar colours and
  the terminal palette. That covers the S button, the task buttons, the whisker
  menu and its search/categories/hover states, application menus and toolbars.
  No compositor, no theme daemon, no extra theme engine.
* **One installer entry.** `hunter-install.desktop` and the `calamares`
  package's own `calamares.desktop` ("Install System") launched the same
  installer. The generic entry is removed while the package and its dependencies
  stay installed, and "Install SMD Linux" now uses the SMD "S" icon instead of
  the old project logo.
* **Auto-hide retired.** The panel stays visible along the bottom edge, black;
  full-screen video covers it. `hunter-panel-dock`, and the `python3` /
  `python3-xlib` packages that existed only for it, are gone. Panel startup, the
  one-panel guarantee and the logout/login fix are unchanged.

* **Screen tearing.** The TearFree repair from the original Debian install is
  included as before - `Driver "intel"` with `Option "TearFree" "true"` in
  `/etc/X11/xorg.conf.d/20-intel.conf`, installed by `hunter-graphics.service`
  before the display manager and only for Intel Bay Trail graphics
  (`8086:0f31`/`0f32`/`0f33`). It had never actually run: the script was
  committed with Windows line endings, so its shebang was unreadable and the
  unit failed at every boot. It also searched `lspci` for the PCI ID before the
  `VGA` class, but `lspci` prints the class first, so it never recognised the
  Chromebook and deleted the file again after each reboot; the match is now
  `VGA.*8086:<id>`, and a test feeds it a real Chromebook line. It starts now,
  and `hunter-graphics --report`
  prints the graphics device, the driver module, the configuration, the
  `TearFree` lines from `/var/log/Xorg.0.log` and the service state so the
  result can be checked after a reboot. No compositor was added.
* **Jellyfin playback.** The ISO ships Debian's `i965-va-driver` and an
  `mpv.conf` for the Jellyfin MPV shim with `hwdec=auto-safe`, so the Chromebook
  decodes in hardware instead of software; machines without the driver fall
  back to software. `display-resample` is not set - it made frame dropping worse
  in testing.
* **Speaker volume.** `hunter-volume` reproduces the level Hunter tuned by hand
  on the Chromebook: the output goes to **125 %** once per session, and only
  while it is still the untouched 100 % and the active port is the internal
  speaker - headphones are left alone, and the volume keys keep working on top
  of it. It is a sink-level setting, so nothing is specific to Jellyfin. On
  the Chromebook the codec's own startup level (raw 10, -14 dB) was also raised
  to the accepted raw 20 (0 dB) by `hunter-audio-hw.service`, which backs up the
  UCM file first and does nothing at all on machines without that codec. The
  delayed Jellyfin audio is addressed by pinning the PipeWire quantum to 2048,
  the value that produced immediate audio on the installed system. The
  sound server itself also had to be fixed: `pipewire.socket` came up failed and
  took PipeWire with it, so sessions had no mixer at all. Activation is now by
  service with the sockets masked, and the session starts `pipewire`,
  `wireplumber` and `pipewire-pulse` if the units do not.

## Verified in a virtual machine

Checks run against the delivered ISO under both BIOS and UEFI; **56 passed, 0
failed** on each:

* the dark theme is selected *and* installed, GTK3/GTK4 settings point at it and
  the i3 title-bar colours are set;
* the menu holds exactly one installer entry, `hunter-install.desktop`, with the
  SMD icon;
* the panel is set never to hide and stays visible along the bottom edge; no
  `hunter-panel-dock` and no `python3` process is running; exactly one panel
  survives an i3 reload;
* resource use recorded under the test conditions: 498 MiB used of 1967 MiB with
  662 MiB free after the session settles;
* PipeWire is the sound server and PipeWire, WirePlumber and `pipewire-pulse`
  are running; `hunter-volume` is installed and logs that it left the volume
  alone, because the virtual machine's sink has no speaker port;
* the quantum is 2048 in `/etc/pipewire/pipewire.conf.d/50-hunter-quantum.conf`
  (quantum, min and max) and `pw-metadata` reports `clock.quantum` 2048 at
  runtime;
* `hunter-audio-hw.service` is enabled and active and did **not** edit any UCM
  file on the virtual machine, which has no max98090 codec;
* the TearFree matcher matches a real Chromebook `lspci` line
  (`00:02.0 VGA compatible controller [0300]: ... [8086:0f31]`), the unit is
  enabled and active, and no `20-intel.conf` is written for the VM's QEMU
  adapter;
* `i965-va-driver` is installed and the shim's `mpv.conf` sets
  `hwdec=auto-safe` without `display-resample`.

The installer was also run end to end: it partitions, installs, writes GRUB and
the EFI entries, reboots, and the installed system reaches the SMD greeter. The
harness could not open a serial login on the installed system, so it logged in
at the greeter instead and the installed desktop's own checks were not automated
in this run.

## Not verified

These need the Chromebook itself, and none of them is claimed here:

* whether the picture is actually tear-free in YouTube and Jellyfin, in window
  and full screen (the VM has no Intel graphics, so it can only prove the file is
  not forced where it does not belong);
* whether the speaker is as loud as the level Hunter accepted after the codec
  fix, and that headphones still switch and stay unboosted;
* whether Jellyfin starts with sound immediately and stays free of dropouts over
  a long session;
* frame drops with VA-API over a long playback (a short run on the Chromebook
  showed none, longer runs still dropped some);
* the top-row keys, Wi-Fi association and battery reporting, which the VM cannot
  exercise.

The CPU governor was tested on the Chromebook and made no noticeable difference,
so no performance-mode change is included.

## Files

* `SMD-Linux-v1.3-amd64.iso` - the bootable image.
* `SHA256SUMS` - checksums with sizes; `sha256sum -c SHA256SUMS`.
* `SMD-Linux-Build-v1.3.zip` - the source of this build.
* `SMD-Linux-v1.3-README.md`, `SMD-Linux-v1.3-Test-Report.md` - documentation.
