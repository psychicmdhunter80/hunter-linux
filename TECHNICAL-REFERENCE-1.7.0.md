# SMD Linux 1.7.0 - technical reference

**Status: built, packaged and tested in virtual machines.** The image has not
yet been accepted on Craig's hardware, and nothing here is a claim about a
public download; the delivered files are in `../delivery-1.7.0/`, described in
`README.md`.

---

## 1. Identity

| | |
| --- | --- |
| Distribution | SMD Linux 1.7.0 |
| Base | Debian 13 "trixie", amd64 |
| Image | `SMD-Linux-v1.7.0-amd64.iso`, 1,207,959,552 bytes (hybrid live ISO, BIOS + UEFI) |
| Installed packages | 944 (exact list in `PACKAGE-MANIFEST-1.7.0.txt`) |
| SHA-256 | `1c637e054c961b8ae9f1172dfa7db39c0290a5cd43490b58ebc70130fd4e8c11` |
| Build | Actions run `44633739555`, job "Build ISO" |
| Image commit | `b5815b83` (the documentation commit that follows it is recorded in `CHECKPOINT-1.7.0.md`) |
| Builder | `debian:trixie` container, `live-build` 1:20250505+deb13u1, Dockerfile in this project |
| Build inputs | this repository at that commit (source archive `SMD-Linux-Build-v1.7.0.zip`) |

## 2. What changed in 1.7.0

Only the window manager's policy changed. There is one new program
(`hunter-workspaces-nav`), one rewritten one (`hunter-autotile`), one extended
one (`hunter-workspaces`), one extra panel control, and a small set of i3
configuration changes. Nothing was added to the package list.

| Area | 1.6.1 | 1.7.0 |
| --- | --- | --- |
| Windows per workspace | up to four in a 1 / 2 / 2x2 balanced layout | **two**; a third opens on its own workspace |
| Workspaces | four buttons, more possible | **ten**, numbered 1-10, never eleven |
| Overflow | none (fourth and later stacked in columns) | next empty workspace, shown; floating when all ten are full |
| `hunter-autotile` | rebuilt a workspace's tree after every change | acts only when a window would make a third; no rebuilds |
| Workspace walk | `Ctrl+Alt+Left/Right` moved a window | `Ctrl+Alt+Left/Right` walk **occupied** workspaces; the move has Shift added |
| Panel | four numbered launcher buttons | the same four, plus one control for 5-10 |
| Version | 1.6.1 | 1.7.0 in `VERSION`, artwork and labels |

## 3. The window rule

### 3.1 Definitions

* **Ordinary tiled window**: a window i3 has in a workspace's tiling tree
  (`nodes`), not in `floating_nodes`. Dialogs, utility windows, the scratchpad
  and the panel are therefore outside the rule; an i3 window that is floating
  (`floating` ends in `_on`) takes no slot.
* **Denied window**: the installer and its dialogs (`calamares`, `yad`,
  `zenity`, `xmessage`, `gcr-prompter`, polkit agents) are never counted, moved
  or floated by the helper.
* **Occupied workspace**: a workspace that holds at least one window, tiled or
  floating (used by navigation and by the panel).
* **Empty workspace**: a workspace with no ordinary tiled window (used as an
  overflow destination). A workspace that only holds a floating window still
  has both of its tiled slots.

### 3.2 Placement

| Windows on the workspace | Result |
| --- | --- |
| 1 | it fills the usable area (`default_orientation horizontal` keeps the split axis predictable) |
| 2 | equal left/right halves, first window left, second right |
| 3 (new window) | the new window moves to the next empty workspace as its first window, and that workspace is shown |
| 3 (window moved in by hand) | the moved window stays on the destination **floating**, with a notification |
| >2 (i3 or the image already left three) | the extra window is handled by the same two exceptions |

Nothing is rebuilt to reach the two-window shape. i3 splits a workspace when
the second window is mapped and collapses the split when one of the two is
closed, so the one-then-two arrangement is i3's own behaviour; the helper acts
only on the window that would make a third. This is why a workspace in the
background cannot be rearranged, and why no command in the helper needs the
view.

### 3.3 Overflow selection

`next_empty_workspace()` in `hunter-autotile`:

```
for step in 1 .. 9:
    number = ((current - 1 + step) % 10) + 1
    if number holds no tiled window:
        return number
return None            # all ten hold a window
```

