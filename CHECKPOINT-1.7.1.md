# SMD Linux 1.7.1 - checkpoint

**Saved:** 22 November 2026, after the startup fix and the verification runs.
1.7.0 and everything before it stays exactly as delivered.

## Where the work is

| | |
| --- | --- |
| Branch | `release/1.7.0` (the branch name predates the patch version; it holds 1.7.1) |
| Rollback point | tag `pre-1.7.1-rollback` @ `f2e8316`, plus `v1.7.0`, `v1.6.0`, `v1.5.0` untouched |
| Image commit | `1c03f74` |
| Image build | Actions run `44978338982` |
| ISO | `SMD-Linux-v1.7.1-amd64.iso`, SHA-256 `2f01b48302287b5c55a3780f6981ec58af75985afc5766204e4447763b4a96bb`, 945 packages |
| Live in | `../delivery-1.7.1/` (the older `3b2183b4...` candidate is in `superseded/`) |
| Release tag | `v1.7.1` on this commit |

## What was wrong and what fixed it

1. **Serial console.** `console=ttyS0,115200` made Plymouth force its text
   `details` plugin onto the serial line
   (`serial consoles detected, managing them with "details" forced`), so the
   graphical theme was never created. `plymouth.ignore-serial-consoles` is now
   on the live and both installed command lines; Plymouth logs
   `ignoring all consoles but default console because explicitly told to.`
2. **Missing label plugin.** `plymouth-label` was not installed, so
   `label-pango.so` could not load and every `Image.Text` drew nothing. The
   package is installed and the initramfs hook now fails a build unless
   `label-pango.so` and `libpango-1.0.so` are inside every initramfs.

`44980208086` (Plymouth debug on the serial line) shows the full chain:
`/dev/dri/card0`, `bochs-drm`, 1280x800 head, `executing script file`, and
`label-pango` sizing `SMD LINUX` 90x19, `VERSION 1.7.1` 117x19,
`SMD Linux is loading...` 178x19. The splash is on screen for about 63 s of the
~85 s pre-desktop interval under TCG; ~13 s of black with a text cursor remain
at the LightDM handover. No delay, no percentage, no resident process.

The earlier note claiming the 1.7.0 initramfs had no Plymouth was wrong
(uncompressed early cpio + gzip payload, grepped as text). Plymouth and the
theme were always packaged; packaging was never the fault.

## Panel

Ten single-item launchers `plugin-20`...`plugin-29`; a multi-item launcher
draws one button plus an overflow arrow, which is why the first attempt still
showed one. Measured on the running desktop: tiles 24 px wide on a 32 px pitch,
group x=829-1140 = **312 px** (320 px at 1366x768). Occupancy icons come from
the existing `hunter-workspaces` subscriber; no new process.

## Verification state

| Step | Result |
| --- | --- |
| `tools/verify-project.py` | all static checks pass |
| Boot test (`44980323313`, mode=both) | **128 passed, 0 failed** on BIOS and UEFI; splash wording drawn, handover, initramfs contents, ten launchers loaded |
| Installation test (`44979098657`, uefi) | **54 passed, 0 failed**; installed disk booted without the ISO |
| Package manifest (`44980929191`) | 945 packages |
| Stability (`44981903097`, 15 min idle) | passed its idle checks, but the CPU/RSS sampler matched no process and the cheapness check passed on an empty sample |
| Stability rerun (`44984337056`) | **failed**: the corrected sampler hit `TypeError: %c requires int or char` on a literal `%c` before the idle window; no measurement taken |
| Stability final (`45038334087`) | **passed**: 94 asserts, 0 failed; 30 samples over 921 s (15.3 min), no layout/focus/helper drift, `hunter-autotile` 0.0 % CPU and 12,852 kB flat, `hunter-workspaces` 0.0 % and 1,524 kB |

Harness defects fixed and rerun, kept in `Test-Report.md`: splash crop used
pixel offsets for percentages; launcher items counted by desktop name instead
of panel plugin; occupied-walk assertion assumed it started on workspace 1; the
helper CPU/RSS sampler matched no process and then crashed on a literal `%c`.
The final sampler reads `/proc` counters, differences them across each sample
and fails when it has no samples at all.

## What is left

1. Craig's hardware confirmation of the startup screen. It is separate from
   every result above, which are all virtual-machine results.
2. Nothing else. The superseded `3b2183b4...` candidate stays marked in
   `superseded/`; `../delivery-1.7.0/` is untouched.

## If interrupted

`git checkout release/1.7.0` restores the source. The image is complete and
verified; no image rebuild is needed for test or document changes. Reuse
`run_id=44978338982` for any test on this ISO.
