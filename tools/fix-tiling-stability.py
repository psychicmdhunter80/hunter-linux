import pathlib

p = pathlib.Path("config/includes.chroot/usr/local/bin/hunter-autotile")
t = p.read_text(encoding="utf-8")

start = t.index("    def reflow(name):")
end = t.index("    def wait_for_container(con_id, timeout=2.0):")

new = '''    def expected_layout(order_ids, geometry):
        """Do the rectangles match the layout this many windows should have?"""
        boxes = [geometry[i] for i in order_ids]
        if len(boxes) == 1:
            return True
        if len(boxes) == 2:
            (ax, ay, aw, ah) = boxes[0]
            (bx, by, bw, bh) = boxes[1]
            return abs(aw - bw) <= 6 and abs(ay - by) <= 6 and ax != bx
        if len(boxes) == 3:
            (ax, ay, aw, ah) = boxes[0]
            (bx, by, bw, bh) = boxes[1]
            (cx, cy, cw, ch) = boxes[2]
            return (abs(cx - ax) <= 6 and cy > ay and abs(cw - aw) <= 6
                    and bx > ax and abs(bw - aw) <= 6)
        if len(boxes) == 4:
            (ax, ay, aw, ah) = boxes[0]
            (bx, by, bw, bh) = boxes[1]
            (cx, cy, cw, ch) = boxes[2]
            (dx, dy, dw, dh) = boxes[3]
            return (abs(cx - ax) <= 6 and abs(dx - bx) <= 6 and cy > ay
                    and dy > by and abs(aw - bw) <= 6 and abs(cw - dw) <= 6)
        return True

    def geometry_of(name):
        workspace = find_workspace(i3.tree(), name) or {}
        return {c["id"]: (c["rect"]["x"], c["rect"]["y"],
                          c["rect"]["width"], c["rect"]["height"])
                for c in leaves_of(workspace)}

    def reflow(name, attempt=1):
        tree = i3.tree()
        workspace = find_workspace(tree, name)
        live = windows_in_tree()
        # Arrival order lives in this process, not in the tree: the tree order
        # is not arrival order once windows have been moved around.
        order = [i for i in state["order"].get(name, []) if i in live]
        if workspace is not None:
            for node in leaves_of(workspace):
                con_id = node.get("id")
                if con_id in live and con_id not in order:
                    order.append(con_id)
        if not order:
            state["order"].pop(name, None)
            state["settled"].pop(name, None)
            return
        state["order"][name] = order
        for con_id in order:
            state["where"][con_id] = name

        if workspace is not None and any(c.get("fullscreen_mode")
                                        for c in leaves_of(workspace)):
            # A fullscreen window owns the screen; its workspace is left alone
            # until it comes back, and then the set is rebuilt once.
            state["settled"].pop(name, None)
            return
        if any(denied(c) for c in leaves_of(workspace or {})):
            note("leaving %s alone: it holds an installer or dialog window" % name)
            return

        # A workspace is rebuilt only when the set of windows on it changes.
        # The helper's own commands raise window events of their own, and a
        # timer cannot separate those from a real window arriving on a slow
        # machine: the window set can.
        signature = tuple(order)
        if attempt == 1 and state["settled"].get(name) == signature:
            return

        note("reflow %s order=%s attempt=%d" % (name, order, attempt))

        # Focus first: an emptied workspace that is not focused is reaped, and
        # the layout would then be built on another one.
        i3.command('workspace "%s"' % name)

        if len(order) == 1:
            # One window always fills the screen, whatever the tree looks like.
            i3.command("[con_id=%d] move container to workspace %s"
                       % (order[0], name))
        else:
            try:
                # Nothing is parked: i3 destroys an emptied workspace. The
                # structure is appended beside the windows and every window is
                # moved into its slot, so the workspace is never empty and the
                # orientation does not depend on what was there before.
                slots = build_layout(name, len(order))
                for index, con_id in enumerate(order):
                    if index < len(slots):
                        i3.command("[con_id=%d] move container to mark "
                                   "smd-slot-%d" % (con_id, index))
                    else:
                        i3.command("[con_id=%d] move container to workspace %s"
                                   % (con_id, name))
            finally:
                clear_slots(name)

        geometry = geometry_of(name)
        placed = [con_id for con_id in order if con_id in geometry]
        good = len(placed) == len(order) and expected_layout(order, geometry)
        note("  placed: %s" % " ".join(
            "%d@%d,%d+%dx%d" % ((con_id,) + geometry[con_id])
            for con_id in placed))
        leftover = [n["id"] for n in nodes_of(find_workspace(i3.tree(), name) or {})
                    if str(n.get("name", "")).startswith("smd-slot-")]
        if leftover:
            note("  placeholders still open: %s" % leftover)
        if good:
            state["settled"][name] = signature
            return
        if attempt < 2:
            # i3 applies commands through a queue: one retry is allowed, and
            # only when the result really is wrong.
            note("  layout not as expected, retrying once")
            time.sleep(0.4)
            reflow(name, attempt + 1)
        else:
            note("  layout still not as expected")
            state["settled"][name] = signature

'''

t = t[:start] + new + t[end:]

# State gains the settled set and the workspace each window belongs to.
t = t.replace('''    state = {"order": {}, "busy": False, "pending": set(),
             "last": {}, "last_time": {}}''',
              '''    state = {"order": {}, "busy": False, "pending": set(),
             "settled": {}, "where": {}}''', 1)

# Placeholder events are recognised by their prefix, and the ids the helper
# created are ignored outright: marks only exist after the slots are marked.
t = t.replace('''        if container.get("name") == "smd-slot" or any(
                m.startswith("smd-slot") for m in marks):''',
              '''        if str(container.get("name", "")).startswith("smd-slot") \\
                or any(str(m).startswith("smd-slot") for m in marks) \\
                or container.get("id") in state["slots"]:''', 1)

# A closing window is already gone from the tree, so its workspace is taken
# from the record kept while it existed.
t = t.replace('''            tree = i3.tree()
            workspace = (workspace_containing(tree, con_id) if con_id else None) \\
                or focused_workspace(tree)''',
              '''            tree = i3.tree()
            workspace = (workspace_containing(tree, con_id) if con_id else None) \\
                or ({"name": state["where"][con_id]}
                    if state["where"].get(con_id) else None) \\
                or focused_workspace(tree)''', 1)

# build_layout records the placeholders it created.
t = t.replace('''        placed = []
        for node in slots:''',
              '''        placed = []
        state["slots"] = {node["id"] for node in slots}
        for node in slots:''', 1)

p.write_bytes(t.encode("utf-8"))
print("reflow reworked")
