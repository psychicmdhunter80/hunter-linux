#!/usr/bin/env python3
"""Print the workspace state the 1.7 window tests read.

The tiling tests need three facts, and they need them in one line each so a
serial console can carry them:

    FOCUSED <n>                      the workspace that has the focus
    MAX <n>                          the highest workspace number that exists
    WS <n> tiled=<n> floating=<n>    how many windows of each kind it holds
    WIN ws=<n> tiled=<0|1> id=<x> name=<title>

A tiled window is one i3 has in the workspace's tiling tree; a floating one
is a dialog, a utility window or a window the tiling helper kept as overflow.
Counting the two separately is what proves that dialogs and overflow windows
do not take an ordinary slot.
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
    lines = []

    def walk(node):
        nonlocal highest
        for key in ("nodes", "floating_nodes"):
            for child in node.get(key, []) or []:
                if child.get("type") == "workspace":
                    number = child.get("num")
                    if isinstance(number, int) and 1 <= number <= MAX_WORKSPACES:
                        highest = max(highest, number)
                        tiled = leaves({"nodes": child.get("nodes") or []})
                        floaters = floating_leaves(child)
                        lines.append("WS %d tiled=%d floating=%d name=%s"
                                     % (number, len(tiled), len(floaters),
                                        child.get("name", number)))
                        for window in tiled:
                            lines.append("WIN ws=%d tiled=1 id=%s name=%s"
                                         % (number, window.get("window"),
                                            str(window.get("name", "")).strip()))
                        for window in floaters:
                            lines.append("WIN ws=%d tiled=0 id=%s name=%s"
                                         % (number, window.get("window"),
                                            str(window.get("name", "")).strip()))
                walk(child)

    walk(tree)
    print("MAX %d" % highest)
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
