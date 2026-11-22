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
| Stability (`44981903097`, 15 min idle) | **passed**: 14m40s idle, no layout drift, no helper appeared or died, i3 responsive, one helper at the end |
| Stability rerun (`44984337056`) | running: measures helper CPU/RSS by pid and requires real idle samples (the earlier sampler matched nothing and passed on no data) |

Harness defects fixed and rerun, kept in `Test-Report.md`: splash crop used
pixel offsets for percentages; launcher items counted by desktop name instead
of panel plugin; occupied-walk assertion assumed it started on workspace 1.

## What is left

1. Read `44984337056` and put its measured CPU/RSS before/after idle into the
   release notes, technical reference and test report.
2. Verify the ISO in `../delivery-1.7.1/` against its SHA-256, run
   `python tools/package-release.py`, and move its outputs next to the ISO.
3. Only then tag `v1.7.1`. Craig's hardware confirmation is separate and still
   pending; nothing here is a hardware result.

## If interrupted

`git checkout release/1.7.0` restores the source. The image is complete and
verified apart from the helper-usage measurement; no image rebuild is needed
for test or document changes. Reuse `run_id=44978338982` for any test on this
ISO.
