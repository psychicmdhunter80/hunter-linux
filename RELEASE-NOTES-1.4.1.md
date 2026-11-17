# SMD Linux 1.4.1

Tiling fix for the Acer Chromebook 11 CB3-111. Everything 1.4 repaired is kept;
1.4, 1.3 and 1.2 stay published as rollback.

## Why this release exists

On Craig's machine two Brave windows sometimes stacked vertically, and with
three or four windows the layout kept jumping instead of settling.

Both symptoms came from one fault in the tiling helper, reproduced in the
virtual machine with real Brave windows: **the helper was reacting to the
placeholder windows it had just created itself.** It recognised its own
placeholders by the exact name `smd-slot`, while the slots it appends are named
`smd-slot-0`, `smd-slot-1` and so on. Every rebuild therefore counted as a new
window arriving, which started another rebuild, and so on. Measured on the
delivered 1.4 image: **28 reflows for four windows**, and layouts still
changing after a minute of not touching anything. That is the jumping Craig
saw.

The vertical stacking of two windows has the same origin: a workspace rebuilt
while a rebuild was still in flight, where the surviving windows kept the
column they had from the four-window grid instead of being split left and
right.

## What changed

* **Placeholders are recognised by their name prefix** (and by their marks), so
  the helper no longer treats its own slots as windows.
* **A workspace is rebuilt when its set of windows changes**, not on a
  three-second timer. Repeated events for a workspace already in its expected
  arrangement do nothing.
* **One and two windows get the same deterministic rebuild as three and four**,
  so a workspace that comes back from four windows to two is split left and
  right even when it was left as a column.
* **The result is checked against the expected geometry**, with one retry, so a
  half-applied layout cannot be left on screen.
* **A single unexpected event can no longer end the helper**, and a closed
  window's workspace is looked up from where it was last seen rather than from
  the focused workspace.

## What the fix was verified against

The same harness that reproduced the fault ran again with the fixed helper in
the live session, with real Brave windows at 1280x772:

| Windows | Rectangles measured | Idle | Reflows |
| --- | --- | --- | --- |
| 1 | 0,0 1280x772 | - | 1 |
| 2 | 0,0 640x772 and 640,0 640x772 | 30 s, 1 layout | 2 |
| 3 | 0,0 640x386, 640,0 640x772, 0,386 640x386 | 60 s, 1 layout | 3 |
| 4 | 2x2, 640x386 each, fourth bottom-right | 60 s, 1 layout | 4 |

Fullscreen, exiting fullscreen, clicking, typing and focus changes left the grid
alone; closing the third window re-arranged the remaining three; reopening a
window settled back into the 2x2 grid. Reflows for the whole session: 7, one per
change, against 28 in the first minute on 1.4. See `Test-Report.md` for the raw
rectangles and for what still needs Craig's own machine.

## Where this release stands

| | |
| --- | --- |
| Image | `SMD-Linux-v1.4.1-amd64.iso` |
| Build | run `BUILD_RUN`, commit `COMMIT` |
| Live boot | LIVE_RESULT |
| Brave tiling | TILE_RESULT |
| Installation | INSTALL_RESULT |
