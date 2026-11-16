#!/usr/bin/env python3
"""Test hunter-autotile inside a booted live session, without rebuilding the ISO.

The live image is only the environment: the helper under test is fetched from
this checkout, installed in the guest as the session user and started there, so
the tiling logic can be iterated against one ISO instead of one build per fix.

Usage: tile-debug.py <iso> <mode: bios|uefi> <work dir>
"""

import json
import os
import re
import socket
import subprocess
import sys
import time

ISO = sys.argv[1]
MODE = sys.argv[2] if len(sys.argv) > 2 else "uefi"
WORK = sys.argv[3] if len(sys.argv) > 3 else "out-tile"

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HELPER = os.path.join(REPO, "config/includes.chroot/usr/local/bin/hunter-autotile")
DUMPER = os.path.join(REPO, "tools/ci/tile-dump.py")

MON_PORT = 4600
SER_PORT = 4601
HTTP_PORT = 4711
LIVE_USER = os.environ.get("LIVE_USER", "user")
LIVE_PASS = os.environ.get("LIVE_PASS", "live")

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
        self.chan.send(LIVE_USER + "\r")
        if self.chan.expect(r"[Pp]assword:", timeout=60):
            self.chan.send(LIVE_PASS + "\r")
        if not self.chan.expect(r"[$#] ", timeout=120):
            record("FAIL: could not log in on the serial console")
            return False
        record("PASS: logged in as %s on the serial console" % LIVE_USER)
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
            record("WARN: command timed out: %s" % command)
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
        vars_copy = os.path.join(WORK, "OVMF_VARS.fd")
        subprocess.run(["cp", var_src, vars_copy], check=True)
        args += ["-machine", "q35",
                 "-drive", "if=pflash,format=raw,readonly=on,file=%s" % code,
                 "-drive", "if=pflash,format=raw,file=%s" % vars_copy]
    else:
        args += ["-boot", "d"]
    args += ["-cdrom", ISO]
    log = open(os.path.join(WORK, "qemu.log"), "w", encoding="utf-8")
    return subprocess.Popen(args, stdout=log, stderr=log)


RECT = re.compile(r"window name=(smd-[\w-]+).*?rect=(-?\d+),(-?\d+)\+(\d+)x(\d+)")


def boxes(text):
    """{title: (x, y, w, h)} for the test windows."""
    found = {}
    for match in RECT.finditer(text):
        found[match.group(1)] = tuple(int(match.group(i)) for i in range(2, 6))
    return found


def describe(found):
    return " ".join("%s[%d,%d %dx%d]" % (name, r[0], r[1], r[2], r[3])
                    for name, r in sorted(found.items()))


