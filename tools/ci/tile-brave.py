#!/usr/bin/env python3
"""Reproduce the tiling behaviour with real Brave windows in a booted live session.

The ISO is only the environment: the helper under test is fetched from this
checkout, so the delivered helper and a patched one can be compared against the
same image.

Evidence captured per stage: helper log (including how many reflows ran), the
number of helper processes, and the i3 tree.  A stage counts as stable only if
the window rectangles stop changing: the tree is sampled repeatedly and the
number of distinct layouts is reported, so a correct-looking screenshot cannot
pass on its own.

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
    args = ["qemu-system-x86_64", "-m", "2048", "-smp", "2", "-accel", accel,
            "-display", "none", "-vga", "std", "-no-reboot",
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


BOX = re.compile(r"WIN id=\d+ .*?xid=(\d+) class=(\S+) .*?rect=(-?\d+),(-?\d+)\+(\d+)x(\d+)")
# The panel owns a real window too; it is part of the furniture, not a window
# the layout has to arrange.
FURNITURE = {"xfce4-panel", "Brave-browser"}.difference({"Brave-browser"})


def layouts(text):
    """The window rectangles from a tree dump, keyed by X id."""
    found = {}
    for match in BOX.finditer(text):
        xid = int(match.group(1))
        if not xid or match.group(2) in FURNITURE:
            continue
        found[xid] = tuple(int(match.group(i)) for i in range(3, 7))
    return found


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

        fetched = shell.run(
            "curl -fsS -m 30 http://10.0.2.2:%d/config/includes.chroot/usr/local/bin/"
            "hunter-autotile -o /tmp/hunter-autotile && echo HELPER=ok; "
            "curl -fsS -m 30 http://10.0.2.2:%d/tools/ci/tile-dump.py "
            "-o /tmp/tile-dump.py && echo DUMPER=ok" % (HTTP_PORT, HTTP_PORT),
            timeout=120)
        if "HELPER=ok" not in fetched:
            record("FAIL: the helper could not be fetched from the checkout")
            return 1
        shell.run("chmod +x /tmp/hunter-autotile /tmp/tile-dump.py; "
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
            out = shell.run("grep -c 'reflow' ~/.cache/smd/autotile.log "
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
                   + ((" - " + detail) if detail else ""))
            passed = passed and condition
            return condition

        # 1 window, from a first run (no profile yet, so Brave shows its welcome).
        open_brave("smd-one", first=True)
        one, _ = stage("one window")
        ok("one window fills the desktop",
           len(one) == 1 and list(one.values())[0][2] >= 1200,
           describe(one, labels_for(one)))

        open_brave("smd-two")
        two, _ = stage("two windows", idle=15)
        a, b = names.get("smd-one"), names.get("smd-two")
        halves = (len(two) == 2 and a in two and b in two
                  and abs(two[a][2] - two[b][2]) <= 4
                  and two[a][1] == two[b][1]
                  and two[a][0] != two[b][0])
        ok("two windows are equal left/right halves", halves,
           describe(two, labels_for(two)))

        open_brave("smd-three")
        three, stable3 = stage("three windows", idle=30)
        w1, w2, w3 = names.get("smd-one"), names.get("smd-two"), names.get(
            "smd-three")
        three_ok = False
        if len(three) == 3 and all(w in three for w in (w1, w2, w3)):
            a, b, c = three[w1], three[w2], three[w3]
            three_ok = (c[0] == a[0] and c[1] > a[1]
                        and abs(c[2] - a[2]) <= 4
                        and b[0] > a[0] and abs(b[2] - a[2]) <= 4)
        ok("three windows: first top-left, third bottom-left, second full right",
           three_ok, describe(three, labels_for(three)))
        ok("three windows settle and stay put", stable3)

        open_brave("smd-four")
        four, stable4 = stage("four windows", idle=30)
        w4 = names.get("smd-four")
        four_ok = False
        if len(four) == 4 and all(w in four for w in (w1, w2, w3, w4)):
            a, b, c, d = four[w1], four[w2], four[w3], four[w4]
            four_ok = (c[0] == a[0] and d[0] == b[0]
                       and c[1] > a[1] and d[1] > b[1]
                       and abs(a[2] - b[2]) <= 4 and abs(c[2] - d[2]) <= 4)
        ok("four windows form an even 2x2 with the fourth bottom-right",
           four_ok, describe(four, labels_for(four)))
        ok("four windows settle and stay put", stable4)

        # Focus, clicking and typing must not rearrange anything.
        before = json.dumps(layouts(tree()), sort_keys=True)
        shell.run("DISPLAY=:0 xdotool mousemove 200 200 click 1; sleep 1; "
                  "xdotool type 'hello'; xdotool key ctrl+l; xdotool type 'about:blank'; "
                  "xdotool key Return; sleep 3", timeout=120)
        shell.run("DISPLAY=:0 i3-msg '[id=%s] focus' >/dev/null; sleep 3"
                  % names.get("smd-one"), timeout=60)
        after = json.dumps(layouts(tree()), sort_keys=True)
        ok("clicking, typing and focusing change no layout", before == after)

        # Fullscreen has to be left alone, and coming back must restore the grid.
        shell.run("DISPLAY=:0 i3-msg '[id=%s] focus'; sleep 1; "
                  "DISPLAY=:0 xdotool key F11; sleep 4"
                  % names.get("smd-two"), timeout=120)
        full = layouts(tree())
        record("INFO: fullscreen: %s" % describe(full))
        shell.run("DISPLAY=:0 xdotool key F11; sleep 4", timeout=120)
        back, stable_back = stage("after fullscreen", idle=8)
        ok("exiting fullscreen restores the 2x2 grid",
           len(back) == 4 and stable_back, describe(back))

        # A dialog must stay floating and must not make the helper rebuild.
        shell.run("DISPLAY=:0 setsid xmessage -center 'SMD dialog test' "
                  ">/dev/null 2>&1 & sleep 4", timeout=120)
        dialog = shell.run("DISPLAY=:0 i3-msg -t get_tree", timeout=120)
        floating = "dialog test" in dialog
        record("INFO: dialog present: %s" % floating)
        shell.run("pkill -x xmessage; sleep 3", timeout=60)
        after_dialog, _ = stage("after dialog")
        ok("a dialog leaves the grid untouched",
           json.dumps(after_dialog, sort_keys=True) == after, describe(after_dialog))

        # Close and reopen.
        shell.run("DISPLAY=:0 xdotool windowclose %s; sleep 6"
                  % names.get("smd-three"), timeout=90)
        closed, stable_closed = stage("after closing the third", idle=10)
        ok("closing the third leaves three windows arranged again",
           len(closed) == 3 and stable_closed, describe(closed))

        open_brave("smd-three")
        reopened, stable_reopen = stage("after reopening", idle=15)
        ok("reopening settles into a 2x2 grid",
           len(reopened) == 4 and stable_reopen, describe(reopened))

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
