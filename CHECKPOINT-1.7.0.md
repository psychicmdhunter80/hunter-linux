# SMD Linux 1.7.0 - checkpoint

**Saved:** 19 November 2026. Work continues from here; nothing before it was
restarted, and no earlier release, tag or delivery folder was touched.

## Where the work is

| | |
| --- | --- |
| Branch | `release/1.7.0` |
| Change commit | `e2d64f0` - "Hold every workspace to two windows and the desktop to ten" |
| Image build | Actions run `44630204635` from that commit |
| Rollback point | tag `v1.6.0` @ `3896657` (the four-window layout) and tag `v1.5.0` @ `84349b0` (the working baseline) - both untouched |
| Earlier deliveries | `../delivery-1.6.0/`, `../delivery-1.5.0/` and the 1.0-1.4 archives stay as they are |

## What was implemented

1. **Two windows per workspace.** The first fills a workspace and the second
   makes equal left/right halves. A third window is moved to the next empty
   workspace in numerical order (1-10, wrapping) and that workspace is shown,
   so the program just opened is the one on screen. Closing a window lets its
   neighbour fill the workspace; nothing is packed between workspaces.
2. **Ten workspaces, no eleventh.** Direct selection (`Alt+1..0`, including
   empty ones) and moves (`Alt+Shift+1..0`) stay. Overflow never creates a
   workspace above 10.
3. **Safe exhaustion.** With all ten workspaces holding a window and the
   current one already holding two, a new program is not closed: it is marked
   `smd-overflow`, floated and centred on the workspace it opened on, and a
   notification says that no empty workspace is left. A window moved by hand
   into a full workspace gets the same exception, and the two windows already
   there are not moved.
4. **Occupied-workspace walk.** `Ctrl+Alt+Right/Left` walk occupied workspaces
   in numerical order, wrapping, skipping empty ones, from an empty workspace
   to the nearest occupied one in that direction. The old "move window to the
   next workspace" shortcut moved to `Ctrl+Alt+Shift+Left/Right` - the only
   shortcut this release changes.
5. **Panel.** `1 2 3 4` stay as buttons. One new control opens workspaces 5-10
   as a list of all ten with the occupied ones marked; its icon shows the
   active number while 5-10 is current, an accent dot while something runs up
   there, and a quiet grid when nothing does.
6. **The focus/stability defects.** The 1.6.x helper rebuilt a workspace's
   layout after every change; that rebuild is what focused background
   workspaces, produced windows on unexpected workspaces and nested
   containers. The rebuild is gone: i3's own split/collapse already produces
   the one-then-two layout, so `hunter-autotile` only acts when a window would
   make a third. A background workspace is never touched, no fullscreen toggle
   or synthetic event is needed to settle anything, and the helper cannot
   trigger itself.

Files changed: `hunter-autotile` (rewritten), `hunter-workspaces-nav` (new),
`hunter-workspaces` (extended), i3 config (orientation, workspace binds,
navigation binds), panel XML (plugin 13), `make-assets.py` (ten workspace
icons plus the two 5-10 states), `verify-project.py` (new source-level
assertions), `shortcuts.html`, all version labels, `VERSION` = 1.7.0, and the
two live test scripts (`boot-test.py`, `tile-brave.py`) plus `ws-dump.py`.

## Verification state

| Step | Result |
| --- | --- |
| `python tools/verify-project.py` | all static checks pass, labels agree on 1.7.0 |
| ISO build | run `44630204635` - `<BUILD_RESULT>` |
| `boot-test` (BIOS + UEFI) | `44631601192` - `<BOOT_RESULT>` |
| `tile-brave` (image helper, UEFI) | `44631605492` - `<TILING_RESULT>` |
| `install-test` | `44631609406` - `<INSTALL_RESULT>` |
| `voice-apps` | `44631612966` - `<VOICE_RESULT>` |
| `installer-label` | `44631616005` - `<LABEL_RESULT>` |
| `manifest` | `44631619056` - `<MANIFEST_RESULT>` |

## Still to do

1. Fill the measured identity (ISO size, SHA-256, package count, run IDs) into
   `README.md`, `RELEASE-NOTES-1.7.0.md`, `TECHNICAL-REFERENCE-1.7.0.md` and
   the `Test-Report.md` section.
2. `python tools/package-release.py`, copy the ISO, archive, documents and
   `SHA256SUMS` into `../delivery-1.7.0/` with `test-evidence/`, and run
   `sha256sum -c`.
3. Tag `v1.7.0` at the documentation commit, push branch and tag.
4. Craig's hardware checks (speakers/headphones, tearing, printed top-row keys,
   Wi-Fi, suspend/locking, battery percentage) and his confirmation of the
   two-window rule on the real machine are still outstanding and are not
   claimed as passed.

## If interrupted

`git checkout release/1.7.0` restores the source; `git status` should be clean
apart from documentation. The build and test runs named above are in the
repository's Actions history and their artifacts are kept for 7-14 days. Do not
rebuild the image unless a source change is made: the delivered ISO must come
from the run recorded here.
