#!/usr/bin/env python3
"""Print the workspace state the 1.7 window tests read.

The tiling tests need three facts, and they need them in one line each so a
serial console can carry them:

    FOCUSED <n>                      the workspace that has the focus
    MAX <n>                          the highest workspace number that exists
    NOTIFY <n>                       notification bubbles on screen
    WS <n> tiled=<n> floating=<n>    how many windows of each kind it holds
    WIN ws=<n> tiled=<0|1> id=<x> class=<c> name=<title>

A tiled window is one i3 has in the workspace's tiling tree; a floating one
is a dialog, a utility window or a window the tiling helper kept as overflow.
Counting the two separately is what proves that dialogs and overflow windows
do not take an ordinary slot.

The desktop notification bubble (class `xfce4-notifyd`) is counted separately
and left out of the workspace totals: it is what the tiling helper's overflow
notice looks like on screen, so its presence is evidence, not a window that
took a slot.
"""

import json
import subprocess

MAX_WORKSPACES = 10


def i3(kind):
    finished = subprocess.run(["i3-msg", "-t", kind], capture_output=True,
                              text=True, timeout=20)
    text = finished.stdout or ""
    starts = [index for index in (text.find("{"), text.find("[")) if index >= 0]
    if not starts:
        return None
    try:
        return json.loads(text[min(starts):])
    except ValueError:
        return None


def leaves(node):
    found = []
    for child in node.get("nodes", []) or []:
        if child.get("window"):
            found.append(child)
        found.extend(leaves(child))
    return found


def floating_leaves(node):
    found = []
    for child in node.get("floating_nodes", []) or []:
        if child.get("window"):
            found.append(child)
        found.extend(leaves(child))
        found.extend(floating_leaves(child))
    return found


def main():
    tree = i3("get_tree") or {}
    focused = None
    for entry in i3("get_workspaces") or []:
        if entry.get("focused"):
            focused = entry.get("num")
    if focused is not None:
        print("FOCUSED %s" % focused)

    highest = 0
    bubbles = 0
    lines = []

    def bubble(window):
        properties = window.get("window_properties") or {}
        return str(properties.get("class", "")).lower() == "xfce4-notifyd"

    def walk(node):
        nonlocal highest, bubbles
        for key in ("nodes", "floating_nodes"):
            for child in node.get(key, []) or []:
                if child.get("type") == "workspace":
                    number = child.get("num")
                    if isinstance(number, int) and 1 <= number <= MAX_WORKSPACES:
                        highest = max(highest, number)
                        tiled = leaves({"nodes": child.get("nodes") or []})
                        floaters = floating_leaves(child)
                        bubbles += sum(1 for window in tiled + floaters
                                       if bubble(window))
                        tiled = [w for w in tiled if not bubble(w)]
                        floaters = [w for w in floaters if not bubble(w)]
                        lines.append("WS %d tiled=%d floating=%d name=%s"
                                     % (number, len(tiled), len(floaters),
                                        child.get("name", number)))
                        for window, kind in ((w, 1) for w in tiled) + \
                                ((w, 0) for w in floaters):
                            properties = window.get("window_properties") or {}
                            lines.append("WIN ws=%d tiled=%d id=%s class=%s name=%s"
                                         % (number, kind, window.get("window"),
                                            properties.get("class", "-"),
                                            str(window.get("name", "")).strip()))
                walk(child)

    walk(tree)
    print("MAX %d" % highest)
    print("NOTIFY %d" % bubbles)
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
