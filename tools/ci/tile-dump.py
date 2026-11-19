#!/usr/bin/env python3
"""Print the i3 layout of every workspace as indented text, for the serial console.

Full get_tree output is far too large for a serial line, so the guest does the
summarising and only the structure comes back.
"""

import json
import subprocess
import sys

try:
    raw = subprocess.run(["i3-msg", "-t", "get_tree"], capture_output=True,
                         text=True, timeout=20).stdout
    tree = json.loads(raw[raw.index("{"):])
except Exception as error:  # noqa: BLE001
    print("TREE-ERROR %s" % error)
    sys.exit(1)

lines = []


def walk(node, depth, parent=None, space=None):
    if not isinstance(node, dict):
        return
    kind = node.get("type")
    if kind == "root" or kind == "output":
        for child in node.get("nodes", []) or []:
            walk(child, depth, parent, space)
        return
    if kind == "workspace":
        # The number travels down: a window's rectangle means nothing without
        # the workspace it is a rectangle on.
        space = node.get("num")
    if kind == "floating_con":
        return
    rect = node.get("rect") or {}
    marks = ",".join(node.get("marks") or [])
    properties = node.get("window_properties") or {}
    print("%s%s id=%s parent=%s xid=%s class=%s layout=%s name=%s ws=%s "
          "rect=%s,%s+%sx%s%s%s" % (
              "  " * depth, "WIN" if node.get("window") else kind, node.get("id"),
              node.get("_parent"), node.get("window") or 0,
              properties.get("class", "-"),
              node.get("layout"), node.get("name"), space,
              rect.get("x"), rect.get("y"),
              rect.get("width"), rect.get("height"),
              " marks=%s" % marks if marks else "",
              " window" if node.get("window") else ""))
    for child in node.get("nodes", []) or []:
        child["_parent"] = node.get("id")
        walk(child, depth + 1, node.get("id"), space)


walk(tree, 0)
