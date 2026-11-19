# SMD Linux 1.6.0

The desktop stays exactly as Hunter approved it on Craig - the same tiling
helper, the same one/two/three/four window layout, the same S menu, the same
bottom panel. What changes is what you see and what you can reach.

## The loading screen

Between the boot menu and the desktop there used to be a bare cursor for
several seconds. There is now a screen that says what is happening:
**SMD LINUX**, the version, "SMD Linux is loading..." and three dots that light
in turn. It appears immediately (`ShowDelay=0`), it lives in the initramfs, and
it disappears when the session starts - it is not a resident service. If it
cannot draw, plymouth falls back to its own text screen by itself, and Escape
shows the boot messages on either path.

## The panel

- Running applications show **icons, not titles**. A long page title used to
  take half the bar. The window title is still in the hover tooltip, and every
  window keeps its own button.
- **File Manager is pinned beside Brave**, as a launcher, in the same block.
- **Four numbered workspace buttons** (`1 2 3 4`) replace the miniature window
  previews. They are always there, even when a workspace is empty; the current
  one is filled in the accent colour; clicking one switches to it. i3 discards
  an empty workspace when you leave it, so the old previews could never show
  all four - these buttons do.
- Restrained styling: a flat background with one border colour, a rounded hover
  tile, the accent colour for the active button. No compositor, no shadows, no
  blur, nothing that costs a frame on a 2 GB machine.
- Alt+1 to Alt+4 already switched workspaces and still do. Alt+Z is still voice
  typing.

## One version, written once

`VERSION` is now the only place the release number exists. The image name, the
ISO label, the ISO application string, the installer strings, the boot theme,
the shortcut page and **every generated picture** derive from it, and the build
regenerates the artwork before it starts. 1.5.0 shipped an installer whose
heading said 1.5.0 while the artwork underneath still said 1.4.1; that
generation defect is now impossible rather than merely fixed.

## The installer entry belongs to the live session

The applications menu lists Browser, File Manager, Terminal, and directly below
them **Install SMD Linux**. The installer's own post-install script removes
both the launcher and the favourites entry, in `/etc/skel` and in every home
directory, so an installed user is left with no installer icon and no favourite
pointing at one.

## Unchanged on purpose

- The tiling helper. It is the code Hunter confirmed on Craig, including the
  four-window grid, and it is not being replaced or rewritten.
- Speakers/headphones, brightness and the top-row keys, Cockpit, Jellyfin MPV
  Shim and Alt+Z voice typing.
- Brave with Shields, h264ify and Auto Quality for YouTube. No second blocker,
  no additional "performance" extension: there is no evidence that one would
  help, and the machine has little memory to spare.

## Recorded, not built

- A default wallpaper with broader appeal: no design chosen yet, current assets
  kept. The image has no wallpaper-changing action of its own (i3 plus feh, no
  desktop manager) and adding one is not worth the memory.
- An offline HTML beginner guide: still deferred until the features settle.
