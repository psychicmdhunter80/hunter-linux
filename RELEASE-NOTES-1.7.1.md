# SMD Linux 1.7.1 - release notes

**Patch release.** The window rule is untouched: two windows per workspace, ten
workspaces, the occupied-workspace walk and the overflow exception behave
exactly as in 1.7.0. This build fixes the black startup screen, replaces the
text workspace menu with ten buttons, and adds a fifteen-minute stability
observation.

## 1. Startup feedback: why the screen was black, and what fixes it

Two independent faults kept the loading screen off the screen. Both were proven
from Plymouth's own debug log, not inferred from a blank photograph.

### Cause 1: the serial console sent the splash to the wrong terminal

The kernel command line carried `console=ttyS0,115200` so the test harness could
read the boot. Plymouth treats a serial console as something it must manage:

```
serial consoles detected, managing them with "details" forced
```

That forces the text `details` plugin onto `/dev/ttyS0`; the graphical `smd`
theme is never created, so the panel shows nothing while `quiet` hides the
kernel's messages. **Fix:** `plymouth.ignore-serial-consoles` on the live and
installed command lines. The same log now answers:

```
ignoring all consoles but default console because explicitly told to.
```

and then opens the DRM renderer.

### Cause 2: the label plugin was missing, so no text could be drawn

`plymouth-label` was not installed. Without `label-pango.so` every
`Image.Text` in `smd.script` drew nothing; only the gradient background
appeared. The debug log said so directly:

```
Could not load module /usr/lib/x86_64-linux-gnu/plymouth/label-pango.so
```

**Fix:** `plymouth-label` is in the package list, and the initramfs hook now
fails the build unless `label-pango.so` and `libpango-1.0.so` are inside every
initramfs.

### What the screen does now

Plymouth's log on the delivered image shows the whole chain:

```
ignoring all consoles but default console because explicitly told to.
creating devices for /dev/dri/card0 (renderer type: 1)
drm driver: bochs-drm
Found preferred mode 1280x800
Creating 1280x800 renderer head
executing script file
label-pango: Text 'SMD LINUX' has dimensions 90x19
label-pango: Text 'VERSION 1.7.1' has dimensions 117x19
label-pango: Text 'SMD Linux is loading...' has dimensions 178x19
```

The visible result is the SMD gradient with **SMD LINUX**, **VERSION 1.7.1**,
**SMD Linux is loading...** and three cycling dots. The splash is on screen for
about 63 seconds of the roughly 85 second pre-desktop interval under software
emulation (TCG). Nothing was added to slow or pad the boot: `ShowDelay=0`, no
sleep, no progress percentage, and no resident process - Plymouth runs from the
initramfs and exits at handover.

### What remains

* About 13 seconds between Plymouth quitting and the greeter drawing are still
  black with a text cursor. That is LightDM starting, not the theme; it is
  measured and documented rather than papered over.
* One wording size is fixed by the label plugin (19 px tall at 1280x800). It is
  legible but modest; enlarging it would mean rendering the wording as images.
* **QEMU measures the virtual VGA only.** Craig's panel is the only place that
  can confirm the same result on his hardware, and that confirmation is still
  separate and pending.

### Correction preserved

An earlier draft said the 1.7.0 initramfs contained no Plymouth at all. That was
wrong: the initramfs is an uncompressed early cpio followed by a gzip payload,
and grepping the raw file misses everything inside it. Plymouth, both
renderers, the `smd` theme and `Theme=smd` were present all along. The two
faults above are the corrected finding.

## 2. The panel shows which workspaces hold windows

The text menu behind the 5-10 control is gone. All ten workspaces are buttons of
their own, and each icon answers "is anything there?":

| Icon | Meaning |
| --- | --- |
| quiet tile with the number | empty workspace |
| quiet tile, number and an accent bar | holds a window |
| accent tile, white number | the workspace you are on |
| accent tile, white number and a white bar | you are on it and it holds a window |

The first 1.7.1 attempt put ten items into one launcher plugin and still showed
a single button and an overflow arrow, because XFCE draws one button per
launcher plugin, not per item. The shipped panel therefore has ten single-item
launchers (`plugin-20`...`plugin-29`); the existing subscriber
(`hunter-workspaces`) writes one `.desktop` per workspace and chooses among
forty icons. Clicking any workspace switches to it, including an empty one.

**Measured footprint**, from the running desktop: tiles are 24 px wide on a
32 px pitch, so the ten occupy **312 px** (x 829-1140 at 1280 wide), not the
"roughly 220 px" guessed earlier. At Craig's 1366x768 that is 320 px of the
panel; the pinned Brave and File Manager, the task list, systray, clock, volume,
battery and power controls are unchanged and unclipped.

## 3. Stability

1.7.0 was signed off on twenty seconds of idle observation. The stability pass
now drives five launch/overflow/switch/move cycles with real windows and then
watches a settled desktop for **fifteen minutes**, failing on any focus change,
window relocation, helper restart, self-triggered rearrangement, slow i3 reply
or runaway helper CPU/memory.

The first stability run on this image (`44979093917`) failed its occupied-walk
assertion five times. The walk was correct - from workspace 5 it went right to
10 and left back to 5 - but the test assumed the third window always lands on
workspace 2 and that the walk starts on 1. With workspace 2 already occupied by
an earlier check, the third window correctly went to 5. The assertion now
measures from the workspace the walk starts on; the behaviour is unchanged.

The measured pass is run `45038334087`: **94 assertions, 0 failures**. Five
interaction cycles, then **30 samples over 921 s (15.3 min)** of a settled
desktop holding one witness window. Layout, focus and helper count never
changed, the helper log did not grow, and the window manager answered every
query.

| While idle | CPU | Memory |
| --- | --- | --- |
| `hunter-autotile` | 0.0 % (1.2 s of CPU in total, unchanged across the window) | 12,852 kB, flat |
| `hunter-workspaces` | 0.0 % | 1,524 kB, flat |

CPU is differenced from `/proc/<pid>/stat` between samples rather than read as
a lifetime average, and a check with no samples now fails instead of passing on
nothing. The helper measured is the one in this image: `git diff` between the
image commit and the test commit touches nothing under `config/`.

## 4. Nothing else changed

* The two-window rule, ten workspaces, occupied-workspace walk, direct
  selection, the overflow exception, dialogs, floating windows, fullscreen and
  the scratchpad are untouched.
* One package was added, `plymouth-label`; the image now has **945** packages.
  No driver was added: the earlier speculative early-module list is not what
  fixed the screen and is not claimed as necessary.
* No Brave extension, Jellyfin component or dictation behaviour was touched.
* 1.7.0 remains unchanged in `../delivery-1.7.0/`.

## 5. Status of this build

| Area | Status |
| --- | --- |
| Window policy | unchanged; boot test passes on both firmwares on this ISO |
| Panel occupancy buttons | ten real buttons, visually checked; boot test loads all ten; footprint measured |
| Startup feedback | **fixed in the VM** and proven from Plymouth's log; Craig's hardware still pending |
| Boot test | run `44980323313` - BIOS and UEFI, 128 passed, 0 failed each |
| Installation test | run `44979098657` - 54 passed, 0 failed, installed disk booted |
| Stability | run `45038334087` - **94 passed, 0 failed**; 15.3 min idle, helper 0.0 % CPU, memory flat |
| Package manifest | run `44980929191` - 945 packages |

See `Test-Report.md` for the run-by-run evidence of this exact image and
`TECHNICAL-REFERENCE-1.7.1.md` for the mechanism.
