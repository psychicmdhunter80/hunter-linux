#!/usr/bin/env python3
"""Reproduce the 1.7 window rules in a booted live session.

Two windows on a workspace, ten workspaces, a third window that opens on the
next empty one, the overflow exception when none is left, the workspace walk
on Ctrl+Alt+Left/Right and the panel's ten workspace buttons are all exercised here.

Brave windows cover the layouts - they are what the owner actually uses - and
ordinary xfce4-terminal launches cover navigation, the ten-workspace limit and
exhaustion, where more windows are needed than a browser test should start.

Evidence captured per stage: helper log (including how many times it had to
act), the number of helper processes, and the i3 tree.  A stage counts as
stable only if the window rectangles stop changing: the tree is sampled
repeatedly and the number of distinct layouts is reported, so a
correct-looking screenshot cannot pass on its own.

Usage: tile-brave.py <iso> <work dir> [mode]
"""

import json
import os
import re
import socket
import subprocess
import sys
import time

ISO = sys.argv[1]
WORK = sys.argv[2] if len(sys.argv) > 2 else "out-brave"
MODE = sys.argv[3] if len(sys.argv) > 3 else "uefi"

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HELPER = os.path.join(REPO, "config/includes.chroot/usr/local/bin/hunter-autotile")

MON_PORT = 4700
SER_PORT = 4701
HTTP_PORT = 4801

os.makedirs(WORK, exist_ok=True)
RESULT = os.path.join(WORK, "result.txt")
STEPS = os.path.join(WORK, "steps.txt")
results = []


def record(line):
    results.append(line)
    print(line, flush=True)