* Numerical order from the current workspace, wrapping through 1-10.
* A spare slot on a **different** occupied workspace is never used: only a
  workspace with no tiled window is a destination.
* Existing windows are never moved or redistributed to make room.
* The workspace number is the only thing consulted, so gaps are handled by
  construction: occupied 1, 2, 4 with 2 full sends the next window to 3.

After the move the helper issues `workspace --no-auto-back-and-forth number N`
and focuses the moved window, because the requirement is that the program just
opened is the one on screen. `--no-auto-back-and-forth` matters on this image:
`workspace_auto_back_and_forth yes` is set in the shipped i3 config, and
without the flag a `workspace` command naming the workspace you are already on
sends the view back to the one you came from.

### 3.4 Exhaustion, and a full destination

Both cases use one exception, so the behaviour is learnable:

1. `[con_id=X] mark --add smd-overflow`
2. `[con_id=X] floating enable, resize set 66 ppt 70 ppt, move position center`
3. `notify-send` (falling back to `i3-nagbar`) naming the window and the
   workspace and saying why it is floating.
4. A line in `~/.cache/smd/autotile.log`.

The application is never killed, never overwritten, and no eleventh workspace
is created. The normal limit (two tiled windows per workspace, ten workspaces)
stays intact, because the overflow window is floating and therefore outside
the count.

The mark is what makes the window identifiable afterwards: `i3-msg -t get_marks`
lists it, and the notification names the window's title.

### 3.5 Closing, moving, fullscreen, floating windows

* **Closing** one of two windows leaves the other filling the workspace (i3
  collapses the split). Other workspaces are untouched. Nothing is packed from
  another workspace into the freed slot.
* **Moving** into a workspace with room settles by itself: i3 appends the
  window and the pair is two halves. The move is a background operation; the
  helper does not switch workspaces, so the focus stays where it was.
* **Fullscreen** does not change the number of tiled windows, and the helper
  ignores `fullscreen_mode` events altogether. Entering and leaving fullscreen
  leaves both windows on their workspace and restores the halves.
* **Floating a window** removes it from the tiling tree, so its slot becomes
  free; the next application opened on that workspace is its first tiled
  window. Tiling it again makes the pair of halves.
* **Browser tabs** are one X window and therefore one slot.

## 4. `hunter-autotile` (rewritten)

Location: `/usr/local/bin/hunter-autotile`, started once per session by
`hunter-applets`, guarded by a `flock` in `$XDG_RUNTIME_DIR`.

* **IPC**: the helper speaks i3's protocol directly (Python 3, no `i3ipc`
  dependency): subscribe, read the tree, run commands, demultiplex replies and
  events on one socket.
* **Events used**: `window` events with change `new`, `move` and `floating`.
  Nothing else is subscribed, and no timer runs.
* **Own moves**: before moving an overflow window the helper records its
  container id; the `move` event that the command itself raises is recognised
  and discarded. That is what prevents it from acting on its own work, and it
  is the only state the helper keeps.
* **No rebuild, no `workspace` command except the deliberate overflow switch**,
  no fullscreen toggle, no synthetic key event.
* **Failure handling**: every event is handled inside a `try`; an error is
  logged and the loop continues. A lost socket is reconnected and the
  subscription re-established.
* **Log**: `~/.cache/smd/autotile.log`, truncated at 64 KiB, one line per
  decision (`workspace N was full: <title> opened on workspace M`, `... stays
  floating`, notification text, command failures).

The 1.6.x machinery (`reflow`, arrival-order bookkeeping, `expected_layout`,
`settle` signatures, wrapper reuse, the flatten detour, `state["order"]`,
`state["settled"]`, `state["due"]`) is gone. It existed to force a 3/4-window
layout i3 does not produce by itself; with a two-window limit there is nothing
to force. Keeping it would have preserved exactly the code that focused
background workspaces and nested containers.

## 5. `hunter-workspaces-nav` (new)

Location: `/usr/local/bin/hunter-workspaces-nav`. One short-lived process per
invocation: it asks i3 one question on its own connection, answers, and exits.
It never subscribes, so it cannot block the session's event stream.