def main():
    for path in (RESULT, STEPS):
        if os.path.exists(path):
            os.unlink(path)

    qemu = start_qemu()
    if qemu is None:
        return 1
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(HTTP_PORT),
                               "--bind", "127.0.0.1", "--directory", REPO],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    try:
        time.sleep(3)
        shell = Shell(Channel(SER_PORT))
        if not shell.login():
            return 1
        if not shell.wait_for_x():
            return 1

        # The helper under test comes from this checkout, not from the image.
        fetched = shell.run(
            "curl -fsS -m 30 http://10.0.2.2:%d/config/includes.chroot/usr/local/bin/"
            "hunter-autotile -o /tmp/hunter-autotile && echo HELPER=fetched "
            "|| echo HELPER=unfetched; "
            "curl -fsS -m 30 http://10.0.2.2:%d/tools/ci/tile-dump.py "
            "-o /tmp/tile-dump.py && echo DUMPER=fetched || echo DUMPER=unfetched"
            % (HTTP_PORT, HTTP_PORT), timeout=120)
        if "HELPER=unfetched" in fetched or "DUMPER=unfetched" in fetched:
            record("INFO: no guest network, sending the helper over the console")
            text = open(HELPER, encoding="utf-8").read()
            import base64
            blob = base64.b64encode(text.encode()).decode()
            shell.run("rm -f /tmp/at.b64", timeout=60)
            for start in range(0, len(blob), 500):
                shell.run("printf '%%s' '%s' >> /tmp/at.b64" % blob[start:start + 500],
                          timeout=60, lines=3)
            shell.run("base64 -d /tmp/at.b64 > /tmp/hunter-autotile && echo B64=ok",
                      timeout=120)
            dumper = open(DUMPER, encoding="utf-8").read()
            blob = base64.b64encode(dumper.encode()).decode()
            shell.run("rm -f /tmp/d.b64", timeout=60)
            for start in range(0, len(blob), 500):
                shell.run("printf '%%s' '%s' >> /tmp/d.b64" % blob[start:start + 500],
                          timeout=60, lines=3)
            shell.run("base64 -d /tmp/d.b64 > /tmp/tile-dump.py && echo B64=ok",
                      timeout=120)

        shell.run("chmod +x /tmp/hunter-autotile /tmp/tile-dump.py; "
                  "python3 -c \"import ast;ast.parse(open('/tmp/hunter-autotile')"
                  ".read());print('SYNTAX=ok')\"", timeout=120)

        # A clean session: the browser is a normal window and would take a slot.
        # The bracket keeps pkill from matching the shell running it.
        shell.run("pkill -x brave; pkill -f 'hunter-auto[t]ile'; sleep 3; "
                  ": > ~/.cache/smd/autotile.log; "
                  "pgrep -fc 'hunter-auto[t]ile' || echo NONE", timeout=90)
        shell.run("DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/1000 "
                  "setsid python3 /tmp/hunter-autotile </dev/null "
                  ">>/tmp/at.log 2>&1 & sleep 4; "
                  "pgrep -fc 'hunter-auto[t]ile'; tail -3 ~/.cache/smd/autotile.log",
                  timeout=90)
        shell.run("DISPLAY=:0 i3-msg 'workspace 1' >/dev/null; echo WS=1", timeout=60)

        def open_window(title):
            shell.run("DISPLAY=:0 setsid xfce4-terminal --title=%s "
                      "</dev/null >/dev/null 2>&1 & sleep 8" % title, timeout=90)

        def dump(stage):
            text = shell.run("DISPLAY=:0 python3 /tmp/tile-dump.py", timeout=120,
                             lines=200)
            note("--- tree after %s ---\n%s" % (stage, text))
            log = shell.run("tail -7 ~/.cache/smd/autotile.log 2>/dev/null", timeout=60)
            record("INFO: helper after %s: %s" % (stage, " ".join(log.split())))
            return text

        def check(label, ok, text):
            record(("PASS: " if ok else "FAIL: ") + label)
            record("INFO: %s: %s" % (label, describe(boxes(text))))
            return ok

        passed = True

        open_window("smd-one")
        text = dump("one")
        found = boxes(text)
        passed &= check("one window fills the desktop",
                        len(found) == 1 and list(found.values())[0][2] >= 1200,
                        text)

        open_window("smd-two")
        text = dump("two")
        found = boxes(text)
        halves = (len(found) == 2
                  and abs(found["smd-one"][2] - found["smd-two"][2]) <= 4
                  and found["smd-one"][1] == found["smd-two"][1]
                  and found["smd-one"][0] != found["smd-two"][0])
        passed &= check("two windows are equal halves", halves, text)

        # Focus must not decide placement: focus the first window before the
        # third arrives.
        shell.run("DISPLAY=:0 i3-msg '[title=\"^smd-one$\"] focus' >/dev/null; "
                  "echo FOCUS=one", timeout=60)
        open_window("smd-three")
        text = dump("three")
        found = boxes(text)
        three_ok = False
        if len(found) == 3:
            one, two, three = found["smd-one"], found["smd-two"], found["smd-three"]
            three_ok = (three[0] == one[0] and three[1] > one[1]
                        and abs(three[2] - one[2]) <= 4
                        and abs(one[2] - two[2]) <= 4)
        passed &= check("the third window sits below the first on the left",
                        three_ok, text)

        open_window("smd-four")
        text = dump("four")
        found = boxes(text)
        four_ok = False
        if len(found) == 4:
            one, two, three, four = (found["smd-one"], found["smd-two"],
                                     found["smd-three"], found["smd-four"])
            four_ok = (one[0] == three[0] and two[0] == four[0]
                       and three[1] > one[1] and four[1] > two[1]
                       and abs(one[2] - two[2]) <= 4
                       and abs(three[2] - one[2]) <= 4
                       and abs(four[2] - two[2]) <= 4)
        passed &= check("the fourth window sits below the second on the right",
                        four_ok, text)

        # Closing a window compresses the survivors, in arrival order.
        shell.run("DISPLAY=:0 xdotool search --name '^smd-three$' windowclose; "
                  "sleep 6; echo CLOSED", timeout=90)
        text = dump("close")
        found = boxes(text)
        close_ok = (len(found) == 3 and found["smd-one"][0] == found["smd-four"][0]
                    and abs(found["smd-one"][2] - found["smd-four"][2]) <= 4)
        passed &= check("closing the third leaves one over four on the left",
                        close_ok, text)

        open_window("smd-three")
        text = dump("reopen")
        found = boxes(text)
        reopen_ok = False
        if len(found) == 4:
            one, two, three, four = (found["smd-one"], found["smd-two"],
                                     found["smd-three"], found["smd-four"])
            reopen_ok = (one[0] == three[0] and two[0] == four[0]
                         and three[1] > one[1] and four[1] > two[1]
                         and abs(one[2] - two[2]) <= 4)
        passed &= check("reopening refills the grid in arrival order",
                        reopen_ok, text)

        record("INFO: final helper log: " + " ".join(
            shell.run("tail -12 ~/.cache/smd/autotile.log 2>/dev/null",
                      timeout=60).split()))
        record("PASS: tiling diagnostics ran to the end")
        shell.run("DISPLAY=:0 xdotool search --name '^smd-' windowclose; "
                  "pkill -f /tmp/hunter-autotile", timeout=60)
        return 0 if passed else 1
    finally:
        server.terminate()
        try:
            monitor = Channel(MON_PORT)
            monitor.send("quit\r")
        except OSError:
            pass
        time.sleep(2)
        if qemu.poll() is None:
            qemu.kill()
        with open(RESULT, "w", encoding="utf-8") as handle:
            handle.write("\n".join(results) + "\n")


if __name__ == "__main__":
    sys.exit(main())