def note(line):
    with open(STEPS, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    print(line, flush=True)


class Channel:
    def __init__(self, port):
        deadline = time.time() + 60
        while True:
            try:
                self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
                break
            except OSError:
                if time.time() > deadline:
                    raise
                time.sleep(0.5)
        self.sock.settimeout(3)
        self.data = ""

    def send(self, text):
        self.sock.sendall(text.encode())

    def expect(self, pattern, timeout=120):
        regex = re.compile(pattern, re.S)
        deadline = time.time() + timeout
        while True:
            match = regex.search(self.data)
            if match:
                text = match.group(0)
                self.data = self.data[match.end():]
                return text
            if time.time() > deadline:
                return None
            try:
                chunk = self.sock.recv(65536)
            except socket.timeout:
                continue
            except OSError:
                return None
            if not chunk:
                return None
            self.data += chunk.decode("utf-8", "replace")


class Shell:
    def __init__(self, chan):
        self.chan = chan
        self.counter = 0

    def login(self, timeout=900):
        if not self.chan.expect(r"login:", timeout=timeout):
            record("FAIL: no login prompt on the serial console")
            return False
        self.chan.send("user\r")
        if self.chan.expect(r"[Pp]assword:", timeout=60):
            self.chan.send("live\r")
        if not self.chan.expect(r"[$#] ", timeout=120):
            record("FAIL: could not log in on the serial console")
            return False
        record("PASS: logged in on the serial console")
        return True

    def run(self, command, timeout=180, lines=60):
        self.counter += 1
        begin = "HUNTERMARK%dBEGIN" % self.counter
        end = "HUNTERMARK%dEND" % self.counter
        wrapped = ('echo "%s""%s"; (%s) 2>&1 | head -%d; echo "%s""%s"'
                   % (begin[:10], begin[10:], command, lines, end[:10], end[10:]))
        self.chan.send(wrapped + "\r")
        text = self.chan.expect(re.escape(begin) + r"(.*?)" + re.escape(end),
                                timeout=timeout)
        if text is None:
            note("$ %s\n<bounded timeout after %ss>" % (command, timeout))
            return ""
        text = re.sub(r"\r", "", text)
        text = text[len(begin):-len(end)].strip()
        note("$ %s\n%s" % (command, text))
        return text

    def wait_for_x(self, timeout=600):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if "READY" in self.run(
                    "DISPLAY=:0 xdpyinfo >/dev/null 2>&1 && echo READY || echo WAIT",
                    timeout=60):
                record("PASS: the X display is up")
                self.run("DISPLAY=:0 xset s off -dpms >/dev/null 2>&1; "
                         "DISPLAY=:0 xset s noblank >/dev/null 2>&1; echo BLANKING=off",
                         timeout=60)
                return True
            time.sleep(10)
        record("FAIL: the X display never came up")
        return False


def start_qemu():
    accel = "kvm" if os.access("/dev/kvm", os.W_OK) else "tcg"
    record("accelerator: %s" % accel)
    # Craig's Chromebook is 1366x768, so the guest is given exactly that screen
    # through the emulated VGA's EDID instead of QEMU's 1280x800 default: a
    # layout that only fits a larger screen would not be his behaviour.
    args = ["qemu-system-x86_64", "-m", "2048", "-smp", "2", "-accel", accel,
            "-display", "none", "-no-reboot",
            "-device", "VGA,edid=on,xres=1366,yres=768,vgamem_mb=16",
            "-monitor", "tcp:127.0.0.1:%d,server,nowait" % MON_PORT,
            "-serial", "tcp:127.0.0.1:%d,server,nowait" % SER_PORT,
            "-netdev", "user,id=n0", "-device", "virtio-net-pci,netdev=n0"]
    if MODE == "uefi":
        code = next((p for p in ("/usr/share/OVMF/OVMF_CODE_4M.fd",
                                 "/usr/share/OVMF/OVMF_CODE.fd",
                                 "/usr/share/edk2/ovmf/OVMF_CODE.fd")
                     if os.path.exists(p)), None)
        var_src = next((p for p in ("/usr/share/OVMF/OVMF_VARS_4M.fd",
                                    "/usr/share/OVMF/OVMF_VARS.fd",
                                    "/usr/share/edk2/ovmf/OVMF_VARS.fd")
                        if os.path.exists(p)), None)
        if not code or not var_src:
            record("FAIL: no OVMF firmware found")
            return None
        variables = os.path.join(WORK, "OVMF_VARS.fd")
        subprocess.run(["cp", var_src, variables], check=True)
        args += ["-machine", "q35",
                 "-drive", "if=pflash,format=raw,readonly=on,file=%s" % code,
                 "-drive", "if=pflash,format=raw,file=%s" % variables]
    else:
        args += ["-boot", "d"]
    args += ["-cdrom", ISO]
    log = open(os.path.join(WORK, "qemu.log"), "w", encoding="utf-8")
    return subprocess.Popen(args, stdout=log, stderr=log)


BOX = re.compile(r"WIN id=\d+ .*?xid=(\d+) class=(\S+) .*?ws=(\d+) "
                 r".*?rect=(-?\d+),(-?\d+)\+(\d+)x(\d+)")
# Only the browser windows are under test: the panel owns a real window too,
# and it is furniture, not a window the layout has to arrange.
UNDER_TEST = "brave"


def layouts(text):
    """The window rectangles from a tree dump, keyed by X id."""
    found = {}
    for match in BOX.finditer(text):
        xid = int(match.group(1))
        if not xid or not match.group(2).lower().startswith(UNDER_TEST):
            continue
        found[xid] = tuple(int(match.group(i)) for i in range(4, 8))
    return found


def spaces(text):
    """The workspace number of every window in a tree dump, keyed by X id."""
    return {int(match.group(1)): int(match.group(3)) for match in BOX.finditer(text)
            if int(match.group(1))}


def on_space(text, number):
    """The windows of the browser under test on one workspace."""
    where = spaces(text)
    return {xid: rect for xid, rect in layouts(text).items()
            if where.get(xid) == number}


def describe(found, labels=None):
    labels = labels or {}
    return " ".join("%s[%d,%d %dx%d]" % (labels.get(k, k), v[0], v[1], v[2], v[3])
                    for k, v in sorted(found.items()))


def main():
    for path in (RESULT, STEPS):
        if os.path.exists(path):
            os.unlink(path)

    qemu = start_qemu()
    if qemu is None:
        return 1
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(HTTP_PORT),
                               "--bind", "127.0.0.1", "--directory", REPO],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    passed = True
    try:
        time.sleep(3)
        shell = Shell(Channel(SER_PORT))
        if not shell.login() or not shell.wait_for_x():
            return 1

        def screen_now():
            """The current mode and the area i3 leaves for windows."""
            out = shell.run(
                "DISPLAY=:0 xrandr --current 2>/dev/null | grep -m1 '\\*' ; "
                "echo ---; DISPLAY=:0 xprop -root _NET_WORKAREA 2>/dev/null",
                timeout=90)
            chunks = out.split("---")
            mode = re.search(r"(\d+)x(\d+)", chunks[0])
            area = re.search(r"(\d+),\s*(\d+),\s*(\d+),\s*(\d+)",
                             chunks[1] if len(chunks) > 1 else "")
            if not mode:
                return None
            screen = (int(mode.group(1)), int(mode.group(2)))
            if area:
                work = tuple(int(area.group(i)) for i in range(1, 5))
            else:
                work = (0, 0, screen[0], screen[1] - 28)
            return screen, work

        # The emulated screen arrives at 1366x768 through EDID; if X landed on
        # another mode anyway it is switched, so every measurement below is
        # made at the size the owner actually has.
        measured = screen_now()
        if measured and measured[0] != (1366, 768):
            record("INFO: session started at %dx%d; switching to 1366x768"
                   % measured[0])
            shell.run(
                "DISPLAY=:0 xrandr --newmode '1366x768_60.00' 85.50 1366 1436 "
                "1579 1792 768 771 774 798 +hsync +vsync 2>/dev/null; "
                "o=$(DISPLAY=:0 xrandr --current | grep -m1 ' connected' "
                "| cut -d' ' -f1); "
                "DISPLAY=:0 xrandr --addmode \"$o\" 1366x768_60.00 2>/dev/null; "
                "DISPLAY=:0 xrandr --output \"$o\" --mode 1366x768_60.00; "
                "sleep 3", timeout=120)
            measured = screen_now()
        screen = measured[0] if measured else (0, 0)
        work = measured[1] if measured else (0, 0, 0, 0)
        record("INFO: screen %dx%d, window area %d,%d %dx%d (panel excluded)"
               % (screen[0], screen[1], work[0], work[1], work[2], work[3]))

        # The helper normally comes from the checkout so a fix can be tested
        # without rebuilding the image; TILE_HELPER=image tests the one that
        # actually ships inside the ISO instead.
        from_image = os.environ.get("TILE_HELPER", "checkout") == "image"
        source = ("install -m 755 /usr/local/bin/hunter-autotile /tmp/hunter-autotile"
                  if from_image else
                  "curl -fsS -m 30 http://10.0.2.2:%d/config/includes.chroot/usr/"
                  "local/bin/hunter-autotile -o /tmp/hunter-autotile" % HTTP_PORT)
        fetched = shell.run(
            source + " && echo HELPER=ok; "
            "curl -fsS -m 30 http://10.0.2.2:%d/tools/ci/tile-dump.py "
            "-o /tmp/tile-dump.py && echo DUMPER=ok; "
            "curl -fsS -m 30 http://10.0.2.2:%d/tools/ci/ws-dump.py "
            "-o /tmp/ws-dump.py && echo WSDUMP=ok" % (HTTP_PORT, HTTP_PORT),
            timeout=120)
        if "HELPER=ok" not in fetched or "WSDUMP=ok" not in fetched:
            record("FAIL: the helper could not be provided to the image")
            return 1
        record("INFO: helper under test: %s" % ("from the image"
                                                if from_image else "from the checkout"))
        shell.run("chmod +x /tmp/hunter-autotile /tmp/tile-dump.py "
                  "/tmp/ws-dump.py; "
                  "python3 -c \"import ast;ast.parse(open('/tmp/hunter-autotile').read())"
                  " ;print('SYNTAX=ok')\"", timeout=120)

        # A clean slate: no browser, no helper, empty log.
        shell.run("pkill -x brave; pkill -x brave-browser; "
                  "pkill -f 'hunter-auto[t]ile'; sleep 2; "
                  ": > ~/.cache/smd/autotile.log; "
                  "rm -rf ~/.config/BraveSoftware; echo CLEAN=done", timeout=120)
        shell.run("DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/1000 "
                  "setsid /tmp/hunter-autotile </dev/null >>/tmp/at.log 2>&1 & "
                  "sleep 4; echo HELPERS=$(pgrep -fc 'hunter-auto[t]ile'); "
                  "tail -2 ~/.cache/smd/autotile.log", timeout=120)
        shell.run("DISPLAY=:0 i3-msg 'workspace 1' >/dev/null; echo WS=1", timeout=60)

        def tree():
            return shell.run("DISPLAY=:0 python3 /tmp/tile-dump.py", timeout=120,
                             lines=200)

        def reflows():
            # 1.7 has no rebuild to count: the helper acts only when a window
            # would make a third, so this counts the actions it took and
            # reports them next to the layout for the evidence.
            out = shell.run("grep -c 'was full' ~/.cache/smd/autotile.log "
                            "2>/dev/null || echo 0", timeout=60)
            return int(out.strip().splitlines()[-1] or 0) if out.strip() else 0

        def helpers():
            out = shell.run("pgrep -fc 'hunter-auto[t]ile' || echo 0", timeout=60)
            return out.strip().splitlines()[-1] if out.strip() else "?"

        names = {}

        def labels_for(found):
            return {xid: label for label, xid in names.items() if xid in found}

        def brave_windows():
            out = shell.run("DISPLAY=:0 xdotool search --class Brave-browser "
                            "2>/dev/null | sort -n | tr '\\n' ' '", timeout=60)
            return [w for w in out.replace("\n", " ").split() if w.isdigit()]

        def open_brave(name, first=False):
            """Start Brave, wait for its new window and give it a known title.

            Brave's windows carry the page title, which changes as it loads, so
            the harness names them itself: the tiling tests need a stable way
            to say which window they mean.
            """
            before = set(brave_windows())
            flag = "" if first else "--new-window "
            started = shell.run(
                "b=$(command -v brave || command -v brave-browser || echo NONE); "
                "echo BIN=$b; [ \"$b\" = NONE ] && exit 0; "
                "DISPLAY=:0 setsid \"$b\" %sabout:blank >/tmp/brave.log 2>&1 & "
                "sleep 2; echo STARTED" % flag, timeout=120)
            record("INFO: %s: %s" % (name, " ".join(started.split())[:200]))
            win = ""
            for _attempt in range(20):
                time.sleep(3)
                new = brave_windows()
                fresh = [w for w in new if w not in before]
                if fresh:
                    win = fresh[-1]
                    break
            note("brave windows now: %s" % " ".join(brave_windows()))
            record("INFO: %s: brave processes=%s new window=%s"
                   % (name, shell.run("pgrep -c -x brave || echo 0", timeout=60).strip(),
                      win or "none"))
            if win:
                names[name] = int(win)
                # A readable title is set on both properties so screenshots and
                # logs stay legible; identification does not depend on it.
                shell.run("DISPLAY=:0 xdotool set_window --name %s %s; "
                          "DISPLAY=:0 xprop -id %s -f _NET_WM_NAME 8u -set "
                          "_NET_WM_NAME %s >/dev/null 2>&1; sleep 3"
                          % (name, win, win, name), timeout=60)
            else:
                record("FAIL: no Brave window appeared for %s" % name)
                log = shell.run("tail -6 /tmp/brave.log 2>/dev/null; "
                                "pgrep -a brave | head -3", timeout=60)
                record("INFO: brave output: " + " | ".join(log.split())[:300])
            return win

        def stage(label, idle=0):
            text = tree()
            found = layouts(text)
            record("INFO: %s: %s" % (label, describe(found, labels_for(found))))
            record("INFO: %s: helpers=%s reflows=%s" % (label, helpers(), reflows()))
            if idle:
                seen = set()
                for _step in range(idle):
                    time.sleep(2)
                    seen.add(json.dumps(layouts(tree()), sort_keys=True))
                record("INFO: %s: %d distinct layouts in %ds idle"
                       % (label, len(seen), idle * 2))
                record(("PASS: %s stays put while idle" % label) if len(seen) == 1
                       else ("FAIL: %s keeps changing while idle" % label))
                return found, len(seen) == 1
            return found, True

        def ok(label, condition, detail=""):
            nonlocal passed
            record(("PASS: " if condition else "FAIL: ") + label
                   + ((" - " + str(detail)) if detail else ""))
            passed = passed and condition
            return condition

        ok("the session runs at Craig's 1366x768", screen == (1366, 768),
           "%dx%d" % screen)
        ok("the panel is accounted for in the window area",
           work[2] == 1366 and work[3] < 768 and work[3] > 700,
           "%d,%d %dx%d" % work)

        # --- 1.7: two tiled windows per workspace --------------------------
        # The rule: the first window fills a workspace, the second makes two
        # equal halves in arrival order, a third opens on the next empty
        # workspace instead - and is shown there - and a window moved into a
        # full workspace stays there floating, with a notification.  Nothing
        # below settles anything with a fullscreen toggle or a synthetic
        # event: every arrangement has to follow from the launch, close or
        # move itself.

        def dump():
            return shell.run("DISPLAY=:0 python3 /tmp/ws-dump.py", timeout=120,
                             lines=200)

        def state():
            """(focused workspace, {number: (tiled, floating)}, highest)."""
            focused, held, highest = None, {}, 0
            for line in dump().splitlines():
                words = line.split()
                if not words:
                    continue
                if words[0] == "FOCUSED" and len(words) > 1:
                    try:
                        focused = int(words[1])
                    except ValueError:
                        pass
                elif words[0] == "MAX" and len(words) > 1:
                    try:
                        highest = int(words[1])
                    except ValueError:
                        pass
                elif words[0] == "WS" and len(words) > 1:
                    fields = dict(word.split("=", 1) for word in words[2:]
                                  if "=" in word)
                    try:
                        held[int(words[1])] = (int(fields.get("tiled", 0)),
                                               int(fields.get("floating", 0)))
                    except ValueError:
                        continue
                    highest = max(highest, int(words[1]))
            return focused, held, highest

        def windows():
            """{title: (workspace, tiled)} for every real window."""
            found = {}
            for line in dump().splitlines():
                if not line.startswith("WIN "):
                    continue
                head, _sep, title = line.partition(" name=")
                fields = dict(word.split("=", 1) for word in head.split()[1:]
                              if "=" in word)
                try:
                    found[title.strip()] = (int(fields.get("ws", 0)),
                                            fields.get("tiled") == "1")
                except ValueError:
                    continue
            return found

        def placement(window_id):
            """(workspace, tiled?) of one window, by id, or (None, None)."""
            for line in dump().splitlines():
                if not line.startswith("WIN "):
                    continue
                head = line.partition(" name=")[0]
                fields = dict(word.split("=", 1) for word in head.split()[1:]
                              if "=" in word)
                if str(fields.get("id")) == str(window_id):
                    return int(fields.get("ws", 0)), fields.get("tiled") == "1"
            return None, None

        def notifications():
            """How many desktop notification bubbles are on screen."""
            for line in dump().splitlines():
                if line.startswith("NOTIFY "):
                    return int(line.split()[1])
            return 0

        def wait_for(want, timeout=90):
            """Poll the workspace state until want(focused, held, highest)."""
            started = time.time()
            seen = state()
            while time.time() - started < timeout:
                seen = state()
                if want(*seen):
                    return seen, True
                time.sleep(2)
            return seen, False

        def screen_of(window_id):
            out = shell.run("DISPLAY=:0 xwininfo -id %s | grep 'Map State'"
                            % window_id, timeout=60)
            return out.strip()

        def switch(number):
            shell.run("DISPLAY=:0 i3-msg -q 'workspace --no-auto-back-and-forth "
                      "number %d'" % number, timeout=60)
            time.sleep(2)

        def send(window_id, target):
            """Move a window the way the owner does: focus it, then move it."""
            here, _tiled = placement(window_id)
            if here is None:
                return False
            if here != target:
                switch(here)
                shell.run("DISPLAY=:0 xdotool windowactivate --sync %s; sleep 1; "
                          "DISPLAY=:0 i3-msg -q 'move container to workspace "
                          "number %d'" % (window_id, target), timeout=90)
                time.sleep(2)
            return True

        def two_halves(found):
            if len(found) != 2:
                return False
            first, second = list(found.values())
            return (abs(first[2] - second[2]) <= 4
                    and abs(first[1] - second[1]) <= 4
                    and first[0] < second[0])

        def wait_shape(number, predicate, timeout=60):
            """Poll until a *shown* workspace really has the wanted shapes.

            i3 does not re-lay-out a workspace that is not on screen, so a
            workspace measured while it is hidden reports stale rectangles.
            The workspace is shown first, then measured until it settles.
            """
            switch(number)
            started = time.time()
            found = on_space(tree(), number)
            while time.time() - started < timeout:
                found = on_space(tree(), number)
                if predicate(found):
                    return found, True
                time.sleep(2)
            return found, False

        def fills(found):
            if len(found) != 1:
                return False
            x, y, w, h = list(found.values())[0]
            return (abs(x - work[0]) <= 2 and abs(y - work[1]) <= 2
                    and abs(w - work[2]) <= 4 and abs(h - work[3]) <= 4)

        open_brave("smd-one", first=True)
        one, _stable_one = stage("one window")
        ok("the first window fills the desktop", fills(one),
           describe(one, labels_for(one)))

        open_brave("smd-two")
        two, stable_two = stage("two windows", idle=10)
        first, second = names.get("smd-one"), names.get("smd-two")
        ok("the second window makes two equal halves", two_halves(two)
           and first in two and second in two,
           describe(two, labels_for(two)))
        ok("the first window stays on the left, the second on the right",
           first in two and second in two and two[first][0] < two[second][0],
           describe(two, labels_for(two)))
        ok("two windows settle and stay put", stable_two)

        open_brave("smd-three")
        overflow, overflow_ok = wait_for(
            lambda focused, held, highest: focused == 2
            and held.get(2, (0, 0))[0] == 1)
        ok("a third window opens on the next empty workspace", overflow_ok,
           "focused=%s held=%s" % (overflow[0],
                                   sorted(overflow[1].items())))
        left_behind = on_space(tree(), 1)
        ok("the workspace it left still shows two equal halves",
           two_halves(left_behind) and names.get("smd-one") in left_behind,
           describe(left_behind, labels_for(left_behind)))
        ok("the application is on screen where it opened, not hidden",
           "IsViewable" in screen_of(names.get("smd-three")),
           screen_of(names.get("smd-three")) or "not found")

        open_brave("smd-four")
        pair, pair_ok = wait_for(
            lambda focused, held, highest: focused == 2
            and held.get(2, (0, 0))[0] == 2)
        ok("a fourth window splits that workspace into halves", pair_ok,
           "focused=%s held=%s" % (pair[0], sorted(pair[1].items())))
        ws_two = on_space(tree(), 2)
        three, four = names.get("smd-three"), names.get("smd-four")
        ok("the overflowed workspace holds two equal halves in arrival order",
           two_halves(ws_two) and three in ws_two and four in ws_two
           and ws_two[three][0] < ws_two[four][0], describe(ws_two))

        # An empty workspace chosen by hand keeps the program opened there:
        # no spare slot elsewhere is filled and nothing is pulled back.
        switch(5)
        open_brave("smd-five")
        chosen, chosen_ok = wait_for(
            lambda focused, held, highest: focused == 5
            and held.get(5, (0, 0))[0] == 1)
        ok("an application opened on a chosen empty workspace stays there",
           chosen_ok, "focused=%s held=%s" % (chosen[0],
                                              sorted(chosen[1].items())))
        ok("it fills that workspace", fills(on_space(tree(), 5)),
           describe(on_space(tree(), 5), labels_for(on_space(tree(), 5))))
        ok("the workspaces it did not touch keep their windows",
           len(on_space(tree(), 1)) == 2 and len(on_space(tree(), 2)) == 2,
           describe(on_space(tree(), 1)) + " | " + describe(on_space(tree(), 2)))

        # Closing a window expands its neighbour and moves nothing else.
        switch(1)
        shell.run("DISPLAY=:0 xdotool windowclose %s; sleep 6"
                  % names.get("smd-two"), timeout=90)
        closed, closed_ok = wait_for(
            lambda focused, held, highest: held.get(1, (0, 0))[0] == 1)
        ok("closing one window lets its neighbour fill the workspace",
           closed_ok and fills(on_space(tree(), 1)),
           describe(on_space(tree(), 1), labels_for(on_space(tree(), 1))))
        ok("closing it leaves the other workspaces exactly as they were",
           len(on_space(tree(), 2)) == 2 and len(on_space(tree(), 5)) == 1,
           describe(on_space(tree(), 2)) + " | "
           + describe(on_space(tree(), 5)))

        # A second tab is not a second window: it takes no tiled slot.
        switch(2)
        shell.run("DISPLAY=:0 i3-msg -q '[id=%s] focus'; sleep 1"
                  % names.get("smd-three"), timeout=60)
        shell.run("DISPLAY=:0 xdotool key ctrl+t; sleep 3; "
                  "DISPLAY=:0 xdotool key ctrl+l; "
                  "DISPLAY=:0 xdotool type 'about:blank'; "
                  "DISPLAY=:0 xdotool key Return; sleep 5", timeout=120)
        tabbed = state()
        ok("a second browser tab is not a second window",
           tabbed[1].get(2, (0, 0))[0] == 2 and tabbed[2] <= 10
           and len(on_space(tree(), 2)) == 2,
           "focused=%s held=%s" % (tabbed[0], sorted(tabbed[1].items())))

        # An ordinary dialog floats and takes no slot.
        opened = shell.run(
            "DISPLAY=:0 setsid zenity --info --title='SMD dialog test' "
            "--text='SMD dialog test' --no-wrap >/tmp/dialog.log 2>&1 & "
            "sleep 6; DISPLAY=:0 xdotool search --onlyvisible --name "
            "'SMD dialog test' 2>/dev/null | head -1", timeout=120)
        dialog_id = (opened.strip().splitlines() or [""])[-1].strip()
        geometry = ""
        if dialog_id.isdigit():
            geometry = shell.run("DISPLAY=:0 xwininfo -id %s "
                                 "| grep -E 'Width:|Height:'" % dialog_id,
                                 timeout=60)
        dims = dict(re.findall(r"(Width|Height):\s*(\d+)", geometry))
        dialog_w = int(dims.get("Width", 0))
        dialog_h = int(dims.get("Height", 0))
        dialog_state = state()
        ok("an ordinary dialog floats instead of taking a tile",
           dialog_id.isdigit() and dialog_w >= 100 and dialog_h >= 40
           and dialog_state[1].get(2, (0, 0))[0] == 2
           and dialog_state[1].get(2, (0, 0))[1] >= 1,
           "%s %dx%d, held=%s" % (dialog_id or "not found", dialog_w, dialog_h,
                                  sorted(dialog_state[1].items())))
        ok("the dialog changes no window's place",
           len(on_space(tree(), 2)) == 2
           and names.get("smd-three") in on_space(tree(), 2),
           describe(on_space(tree(), 2)))
        shell.run("pkill -x zenity; sleep 3", timeout=60)

        # A floating window does not consume an ordinary slot.
        switch(5)
        shell.run("DISPLAY=:0 i3-msg -q '[id=%s] floating enable'; sleep 4"
                  % names.get("smd-five"), timeout=60)
        floated, floated_ok = wait_for(
            lambda focused, held, highest: held.get(5, (0, 0))[0] == 0)
        ok("a floating window leaves the tiled slot free", floated_ok,
           "held=%s" % sorted(floated[1].items()))
        open_brave("smd-six")
        sixth, sixth_ok = wait_for(
            lambda focused, held, highest: focused == 5
            and held.get(5, (0, 0))[0] == 1)
        ok("so the next application still opens on that workspace", sixth_ok,
           "focused=%s held=%s" % (sixth[0], sorted(sixth[1].items())))
        shell.run("DISPLAY=:0 i3-msg -q '[id=%s] floating disable'; sleep 5"
                  % names.get("smd-five"), timeout=60)
        rejoined, rejoined_ok = wait_for(
            lambda focused, held, highest: held.get(5, (0, 0))[0] == 2)
        ws_five = on_space(tree(), 5)
        ok("tiling it again makes the pair of halves",
           rejoined_ok and two_halves(ws_five), describe(ws_five))

        # Fullscreen must not push anything onto another workspace.
        switch(2)
        shell.run("DISPLAY=:0 i3-msg -q '[id=%s] fullscreen enable'; sleep 4"
                  % names.get("smd-three"), timeout=60)
        during = state()
        ok("going fullscreen keeps both windows on their workspace",
           during[1].get(2, (0, 0))[0] == 2 and during[2] <= 10,
           "focused=%s held=%s" % (during[0], sorted(during[1].items())))
        shell.run("DISPLAY=:0 i3-msg -q '[id=%s] fullscreen disable'; sleep 4"
                  % names.get("smd-three"), timeout=60)
        restored, restored_ok = wait_for(
            lambda focused, held, highest: held.get(2, (0, 0))[0] == 2)
        ws_two = on_space(tree(), 2)
        ok("leaving fullscreen restores the two halves in order",
           restored_ok and two_halves(ws_two) and three in ws_two
           and four in ws_two and ws_two[three][0] < ws_two[four][0],
           describe(ws_two))

        # --- ordinary moves, both ends, with nothing triggered afterwards --
        switch(1)
        send(names.get("smd-one"), 7)
        moved, moved_ok = wait_for(
            lambda focused, held, highest: focused == 1
            and held.get(1, (0, 0))[0] == 0
            and held.get(7, (0, 0))[0] == 1)
        ok("a window moved to an empty workspace leaves the old one empty",
           moved_ok, "focused=%s held=%s" % (moved[0], sorted(moved[1].items())))
        ok("moving it in the background did not take the focus", moved[0] == 1,
           "focused=%s" % moved[0])
        alone, alone_ok = wait_shape(7, fills)
        ok("and it fills that workspace once it is shown", alone_ok,
           describe(alone, labels_for(alone)))

        switch(2)
        send(names.get("smd-four"), 7)
        after_second = state()[0]
        ok("the second move did not take the focus either", after_second == 2,
           "focused=%s" % after_second)
        pair7, pair7_ok = wait_shape(7, two_halves)
        ok("a window moved beside one window makes two halves", pair7_ok,
           describe(pair7, labels_for(pair7)))

        switch(2)
        send(names.get("smd-three"), 7)   # that workspace now holds two
        where_three, tiled_three = placement(names.get("smd-three"))
        ok("a window moved into a full workspace stays there floating",
           where_three == 7 and tiled_three is False,
           "workspace=%s tiled=%s" % (where_three, tiled_three))
        ok("and the owner is notified on screen", notifications() >= 1,
           "%s notification window(s)" % notifications())
        marks = shell.run("DISPLAY=:0 i3-msg -t get_marks", timeout=60)
        ok("the overflow window is marked so it can be recognised",
           "smd-overflow" in marks, marks.strip()[:120])
        leftover, leftover_ok = wait_shape(7, two_halves)
        ok("nothing that was already on the full workspace was moved",
           leftover_ok and names.get("smd-one") in leftover
           and names.get("smd-four") in leftover,
           describe(leftover, labels_for(leftover)))
        said = shell.run("grep -c 'stays floating' ~/.cache/smd/autotile.log",
                         timeout=60)
        ok("the helper records why the window is floating",
           said.strip().splitlines()[-1:] == ["1"], said.strip()[:120])
        record("INFO: autotile log: " + " | ".join(
            shell.run("tail -8 ~/.cache/smd/autotile.log 2>/dev/null").split())[:500])

        # --- the scratchpad, which is i3's own and must keep working --------
        # Workspace 5 holds its two halves, so hiding one of them must free a
        # slot, showing it again must float it over the same workspace, and
        # hiding it again must leave exactly the state it started in.
        switch(5)
        before = state()[1].get(5, (0, 0))
        shell.run("DISPLAY=:0 i3-msg -q '[title=\"smd-six\"] move scratchpad'; "
                  "sleep 4", timeout=60)
        hidden = state()
        ok("a window sent to the scratchpad leaves its workspace",
           hidden[1].get(5, (0, 0)) == (before[0] - 1, 0),
           "was=%s now=%s" % (before, sorted(hidden[1].items())))
        shell.run("DISPLAY=:0 i3-msg -q 'scratchpad show'; sleep 4", timeout=60)
        shown = state()
        ok("showing it floats over the workspace without taking a slot",
           shown[0] == 5 and shown[1].get(5, (0, 0)) == (before[0] - 1, 1),
           "focused=%s held=%s" % (shown[0], sorted(shown[1].items())))
        ok("and no other workspace was used to hold it",
           shown[2] <= 10 and set(shown[1]) <= {2, 5, 7},
           "highest=%s held=%s" % (shown[2], sorted(shown[1].items())))
        shell.run("DISPLAY=:0 i3-msg -q '[title=\"smd-six\"] move scratchpad'; "
                  "sleep 4", timeout=60)
        back = state()
        ok("hiding it again leaves the workspace exactly as it was",
           back[1].get(5, (0, 0)) == (before[0] - 1, 0)
           and back[0] == 5,
           "focused=%s held=%s" % (back[0], sorted(back[1].items())))

        # --- navigation and the ten-workspace limit, ordinary launches -----
        shell.run("pkill -x brave; pkill -x brave-browser; sleep 3; "
                  "pkill -x xfce4-terminal; sleep 2", timeout=90)
        switch(1)

        def term(title, workspace=None):
            if workspace is not None:
                switch(workspace)
            shell.run("setsid env DISPLAY=:0 xfce4-terminal --title=%s "
                      "</dev/null >/dev/null 2>&1 &" % title, timeout=60)
            started = time.time()
            while time.time() - started < 45:
                time.sleep(2)
                found = windows()
                if title in found:
                    return found[title][0]
            record("INFO: %s never appeared" % title)
            return None

        def close_title(title):
            for line in dump().splitlines():
                if not line.startswith("WIN "):
                    continue
                head, _sep, name = line.partition(" name=")
                fields = dict(word.split("=", 1) for word in head.split()[1:]
                              if "=" in word)
                if name.strip() == title:
                    shell.run("DISPLAY=:0 xdotool windowclose %s"
                              % fields.get("id"), timeout=60)
            time.sleep(3)

        def nav(action):
            # The serial console has no DISPLAY of its own; the helper asks i3
            # through i3-msg, which needs to know which X server to ask.
            shell.run("DISPLAY=:0 hunter-workspaces-nav %s" % action,
                      timeout=60)
            time.sleep(2)
            return state()[0]

        for title, place in (("nav-one", 1), ("nav-four", 4), ("nav-seven", 7)):
            term(title, place)
        placed_ok = all(windows().get(title, (None,))[0] == place
                        for title, place in (("nav-one", 1), ("nav-four", 4),
                                             ("nav-seven", 7)))
        ok("three applications are open on workspaces 1, 4 and 7", placed_ok,
           sorted((title, windows().get(title)) for title in
                  ("nav-one", "nav-four", "nav-seven")))

        switch(1)
        walked = [nav("next") for _ in range(3)]
        ok("Ctrl+Alt+Right visits the occupied workspaces in numerical order, "
           "wrapping round", walked == [4, 7, 1], walked)
        walked = [nav("prev") for _ in range(3)]
        ok("Ctrl+Alt+Left visits them backwards, wrapping round",
           walked == [7, 4, 1], walked)
        switch(5)
        ok("from an empty workspace, Right finds the next occupied one",
           nav("next") == 7, "landed on %s" % state()[0])
        switch(5)
        ok("and Left finds the one before it", nav("prev") == 4,
           "landed on %s" % state()[0])

        close_title("nav-four")
        close_title("nav-seven")
        switch(3)
        ok("with only one occupied workspace, Right stays on it",
           nav("next") == 1)
        switch(3)
        ok("and so does Left", nav("prev") == 1)
        switch(1)
        ok("from that workspace itself it stays put too", nav("next") == 1)

        close_title("nav-one")
        switch(3)
        ok("with nothing open at all the view does not move", nav("next") == 3)
        ok("nor does Left move it", nav("prev") == 3)

        # Ten workspaces, then safe exhaustion: every one holds a window and
        # the current one already holds two.
        for number in range(1, 11):
            term("fill-%d-a" % number, number)
            if number == 10:
                term("fill-10-b", 10)
        filled = state()[1]
        ok("applications open on all ten workspaces",
           all(filled.get(number, (0, 0))[0] >= 1 for number in range(1, 11)),
           sorted((number, filled.get(number)) for number in range(1, 11)))
        ok("the desktop never grows an eleventh workspace", state()[2] <= 10,
           state()[2])

        switch(10)
        term("exhaust", None)
        exhausted, exhausted_ok = wait_for(
            lambda focused, held, highest: focused == 10
            and windows().get("exhaust", (None, True))[1] is False, timeout=120)
        ok("with every workspace full a new window is kept, floating",
           exhausted_ok, "focused=%s held=%s"
           % (exhausted[0], sorted(exhausted[1].items())))
        ok("no eleventh workspace was created to hold it",
           exhausted[2] <= 10, exhausted[2])
        ok("and the owner is notified that no workspace is empty",
           notifications() >= 1, "%s notification window(s)" % notifications())
        marks = shell.run("DISPLAY=:0 i3-msg -t get_marks", timeout=60)
        ok("the exhausted window is marked as overflow",
           "smd-overflow" in marks, marks.strip()[:120])
        said = shell.run("grep -c 'no workspace is empty' "
                         "~/.cache/smd/autotile.log", timeout=60)
        ok("the helper says that no workspace is empty",
           said.strip().splitlines()[-1:] == ["1"], said.strip()[:120])

        # Overflow with gaps and wraparound: 1-9 are emptied, 10 stays full,
        # so the next empty workspace after 10 is 1.
        for number in range(1, 10):
            close_title("fill-%d-a" % number)
        switch(10)
        term("wrap", None)
        wrapped, wrapped_ok = wait_for(
            lambda focused, held, highest: focused == 1
            and held.get(1, (0, 0))[0] == 1, timeout=120)
        ok("the overflow wraps from workspace 10 round to workspace 1",
           wrapped_ok, "focused=%s held=%s" % (wrapped[0],
                                               sorted(wrapped[1].items())))
        term("gap-a", None)
        gap, gap_ok = wait_for(
            lambda focused, held, highest: focused == 1
            and held.get(1, (0, 0))[0] == 2)
        term("gap-b", None)
        gapped, gapped_ok = wait_for(
            lambda focused, held, highest: focused == 2
            and held.get(2, (0, 0))[0] == 1, timeout=120)
        ok("with a gap, the next empty workspace in numerical order is used",
           gap_ok and gapped_ok, "focused=%s held=%s"
           % (gapped[0], sorted(gapped[1].items())))

        # Repeated launch/close cycles: nothing accumulates, no workspace is
        # invented and the helper never doubles up.
        for round_number in (1, 2):
            switch(3)
            term("cycle-%d-a" % round_number, 3)
            term("cycle-%d-b" % round_number, 3)
            term("cycle-%d-c" % round_number, None)
            started = time.time()
            target = None
            while time.time() - started < 90:
                focused, held, highest = state()
                if focused not in (3, None) and held.get(focused, (0, 0))[0] == 1:
                    target = focused
                    break
                time.sleep(2)
            ok("round %d: the third window overflowed to workspace %s"
               % (round_number, target or "?"), target is not None,
               "focused=%s held=%s" % (state()[0], sorted(state()[1].items())))
            for title in ("cycle-%d-a" % round_number,
                          "cycle-%d-b" % round_number,
                          "cycle-%d-c" % round_number):
                close_title(title)

        # Extended idle: nothing may re-settle on its own.
        switch(4)
        term("idle", 4)
        seen = set()
        for _step in range(10):
            time.sleep(2)
            seen.add(json.dumps(state()[1], sort_keys=True))
        ok("the desktop is unchanged after twenty idle seconds",
           len(seen) == 1, "%d layouts" % len(seen))

        ok("exactly one tiling helper is running", helpers() == "1", helpers())
        errors = shell.run("grep -c 'error' ~/.cache/smd/autotile.log "
                           "2>/dev/null || echo 0", timeout=60)
        ok("the helper logged no error", errors.strip().splitlines()[-1:] == ["0"],
           errors.strip()[:120])
        ok("the desktop still has no workspace above ten", state()[2] <= 10,
           state()[2])

        # --- extended stability (1.7.1) -------------------------------------
        # 1.7.0 was signed off on twenty seconds of idle time.  This runs the
        # same policy through repeated cycles and then watches a settled
        # desktop for a quarter of an hour, recording focus, layout and helper
        # behaviour instead of trusting a single screenshot.
        if os.environ.get("STABILITY") == "1":
            minutes = int(os.environ.get("STABILITY_MINUTES", "15"))
            record("INFO: --- stability: interaction cycles, then %d minutes idle ---"
                   % minutes)

            def tree_signature():
                """What is on screen, exactly: window, workspace, geometry."""
                text = shell.run("DISPLAY=:0 i3-msg -t get_tree 2>/dev/null",
                                 timeout=90)
                try:
                    data = json.loads(text[text.index("{"):])
                except (ValueError, KeyError):
                    return None
                found = []

                def walk(node, workspace):
                    number = (node.get("num") if node.get("type") == "workspace"
                              else workspace)
                    if node.get("window"):
                        box = node.get("rect") or {}
                        found.append("%s@ws%s:%s,%s,%s,%s" % (
                            node.get("name"), number, box.get("x"), box.get("y"),
                            box.get("width"), box.get("height")))
                    for child in (node.get("nodes") or []) + \
                            (node.get("floating_nodes") or []):
                        walk(child, number)

                walk(data, None)
                return sorted(found)

            def focus():
                text = shell.run("DISPLAY=:0 i3-msg -t get_workspaces 2>/dev/null",
                                 timeout=60)
                try:
                    data = json.loads(text[text.index("["):])
                except (ValueError, KeyError):
                    return None
                for entry in data:
                    if entry.get("focused"):
                        return str(entry.get("num"))
                return None

            def helper_usage():
                """(percent CPU, resident kB) of the helper, or None."""
                text = shell.run("ps -o %cpu=,rss= -C hunter-autotile 2>/dev/null "
                                 "| head -1", timeout=60).split()
                if len(text) < 2:
                    return None
                try:
                    return (float(text[0]), int(text[1]))
                except ValueError:
                    return None

            def log_size():
                text = shell.run("wc -l < ~/.cache/smd/autotile.log 2>/dev/null",
                                 timeout=60).strip()
                return int(text) if text.isdigit() else -1

            for cycle in range(1, 6):
                shell.run("DISPLAY=:0 i3-msg -q 'workspace --no-auto-back-and-forth "
                          "number 1'", timeout=60)
                for suffix in ("a", "b", "c"):
                    shell.run("DISPLAY=:0 xfce4-terminal --title='SMD cycle %d %s' "
                              ">/dev/null 2>&1 &" % (cycle, suffix), timeout=60)
                    time.sleep(6)
                time.sleep(6)
                places = tree_signature() or []
                third = [entry for entry in places
                         if entry.startswith("SMD cycle %d c@" % cycle)]
                ok("cycle %d: the third window left workspace 1" % cycle,
                   bool(third) and "@ws1:" not in third[0], third[:1])
                shell.run("DISPLAY=:0 xdotool key --clearmodifiers ctrl+alt+Right",
                          timeout=60)
                time.sleep(4)
                stop = focus()
                shell.run("DISPLAY=:0 xdotool key --clearmodifiers ctrl+alt+Left",
                          timeout=60)
                time.sleep(4)
                ok("cycle %d: the occupied walk skipped the empty workspace and "
                   "came back" % cycle, stop not in (None, "1") and focus() == "1",
                   "stopped on %s, back on %s" % (stop, focus()))
                shell.run("DISPLAY=:0 i3-msg -q 'workspace --no-auto-back-and-forth "
                          "number 9'", timeout=60)
                time.sleep(3)
                ok("cycle %d: an empty workspace can be chosen directly" % cycle,
                   focus() == "9", focus())
                shell.run("DISPLAY=:0 i3-msg -q 'workspace --no-auto-back-and-forth "
                          "number 1'", timeout=60)
                time.sleep(3)
                shell.run("pkill -f 'SMD cycle %d' >/dev/null 2>&1; "
                          "pkill -x xfce4-terminal", timeout=60)
                time.sleep(5)
                ok("cycle %d: exactly one tiling helper is running" % cycle,
                   helpers() == "1", helpers())

            shell.run("DISPLAY=:0 i3-msg -q 'workspace --no-auto-back-and-forth "
                      "number 1'", timeout=60)
            shell.run("DISPLAY=:0 xfce4-terminal --title='SMD idle witness' "
                      ">/dev/null 2>&1 &", timeout=60)
            time.sleep(12)
            layout0, focus0, helpers0, log0 = (tree_signature(), focus(),
                                               helpers(), log_size())
            record("INFO: idle start: focus %s, helpers %s, %d log lines"
                   % (focus0, helpers0, log0))
            drift, usage, slow = [], [], []
            samples = max(2, minutes * 2)
            for index in range(samples):
                time.sleep(30)
                if tree_signature() != layout0:
                    drift.append("layout moved after %ds" % ((index + 1) * 30))
                if focus() != focus0:
                    drift.append("focus moved to %s after %ds"
                                 % (focus(), (index + 1) * 30))
                if helpers() != helpers0:
                    drift.append("helpers became %s after %ds"
                                 % (helpers(), (index + 1) * 30))
                if log_size() != log0:
                    drift.append("the helper acted while idle after %ds"
                                 % ((index + 1) * 30))
                used = helper_usage()
                if used:
                    usage.append(used)
                asked = time.time()
                shell.run("DISPLAY=:0 i3-msg -t get_version", timeout=60)
                took = time.time() - asked - 1.5
                if took > 2.0:
                    slow.append("i3 answered in %.1fs at %ds" % (took, (index + 1) * 30))
            record("INFO: helper while idle (cpu%%, rss kB): %s" % (usage[:3],))
            record("INFO: idle drift: %s" % (drift[:6] or "none"))
            ok("the desktop does not rearrange itself while idle", not drift,
               drift[:3])
            ok("no helper appeared or died while idle", not any(
                entry.startswith("helpers") for entry in drift), drift[:3])
            ok("the window manager stayed responsive while idle", not slow,
               slow[:3])
            ok("the helper stayed cheap while idle",
               not usage or max(entry[0] for entry in usage) < 5.0,
               max((entry[0] for entry in usage), default=0))
            if usage:
                ok("the helper did not grow while idle",
                   usage[-1][1] <= max(usage[0][1] * 1.5, usage[0][1] + 4096),
                   "%d kB -> %d kB" % (usage[0][1], usage[-1][1]))

        record("INFO: helper processes at the end: %s" % helpers())
        record("INFO: reflows at the end: %s" % reflows())
        tail = shell.run("tail -12 ~/.cache/smd/autotile.log 2>/dev/null",
                         timeout=60)
        record("INFO: helper log tail: " + " | ".join(tail.split()))
        ok("exactly one tiling helper is running", helpers() == "1", helpers())
        shell.run("DISPLAY=:0 xdotool windowclose %s; "
                  "pkill -x brave; pkill -f /tmp/hunter-autotile"
                  % " ".join(str(w) for w in names.values()), timeout=60)
        return 0 if passed else 1
    finally:
        server.terminate()
        try:
            Channel(MON_PORT).send("quit\r")
        except OSError:
            pass
        time.sleep(2)
        if qemu.poll() is None:
            qemu.kill()
        with open(RESULT, "w", encoding="utf-8") as handle:
            handle.write("\n".join(results) + "\n")


if __name__ == "__main__":
    sys.exit(main())