| Invocation | Effect |
| --- | --- |
| `next` / `prev` | switch to the next/previous **occupied** workspace, numerical order, wrapping |
| `move-next` / `move-prev` | move the focused window to the next/previous workspace number (1-10, wrapping) |
| `menu` | rofi list of workspaces 1-10 with state, then switch to the choice |
| `menu --print` | the same list as text (used by the boot test) |
| `state` | `active=<n>` and `occupied=<a,b,c>` for the panel helper |

Rules implemented:

* Occupied = holds a window, tiled or floating; empty workspaces are skipped.
* From an occupied workspace, next is the smallest occupied number above it,
  wrapping to the lowest; previous is the largest below it, wrapping to the
  highest.
* From an empty workspace, next is the smallest occupied number above it
  (wrapping), previous the largest below it (wrapping).
* One occupied workspace: the target is that workspace and the command is not
  issued, so the view does not move. No occupied workspace: nothing is issued.
* The menu uses `rofi -dmenu -no-custom`, so a typed workspace cannot become an
  eleventh.

## 6. Panel controls

`xfce4-panel` keeps plugin 4 (launchers 1-4) and gains plugin 13, a launcher
for `smd-workspace-more.desktop`, placed directly after the numbered buttons.

`hunter-workspaces` writes the five `.desktop` files on every start and on
every relevant event, and only rewrites a file whose content changed:

| File | Icon | Action |
| --- | --- | --- |
| `smd-workspace-1..4.desktop` | `smd-ws-N` / `smd-ws-N-active` | `i3-msg -q "workspace number N"` |
| `smd-workspace-more.desktop` | see below | `hunter-workspaces-nav menu` |

The 5-10 button's icon is chosen by `more_icon()`:

* active workspace is 5-10 → `smd-ws-<n>-active`, i.e. **the number itself**,
  filled in the accent colour;
* something runs on 5-10 → `smd-ws-more-busy` (grid with an accent dot);
* otherwise → `smd-ws-more` (quiet grid).

So the active number is always visible, an occupied workspace above 4 is
announced on the panel, and the menu lists all ten with their window counts -
no application can be stranded on a workspace the panel cannot reach.

The helper subscribes to `workspace` **and** `window` events. A window event
(something opened, closed or moved) refreshes the occupancy marker; only a
workspace `focus`/`init` event moves the highlight, so the 1.6 defect that put
the highlight back on the workspace just left cannot return. All ten icons
(`smd-ws-1` … `smd-ws-10`, plain and active) plus the two 5-10 icons are
generated by `tools/make-assets.py` from `VERSION`'s image assets, not drawn by
hand.

## 7. i3 configuration changes

`config/includes.chroot/etc/skel/.config/i3/config`:

* `default_orientation horizontal` added, so the first split is always
  left/right and never top/bottom.
* Workspace section documents the two-window rule and keeps all twenty direct
  binds (`Alt+1..0`, `Alt+Shift+1..0`); nothing can create workspace 11.
* `Ctrl+Alt+Right/Left` → `hunter-workspaces-nav next/prev`;
  `Ctrl+Alt+Shift+Right/Left` → `hunter-workspaces-nav move-next/move-prev`
  (the old `move container to workspace next/prev`).
* Everything else is unchanged, including `Alt+Z` dictation, the editing keys,
  `Alt+H/J/K/L`, floating/fullscreen/scratchpad keys and the resize mode.

`workspace_auto_back_and_forth yes` is kept: it is the owner's setting and the
reason every workspace command the image issues carries
`--no-auto-back-and-forth`.

## 8. Version handling

`VERSION` is still the only place the release number is written. The image
name, ISO label and application string, installer strings, boot theme,
shortcut page and every generated picture derive from it; the build regenerates
the artwork before the squashfs is made. `tools/verify-project.py` reads the
label out of Calamares, `/etc/issue`, `/etc/os-release`, `/etc/lsb-release`,
the shortcut page, the GRUB theme and the disc README and fails if any of them
disagrees with `VERSION`.

## 9. Components

Unchanged from 1.6.0, with the same provenance: Debian 13 packages from the
official repositories, Brave from Brave's signed repository, the Jellyfin MPV
Shim in `/opt/jellyfin-mpv-shim`, nerd-dictation from source with the Vosk
`vosk-model-small-en-us-0.15` model fetched at build time and refused if its
checksum differs. The exact installed set is in `PACKAGE-MANIFEST-1.7.0.txt`;
1.7.0 adds no package, only files.

