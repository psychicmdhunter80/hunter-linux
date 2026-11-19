# SMD Linux 1.6.1

**Moving a window to another workspace left both workspaces wrong.** Fixing
that exposed two further defects in how the helper builds a layout at all, and
the three of them were found by reading the test evidence and then reproducing
it on the image, not by looking at the desktop.

## What was wrong

The tiling helper ignored i3's move events. That was deliberate - the helper
moves windows itself while it builds a layout, and reacting to its own moves
would loop - but the reasoning covered only half the case.

Move a window to another workspace and i3 redistributes the space by itself:

- the workspace it left came back with the right number of tiles and the
  **wrong arrangement**. Four windows are two stacked on the left and two on
  the right; after the fourth left, i3 gave the first window the full height and
  stacked the other two beside it. The helper's rule is the third below the
  first, the second full height on the right - arrival order, which i3 does not
  know.
- the workspace it arrived on showed the new window at the size it had, or
  split itself in a way that only looks right while there are two windows. The
  moment a third one arrived, the arrangement was whatever i3 inserted rather
  than the one the layout asks for.

The only way to get a correct layout back was to open or close a window. The
1.6.0 test suite never noticed, because the boot test moved its windows with a
fullscreen toggle afterwards - a test-only trigger that no owner ever presses.

## What happens now

A window that changes workspace is a rebuild reason for **both ends**, and the
helper still never reacts to its own moves: a workspace is rebuilt only when the
set of windows on it has really changed, so its own commands settle without
doing anything.

Fixing that exposed a second defect, in how the helper built a layout at all.
It used to append a layout file, move the windows into the marked slots and
close the slots - which left the wrapper container behind. The next rebuild was
appended inside that wrapper, so a workspace that had been arranged twice came
out narrower than the screen: two windows as 456 and 455 pixels of a 1366-wide
desktop, three as three narrow tiles in the left half. It also meant a window
could keep one of the slot marks after a rebuild, and the next rebuild found
that mark on another workspace and took its window there.

The arrangement is now made out of the windows themselves. Two windows are what
i3 makes when one arrives beside another; for the third and the fourth, the
window that has to share its half is split vertical and the new one is moved
beside it. Nothing is appended, nothing is marked, nothing is left behind - so
the same rebuild gives the same geometry every time, however often it runs.

A workspace nobody is looking at is marked *due* and arranged the moment you
show it, which is also the first moment its arrangement can be seen.

Arranging must not touch the view, and the first attempt at this did: it asked
i3 for the workspace it was about to arrange, every time, "to be sure". The
shipped i3 config sets `workspace_auto_back_and_forth`, so that command is not
a no-op when the workspace already has the focus - i3 reads it as "go back" and
sends you to the workspace you came from. This was found on the image by the
live boot test, not in review: with two windows open, closing one of them moved
the desktop to the other workspace while both remaining windows stayed behind.
The command is gone. The arrangement is made with splits and moves that name
their windows, so it goes into the tree and never into the view.

The same setting applies to `move container to workspace`: moving a window to
the workspace it is already on sends it to the one you came from. The helper
therefore moves a lone window only when it really is somewhere else, and passes
`--no-auto-back-and-forth` when it does. The tests show a workspace with
`workspace --no-auto-back-and-forth number N` for the same reason: a measurement
step that asks for the workspace it is already on must not change what it is
about to measure.

The half that holds two windows is reused when it is still there from the
previous rebuild, instead of being split a second time: splitting it again
would bury the pair one wrapper deeper on every rebuild, and a workspace
arranged often enough would end up inside a stack of containers. A window that
floats, or one that sits in the scratchpad, is not part of the arrangement, and
one that is tiled again afterwards is arranged like a new arrival.

Nothing else changes: the same 1 / 2 / 3 / 4 layout, the same panel, the same
icons, the same loading screen, the same voice typing.

## What the tests do now

- The boot test moves a window to another workspace with nothing but i3's own
  move command, shows the workspace the way you would, and asserts the
  **shape**, not just the number of tiles: the three windows left behind keep
  their arrival order, the window that arrived fills its workspace, and a second
  arrival becomes two equal halves.
- The Brave reproduction at 1366x768 does the same and adds the case that
  actually separates the two behaviours: a *third* window moved in has to go
  below the first, which is exactly where i3's own redistribution and the
  helper's arrival order disagree.
- The fullscreen-toggle trigger is gone from both.
- The Brave reproduction also moves the same window back and forth twice, floats
  a window and tiles it again, sends one to the scratchpad and shows it over an
  unchanged layout, and reads the container depth out of the tree, so a rebuild
  that wrapped what it arranged would show up as a deeper tree.
- The live boot test records where every window really is, and which workspace
  has the focus, around the panel section's window closing. That record is what
  identified the workspace bounce.

## Verification

Results are recorded in `Test-Report.md`; the raw `result.txt` of every run
travels with the delivery.
