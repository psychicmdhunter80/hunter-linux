# SMD Linux 1.6.1

One defect, found by reading the test evidence rather than by looking at the
desktop: **moving a window to another workspace left both workspaces wrong.**

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

Rebuilding takes the focus i3 needs to do that, so a workspace nobody is
looking at is marked *due* and arranged the moment you show it, which is also
the first moment its arrangement can be seen.

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

## Verification

Results are recorded in `Test-Report.md`; the raw `result.txt` of every run
travels with the delivery.
