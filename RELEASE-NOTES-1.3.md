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

## Verified in a virtual machine

`<!-- RESULTS -->`

## Not verified

`<!-- REMAINING -->`

## Files

* `SMD-Linux-v1.3-amd64.iso` - the bootable image.
* `SHA256SUMS` - checksums with sizes; `sha256sum -c SHA256SUMS`.
* `SMD-Linux-Build-v1.3.zip` - the source of this build.
* `SMD-Linux-v1.3-README.md`, `SMD-Linux-v1.3-Test-Report.md` - documentation.
