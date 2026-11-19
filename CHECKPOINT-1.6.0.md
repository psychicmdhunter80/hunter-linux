# SMD Linux 1.6.0 - working checkpoint

Written while the first 1.6.0 ISO was building, so the next session starts
exactly here instead of repeating the survey.

## State at this checkpoint

| | |
| --- | --- |
| Branch | `release/1.6.0` (the 1.5.0 delivery is untouched: tag `v1.5.0`, branch `baseline-1.5.0`) |
| Baseline | `SMD-Linux-v1.5.0-amd64.iso`, 1,134,166,016 bytes, `9820f5fa...fa1952`, tag `v1.5.0` at `84349b0` |
| Version now | `1.6.0`, written once in `VERSION` |
| Build revision | `2e18858` (the source the image is built from) |
| Build attempts | `44437139505` failed in the artwork step; `44438132258` is the live build |
| Static checks | `python tools/verify-project.py` - all pass |

## Done in this session

1. **Version consistency, at the cause.** `VERSION` is the only place the
   release number is written. `auto/config` (image name, ISO label, ISO
   application), `build.sh` and the build workflow derive from it, and
   `tools/make-assets.py` draws the pictures from it. The artwork was
   regenerated for 1.6.0 - the installer logo now reads "VERSION 1.6.0" and the
   wallpaper "1.6.0" (checked by eye, not just by string search). The build has
   a new step that regenerates every asset into a scratch tree and fails if the
   committed picture differs, which is the class of defect that shipped 1.4.1
   artwork under a 1.5.0 heading.
2. **Panel.** Running windows are icons only (`show-labels false`), the title
   stays in the tooltip, the File Manager is pinned beside Brave, the S menu,
   spacers and status controls are untouched. `gtk.css` adds a restrained
   panel-only style: flat background, one border colour, a rounded hover tile
   and the accent colour for the active button - no compositor, no shadows.
3. **Numbered workspace buttons.** The miniature pager is replaced by four
   launcher buttons (`smd-workspace-1..4.desktop`), always present, with a
   filled accent tile for the current one. A new `hunter-workspaces` helper
   writes those .desktop files at session start and rewrites them on i3's
   workspace event stream - no polling. Alt+1..Alt+4 were already the workspace
   keys (`$mod` is Mod1) and are left as they were.
4. **Loading screen.** Plymouth with a generated `smd` theme: "SMD LINUX /
   VERSION 1.6.0 / SMD Linux is loading..." and three dots that light in turn.
   `ShowDelay=0`, `DeviceTimeout=8`, `splash` on the installed system's kernel
   line. It lives in the initramfs and stops when the session starts.
5. **Live installer favourite.** The menu lists Browser, File Manager, Terminal,
   then "Install SMD Linux". `hunter-postinstall` removes both the .desktop
   file and the favourites entry, in `/etc/skel` and in every home directory.
6. **Checks.** `tools/verify-project.py` grew `check_panel_controls`,
   `check_startup_feedback` and `check_installer_favourite`, all source-level.

## Not done yet - next steps in order

1. Watch run `44438132258` (the first build, `44437139505`, failed on an
   artwork byte-comparison that was unsound across zlib builds; the build now
   regenerates the artwork instead of comparing it).
2. Download the ISO artefact and record its size and SHA-256.
3. Run, against that exact ISO: `boot-test.yml` (BIOS and UEFI), the panel and
   workspace checks (new test still to write - the panel must be photographed at
   1366x768 and the workspace buttons clicked), `tile-brave.yml`,
   `voice-apps.yml`, `installer-label.yml`, and `install-test.yml` with the
   greeter login. A screenshot file-size threshold is not evidence: the panel
   and desktop checks must read the window properties, the xfconf values and the
   running processes inside the session.
4. Item 8 (playback stability) needs real measurement on Craig/Dell hardware:
   a QEMU guest decodes in software and cannot answer a hardware-decode
   question. Record what the image contains (Brave Shields, h264ify, Auto
   Quality for YouTube, no second blocker) and let Hunter measure the same video
   before and after.
5. Item 9: there is no wallpaper-changing action in this image to inspect -
   i3 plus feh, no desktop manager. Recorded as awaiting Hunter's chosen
   artwork; adding a desktop manager is refused on resource grounds.
6. Docs: README status table, RELEASE-NOTES-1.6.0.md, Test-Report section,
   TECHNICAL-REFERENCE-1.6.0.md, package manifest, source ZIP, `SHA256SUMS`,
   then tag `v1.6.0` at the documentation commit. Keep the build revision
   separate from the documentation commit in the report.
