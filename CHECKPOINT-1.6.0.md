# SMD Linux 1.6.0 - working checkpoint

Written while the first 1.6.0 ISO was building, so the next session starts
exactly here instead of repeating the survey.

## State at this checkpoint

| | |
| --- | --- |
| Branch | `release/1.6.0` (the 1.5.0 delivery is untouched: tag `v1.5.0`, branch `baseline-1.5.0`) |
| Baseline | `SMD-Linux-v1.5.0-amd64.iso`, 1,134,166,016 bytes, `9820f5fa...fa1952`, tag `v1.5.0` at `84349b0` |
| Version now | `1.6.0`, written once in `VERSION` |
| Build revision | `41f79bf` (the source the delivered image is built from) |
| Final build | `44550560639` - `SMD-Linux-v1.6.0-amd64.iso`, 1,207,959,552 bytes, `94a38565...a05141` |
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

## Test results so far (exact ISO `91e4103...`)

| Check | Result |
| --- | --- |
| Build `44438132258` | success; `SMD-Linux-v1.6.0-amd64.iso`, 1,207,959,552 bytes, SHA-256 `91e410328141abda48837736c7dfadbf4409bab3fa61a9c327213148b66f4261` (local copy re-hashed, matches) |
| Installer version label `44439474802` | 12/12 pass - productName, version, versionedName, os-release, issue, lsb-release, window title and on-screen text all say 1.6.0 |
| Installation test `44444481561` | **106 pass, 0 fail**, 2 notes (power handling from a serial session): greeter login, installed desktop, wallpaper, panel, icons-only buttons, Brave and File Manager pinned, four workspace buttons, **no installer favourite and no installer shortcut on the installed system** |
| Voice typing `44448554475` | 37 pass, 1 fail: the toggle, notification, single recogniser and mic release all pass; the recogniser transcribed the fixture as "OnceThe roses" instead of the digits. Re-run `44449785929` dispatched to see whether that is flaky |
| Live boot `44443429824` | **failed**: both firmwares. Boot frames were all black ("something was drawn while the machine booted" failed), and a cluster of unrelated checks failed together (PipeWire, solid panel background, menu icon, top row, notifications, tiling) alongside `WARN: command timed out` lines - the guest stopped answering the serial console mid-run. That pattern is a hung/starved test VM, not yet a diagnosed image defect; it needs one run with the serial timeouts instrumented before anything is concluded |
| Tiling `44448557433` | still running |

The 1.5.0 baseline is untouched: `baseline-1.5.0` branch and tag `v1.5.0`, ISO
still `9820f5fa...fa1952`.

## Second image: the i3 wedge found and fixed

The live boot test on `91e4103...` failed on both firmwares, and the cause was
this project's own code, not the test: `hunter-workspaces` asked i3 for the
workspace list from inside i3's event stream, on the same socket i3 uses to
answer that request. i3 stopped answering - `i3-msg -t get_workspaces` never
returned - and the tiling helper could not get its work done in time either.
The helper now reads the workspace number out of the event itself and never
talks to i3 from inside the loop. Two test defects from the same run are fixed
too: boot frames were never captured (the monitor was out of scope) and a hung
guest produced one failure per stranded command instead of one honest line.

| | |
| --- | --- |
| Build `44454488079` | success, commit `1b65fea`; `SMD-Linux-v1.6.0-amd64.iso`, 1,207,959,552 bytes, SHA-256 `7a7653945dd06f7beb3b3f153146bab53cfad9f267a43897e6ada8ac279f936f`; downloaded to `../delivery-1.6.0/`, re-hashed, matches |
| Manifest `44456401528` | 944 packages (+plymouth, +libplymouth5); `PACKAGE-MANIFEST-1.6.0.txt` |
| Installer label `44455799482` | RESULT: passed - productName, version, versionedName, os-release, issue, lsb-release, window title and on-screen text all say 1.6.0 |

The first manifest run failed because the version-free ISO glob sat in a
variable, where the shell never expands it; fixed in the workflow and re-run.

## Where this ended

The delivered image is build `44550560639` (commit `41f79bf`), and every test
below was run against that exact artifact:

| Check | Result |
| --- | --- |
| Live boot `44560534614` | BIOS and UEFI, 102 passed and 0 failed on each |
| Installer label `44552638839` | 12 passed, 0 failed |
| Brave tiling at 1366x768 `44552628935` | 25 passed, 0 failed, helper from the image |
| Voice typing and Jellyfin `44552633676` | 38 passed, 0 failed |
| Installation `44552643828` | 53 passed, 0 failed, 1 note about the power menu |
| Package manifest `44552648621` | 944 packages, identical to `PACKAGE-MANIFEST-1.6.0.txt` |

Three defects were found by testing and fixed in this release, all in this
project's own code rather than in the tests: the workspace helper acted on i3's
`empty` event for the workspace just left, the tiling helper rebuilt from its
remembered window order and so pulled a moved window back, and the boot test's
window placement used i3 criteria that matched nothing on this image.

## Not done yet - next steps in order

1. (done) Watch run `44438132258` (the first build, `44437139505`, failed on an
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