## 10. Tests

| Job | What it proves |
| --- | --- |
| `build` | static checks (including the new panel, navigation and two-window assertions); the image builds; the artwork is regenerated from `VERSION`; no CRLF inside the image; the 1.5/1.6 clients and tools are present |
| `boot-test` (`mode=both`) | live boot under BIOS and UEFI: login, what is on screen while booting, panel (bottom edge, never hides, icons only, pinned Brave/File Manager), the four buttons **and the 5-10 control**, the menu listing all ten, the active number visible above 4, the two-window layout, the third window overflowing to the next empty workspace, closing expanding the neighbour, the occupied-workspace walk, a move between workspaces, the full-destination exception |
| `tile-brave` (`helper=image`, uefi) | real Brave windows at 1366x768: one fills, two are ordered halves, the third and fourth overflow to the next empty workspace, an application opened on a chosen empty workspace stays there, closing expands the neighbour, tabs are not windows, a dialog floats, a floating window frees its slot, fullscreen keeps both windows, moves into empty/partial/full destinations, the overflow mark and notification, navigation through gaps and wrapping, one occupied and no occupied workspace, all ten workspaces, exhaustion, repeated cycles and idle stability, one helper and no errors |
| `installer-label` | the installer drawn on the image names 1.7.0 in text and in the artwork, with a screenshot |
| `voice-apps` | Alt+Z start/stop, known recording dictated into a real text field, Ctrl+Z/X/A reaching the application, notification feedback, the Jellyfin client starting with its configuration |
| `install-test` | install to a disposable disk, remove the ISO, boot the disk, log in, prove it is the installed system, then check Cockpit, panel, icons-only buttons, workspace buttons, wallpaper, audio, applications, the two clients, Voice Typing - and that no installer favourite or shortcut is left |
| `manifest` | the exact package list and component manifest read from the image |

Results, run IDs and the exact list of what passed are in `Test-Report.md`. A
`FAIL` line fails its job; a check that could not run is reported as
incomplete, never as a pass.

## 11. Known limitations

* **Hardware-only, not testable in a VM:** speaker and headphone loudness,
  panel tearing on the Bay Trail screen, the printed top-row keys, Wi-Fi against
  real access points, suspend/lid, the battery percentage and dictation accuracy
  in a real room. These remain Craig's to confirm.
* **A floating overflow window is found by its notification and its mark**, not
  by a panel button of its own. The notification names the window and the
  workspace; `Alt+Shift+<n>` goes there. It is deliberately the rare path, and
  it keeps the application alive rather than closing it.
* **The overflow notification is a desktop notification** (with `i3-nagbar` as
  the fallback if `notify-send` is missing). Whether the bubble is visible
  depends on `xfce4-notifyd` running, which the session does start; a
  screenshot of the bubble is not part of the automated evidence - the log line
  and the mark are.
* **1366x768 is emulated** through the virtual VGA's EDID. It matches Craig's
  panel geometry and panel height, but it is not his panel.
* **The panel menu needs `rofi`**, which the image already ships for the
  launcher; if `rofi` failed, `Alt+5..0` and the four buttons would still work.
* **Jellyfin playback** is not exercised end to end: no server exists in the
  test environment.
* **The Jellyfin client still logs a missing PyGObject** (`No module named
  'gi'`) at start-up, as recorded for 1.6.0; playback and the window are
  unaffected.
* **A wallpaper with broader appeal** still has no design; no wallpaper service
  was added, as requested.

## 12. Rebuilding and rolling back

```
./build.sh                 # -> SMD-Linux-v1.7.0-amd64.iso in this directory
```

The build is from scratch every time (`lb clean --purge`), and the source
archive is `SMD-Linux-Build-v1.7.0.zip`.

Rollback points, untouched by this release:

| Tag | Delivery |
| --- | --- |
| `v1.6.0` (`3896657`) | `delivery-1.6.0/` - the four-window layout, 1,207,959,552 bytes, SHA-256 `94a38565…a05141` |
| `v1.5.0` (`84349b0`) | `delivery-1.5.0/` - the working baseline before the window work |

`git checkout v1.6.0` restores the previous window behaviour; the panel
configuration, icons and `VERSION` move with it, so no mixed state is possible.
