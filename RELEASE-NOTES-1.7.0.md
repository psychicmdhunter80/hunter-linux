# SMD Linux 1.7.0

1.7.0 changes one thing about the desktop: how windows are placed, and how the
workspaces they live on behave. The panel, the applications, the installer, the
loading screen and the shortcuts for everything else are the ones Hunter
approved.

## Two windows on a workspace

- The **first** ordinary window on a workspace fills it.
- The **second** splits it into **equal left and right halves**: the first
  window stays on the left, the second goes on the right.
- A **third** window is not squeezed in. It opens on its own workspace - as
  that workspace's first window, filling it - and the desktop switches to that
  workspace, so the program you just opened is the one you see.

The workspace you are looking at always comes first. Open YouTube on workspace
1, switch to empty workspace 2 and open email: the email stays on 2 and YouTube
stays on 1. Stay on workspace 1 and open email instead, and the two become
left and right halves. Opening a program never jumps back to another workspace
because that one has room.

Closing a window lets its neighbour fill the workspace again. Nothing slides or
packs between workspaces: the windows on the other workspaces are left exactly
where they are.

## When there is no room

Ten workspaces, two windows each. If every workspace already holds a window
and the one you are on already holds two, the program is **not** closed and
nothing else is moved out of the way to make room for it:

- it stays on the workspace it opened on, as a **floating window**, centred and
  marked, and a notification says that no empty workspace is left and what to
  do (close a window and open it again);
- a window you **move by hand** into a workspace that already holds two stays
  there floating, with the same notification, and the two windows that were
  already there are not moved.

Browser tabs are not windows, and dialogs, floating utility windows, the
scratchpad and the panel take no slot. Fullscreen keeps both windows on their
own workspace; it never pushes an application onto another one.

## Ten workspaces, and walking them

The desktop has workspaces **1 to 10** and does not create an eleventh.

- **Alt+1 … Alt+0** goes straight to a workspace, including an empty one, so
  applications can be kept apart on purpose.
- **Alt+Shift+1 … Alt+Shift+0** moves the focused window to one.
- **Ctrl+Alt+Right** goes to the **next workspace that holds a window**, in
  numerical order, wrapping round; **Ctrl+Alt+Left** goes backwards. With
  workspaces 1, 4 and 7 in use, Right walks 1 → 4 → 7 → 1 and Left 1 → 7 → 4 →
  1. Empty workspaces are skipped, and from an empty workspace you land on the
  nearest occupied one in that direction.
- The old "move the window to the next workspace" shortcut used those same
  keys, so it now has Shift added: **Ctrl+Alt+Shift+Left/Right**. It is the
  only shortcut 1.7 changes.

On the panel, the four numbered buttons for **1-4** stay. Beside them is one
compact button for **5-10**: it opens a list of all ten workspaces with the
occupied ones marked, and its icon shows the number itself while you are on
5-10, an accent dot while something runs up there, and a quiet grid when nothing
does. The active workspace number is therefore never hidden, and no application
can sit on a workspace the panel cannot reach.

## The helper got smaller, and stopped taking the focus

The 1.6.x helper rebuilt a workspace's layout after every change. That rebuild
is what focused a workspace in the background, what produced new windows on an
unintended workspace while it was working, and what left nested containers
behind. 1.7 removes the rebuild entirely: i3 already splits a workspace when a
second window arrives and collapses the split when one leaves, which **is** the
one-then-two layout. The helper now acts only when a window would make a third,
and it acts on that window by id, on the workspace that window is on.

So: a background workspace is never rebuilt and never takes the focus; opening,
closing and moving settle on their own without a fullscreen toggle or any other
synthetic event; the helper is one process, it cannot trigger itself, and there
are no overlapping rebuilds.

## Unchanged

The panel's size, styling and position; the pinned Brave and File Manager
launchers; icons-only running-window buttons with the title in the tooltip; the
S menu; **Alt+Z** voice typing and the text-editing keys; Brave with its
extensions and codecs; VLC; the Jellyfin client; Cockpit; the loading screen;
the installer and its live-session-only entry.

## Delivery

| | |
| --- | --- |
| Image | `SMD-Linux-v1.7.0-amd64.iso`, 1,207,959,552 bytes |
| SHA-256 | `1c637e054c961b8ae9f1172dfa7db39c0290a5cd43490b58ebc70130fd4e8c11` |
| Build | Actions run `44633739555`, image commit `b5815b83` |
| Source | `SMD-Linux-Build-v1.7.0.zip`, checksums in `SHA256SUMS` |
| Live boot (BIOS and UEFI) | run `44635214442` |
| Window and workspace behaviour | run `44635217637` |
| Installation test | run `44635222172` |
| Voice typing and Jellyfin | run `44635226301` |
| Installer version label | run `44635230275` |
| Package manifest | run `44635232817` |

What passed, what did not, and which checks still need Craig's own machine are
in `Test-Report.md`; the mechanism is documented in
`TECHNICAL-REFERENCE-1.7.0.md`.
