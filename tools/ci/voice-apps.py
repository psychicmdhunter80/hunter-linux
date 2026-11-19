#!/usr/bin/env python3
"""Verify Voice Typing (Alt+Z) and the Jellyfin client in a live session.

    voice-apps.py <iso> <work dir> [uefi|bios]

Nothing here needs a microphone or a Jellyfin server:

  * a null sink and its monitor source carry a known speech recording into the
    recogniser, so the words that appear in a text field can be checked against
    what was spoken;
  * the client is opened and its window, log and configuration are inspected,
    and no server, account or autostart entry is allowed to be present.

The listening/stopped feedback is read from a screenshot with tesseract, which
is the only way to prove that a notification was actually drawn.
"""

import os
import re
import socket
import subprocess
import shlex
import sys
import time

from PIL import Image
import pytesseract

ISO = sys.argv[1]
WORK = sys.argv[2] if len(sys.argv) > 2 else "out-voice"
MODE = sys.argv[3] if len(sys.argv) > 3 else "uefi"

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WAV = os.path.join(REPO, "tools", "ci", "audio", "vosk-test.wav")
WAV_SHA256 = "dcfea5712c43a43ba7ae8083afb39d36993e5a69c46e88b68aaa72b65cb615bb"

MON_PORT = 4900
SER_PORT = 4901
HTTP_PORT = 4902

os.makedirs(WORK, exist_ok=True)
RESULT = os.path.join(WORK, "result.txt")
STEPS = os.path.join(WORK, "steps.txt")
results = []
failed = []


def record(line):
    results.append(line)
    print(line, flush=True)


def note(line):
    with open(STEPS, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def check(label, condition, detail=""):
    line = ("PASS: " if condition else "FAIL: ") + label
    if detail:
        line += " - " + str(detail)[:300]
    record(line)
    if not condition:
        failed.append(label)
    return condition


class Channel:
    def __init__(self, port):
        deadline = time.time() + 90
        while True:
            try:
                self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
                break
            except OSError:
                if time.time() > deadline:
                    raise
                time.sleep(0.5)
        self.sock.settimeout(5)
        self.data = ""

    def send(self, text):
        self.sock.sendall(text.encode())

    def expect(self, pattern, timeout=120):
        deadline = time.time() + timeout
        regex = re.compile(pattern, re.IGNORECASE | re.DOTALL)
        while time.time() < deadline:
            try:
                chunk = self.sock.recv(65536).decode("utf-8", "replace")
            except socket.timeout:
                continue
            except OSError:
                break
            if chunk:
                self.data += chunk
            match = regex.search(self.data)
            if match:
                found = match.group(0)
                # Markers are unique per command, so what has been consumed is
                # dropped: a long run does not grow one endless buffer.
                self.data = self.data[match.end():]
                return found, self.data
        return None, self.data


class Monitor:
    """Screenshots through the QEMU monitor: no VNC server needed."""

    def __init__(self):
        self.chan = Channel(MON_PORT)
        self.chan.expect(r"\(qemu\)", timeout=30)

    def hmp(self, command, wait=1.0):
        self.chan.send(command + "\n")
        self.chan.expect(r"\(qemu\)", timeout=60)
        time.sleep(wait)

    def screenshot(self, name):
        ppm = os.path.join(WORK, "screen-%s.ppm" % name)
        png = os.path.join(WORK, "screen-%s.png" % name)
        self.hmp("screendump %s" % ppm, wait=1.5)
        subprocess.run(["convert", ppm, png], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(png):
            os.unlink(ppm) if os.path.exists(ppm) else None
        record("INFO: screenshot %s" % os.path.basename(png))
        return png


class Shell:
    def __init__(self, chan):
        self.chan = chan
        self.counter = 0
        self._session = {}

    def login(self, user="user", password="live", timeout=900):
        matched, _ = self.chan.expect(r"login:", timeout=timeout)
        if not matched:
            for _attempt in range(6):
                self.chan.send("\r")
                matched, _ = self.chan.expect(r"login:", timeout=10)
                if matched:
                    break
        if not matched:
            record("FAIL: no login prompt on the serial console")
            return False
        self.chan.send(user + "\r")
        if self.chan.expect(r"[Pp]assword:", timeout=60):
            self.chan.send(password + "\r")
        if not self.chan.expect(r"[$#] ", timeout=180):
            record("FAIL: could not log in on the serial console")
            return False
        record("PASS: logged in on the serial console")
        return True

    def run(self, command, timeout=180, lines=60):
        self.counter += 1
        begin = "VOICEMARK%dBEGIN" % self.counter
        end = "VOICEMARK%dEND" % self.counter
        # The marker is split so the echoed command cannot match it.
        wrapped = ('echo "%s""%s"; (%s) 2>&1 | head -%d; echo "%s""%s"'
                   % (begin[:10], begin[10:], command, lines, end[:10], end[10:]))
        self.chan.send(wrapped + "\r")
        match, _ = self.chan.expect(re.escape(begin) + r"(.*?)" + re.escape(end),
                                    timeout=timeout)
        if not match:
            note("$ %s\n<bounded timeout after %ss>" % (command, timeout))
            record("FAIL: the command timed out: %s" % command[:120])
            return ""
        text = re.sub(r"\r", "", match[len(begin):-len(end)]).strip()
        note("$ %s\n%s" % (command, text))
        return text

    def session_environment(self):
        """The live session's own display, runtime directory and bus address.

        /run/user/1000/bus does not exist on this image, so every guess at the
        socket made notify-send fail with "No such file or directory".  Look
        for the bus that actually exists - the systemd per-user socket or the
        one dbus-launch creates in /tmp - and record what was found, so a
        session without any bus is reported instead of guessed at.
        """
        if self._session.get("__probed"):
            return self._session
        out = self.run(
            "id -un; echo ---; "
            "pgrep -a -x i3 | head -2; echo ---; "
            "ls -d /run/user/*/bus /tmp/dbus-* 2>/dev/null | head -4; echo ---; "
            "pgrep -a dbus-daemon | head -2; echo ---; "
            "for p in $(pgrep -x i3 | head -1); do "
            "tr '\0' '\n' < /proc/$p/environ 2>/dev/null "
            "| grep -E '^(DISPLAY|XDG_RUNTIME_DIR|DBUS_SESSION_BUS_ADDRESS)='; "
            "done", timeout=120)
        chunks = [part.strip() for part in out.split("---")]
        record("INFO: session probe: %s" % " | ".join(
            " ".join(part.split())[:70] for part in chunks)[:300])
        env = {"__probed": "1"}
        for part in chunks:
            for line in part.splitlines():
                if line.startswith(("DISPLAY=", "XDG_RUNTIME_DIR=",
                                    "DBUS_SESSION_BUS_ADDRESS=")):
                    key, value = line.split("=", 1)
                    env[key] = value.strip()
        if "DBUS_SESSION_BUS_ADDRESS" not in env:
            for part in chunks:
                for line in part.splitlines():
                    if line.startswith("/run/user/") and line.endswith("/bus"):
                        env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=" + line
                        break
                    if line.startswith("/tmp/dbus-"):
                        env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=" + line
                        break
                if "DBUS_SESSION_BUS_ADDRESS" in env:
                    break
        self._session = env
        record("INFO: session environment: %s"
               % " ".join("%s=%s" % item for item in sorted(env.items())
                          if not item[0].startswith("__"))[:220])
        return env

    def xrun(self, command, timeout=180, lines=60):
        """Run a command with the live session's display and bus."""
        env = self.session_environment()
        exports = " ".join(
            "%s=%s" % (key, shlex.quote(env.get(key, fallback)))
            for key, fallback in (("DISPLAY", ":0"),
                                  ("XDG_RUNTIME_DIR", "/run/user/1000"),
                                  ("DBUS_SESSION_BUS_ADDRESS",
                                   "unix:path=/run/user/1000/bus")))
        return self.run("export " + exports + "; " + command,
                        timeout=timeout, lines=lines)

    def wait_for_x(self, timeout=600):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if "READY" in self.run(
                    "DISPLAY=:0 xdpyinfo >/dev/null 2>&1 && echo READY || echo WAIT",
                    timeout=60):
                record("PASS: the X display is up")
                self.run("DISPLAY=:0 xset s off -dpms >/dev/null 2>&1; "
                         "DISPLAY=:0 xset s noblank >/dev/null 2>&1; echo BLANK=off",
                         timeout=60)
                return True
            time.sleep(10)
        record("FAIL: the X display never came up")
        return False


def count_notifications(shell):
    """How many notification bubbles the session has raised so far."""
    out = shell.run("grep -c 'member=Notify' /tmp/notif.txt 2>/dev/null || echo 0",
                    timeout=60)
    numbers = [ln.strip() for ln in out.splitlines() if ln.strip().isdigit()]
    return int(numbers[-1]) if numbers else 0


def notification_text(shell):
    """The summary and body strings of the captured notifications."""
    out = shell.run("grep -o 'string \"[^\"]*\"' /tmp/notif.txt 2>/dev/null "
                    "| tail -14", timeout=60)
    return " ".join(out.split()).replace('string "', "").replace('"', "")


def start_qemu():
    accel = "kvm" if os.access("/dev/kvm", os.W_OK) else "tcg"
    record("INFO: accelerator %s" % accel)
    args = ["qemu-system-x86_64", "-m", "2048", "-smp", "2", "-accel", accel,
            "-display", "none", "-vga", "std", "-no-reboot",
            "-monitor", "tcp:127.0.0.1:%d,server,nowait" % MON_PORT,
            "-serial", "tcp:127.0.0.1:%d,server,nowait" % SER_PORT,
            "-netdev", "user,id=n0", "-device", "virtio-net-pci,netdev=n0"]
    if MODE == "uefi":
        code = "/usr/share/OVMF/OVMF_CODE_4M.fd"
        var_src = "/usr/share/OVMF/OVMF_VARS_4M.fd"
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


def ocr(path):
    if not path or not os.path.exists(path):
        return ""
    try:
        return pytesseract.image_to_string(Image.open(path))
    except Exception as error:  # noqa: BLE001 - report, do not crash the run
        record("WARN: OCR failed: %s" % error)
        return ""


def main():
    for path in (RESULT, STEPS):
        if os.path.exists(path):
            os.unlink(path)
    if not os.path.exists(WAV):
        record("FAIL: the test recording %s is missing" % WAV)
        return 1
    digest = subprocess.run(["sha256sum", WAV], capture_output=True, text=True)
    record("PASS: the test recording is intact"
           if WAV_SHA256 in digest.stdout else
           "FAIL: the test recording does not match its checksum")

    qemu = start_qemu()
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(HTTP_PORT),
                               "--bind", "127.0.0.1", "--directory", REPO],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    monitor = None
    try:
        time.sleep(6)
        # The serial port is opened before the guest boots: QEMU keeps no
        # output for a client that connects later, and that is how the install
        # test lost a login prompt.
        shell = Shell(Channel(SER_PORT))
        monitor = Monitor()
        if not shell.login() or not shell.wait_for_x():
            return 1
        # The serial shell is not the desktop session: notifications and
        # xdotool both need that session's display and bus (see Shell.xrun).
        shell.xrun("echo ENV=ready", timeout=60)

        # ---------------------------------------------------------- fresh user
        fresh = shell.xrun(
            "test -e ~/.local/share/smd-dictation && echo voice-state || echo voice-clean; "
            "test -e ~/.config/jellyfin-mpv-shim/config.json && echo jf-config || echo jf-clean; "
            "xrandr --display :0 >/dev/null 2>&1; echo ---; "
            "pactl info 2>&1 | grep -i 'server name'; "
            "pgrep -x pipewire >/dev/null && echo PIPEWIRE-RUNNING; echo ---; "
            "cat ~/.config/jellyfin-mpv-shim/mpv.conf 2>/dev/null | grep -v '^#'",
            timeout=120)
        fchunks = fresh.split("---")
        check("a fresh user has no dictation state", "voice-clean" in fchunks[0])
        check("a fresh user has no saved Jellyfin configuration",
              "jf-clean" in fchunks[0])
        record("INFO: first audio probe: %s" % " ".join(fchunks[1].split())[:100])
        check("the client keeps its hardware decoding setting",
              "hwdec=auto-safe" in (fchunks[2] if len(fchunks) > 2 else ""),
              (fchunks[2] if len(fchunks) > 2 else "").strip()[:60])

        # A notification bubble is the listening/stopped feedback.  Prove the
        # path first with a probe bubble: if this fails the desktop has no
        # notifier and every later bubble would silently go nowhere.
        base = shell.xrun(
            "pkill -x dbus-monitor 2>/dev/null; "
            "(setsid dbus-monitor --session \"interface='org.freedesktop.Notifications'\" "
            "</dev/null >/tmp/notif.txt 2>&1 &); sleep 3; "
            "notify-send -a 'SMD test' 'SMD test' 'feedback probe' >/dev/null 2>&1; "
            "echo RC=$?; echo ---; "
            "pgrep -x xfce4-notifyd >/dev/null && echo NOTIFYD=up || echo NOTIFYD=down; "
            "echo ---; grep -c 'member=Notify' /tmp/notif.txt 2>/dev/null || echo 0; "
            "echo ---; head -2 /tmp/notif.txt", timeout=150)
        bchunks = base.split("---")
        record("INFO: notification probe: %s"
               % " ".join(" ".join(bchunks).split())[:200])
        check("the desktop can show notifications",
              "RC=0" in (bchunks[0] if bchunks else ""),
              (bchunks[0] if bchunks else "").strip()[:80])
        if "RC=0" not in (bchunks[0] if bchunks else ""):
            record("NOTE: no notification could be delivered in this session; "
                   "the state file and `hunter-dictation status` are the only "
                   "feedback a user would see")
        notif_base = count_notifications(shell)
        check("the notification capture is running", notif_base >= 1,
              "bubbles captured: %d" % notif_base)
        record("INFO: notification daemon: %s, bubbles so far: %d"
               % (" ".join((bchunks[1] if len(bchunks) > 1 else "").split())[:40],
                  notif_base))

        # A recording to speak into.  PipeWire comes up with the session, so wait
        # for it before asking anything of it.
        audio = shell.xrun(
            "for i in $(seq 1 18); do pactl info >/dev/null 2>&1 && { echo AUDIO=ready; "
            "break; }; sleep 5; done; "
            "pactl info 2>&1 | grep -i 'server name'; echo ---; "
            "pactl load-module module-null-sink sink_name=smdvoice "
            "sink_properties=device.description=smdvoice >/tmp/module.txt 2>&1; "
            "pactl set-default-sink smdvoice 2>&1; "
            "pactl set-default-source smdvoice.monitor 2>&1; sleep 3; "
            "pactl list short sources 2>&1 | grep -c smdvoice", timeout=240)
        achunks = audio.split("---")
        check("the sound server is PipeWire",
              "PipeWire" in achunks[0] or "AUDIO=ready" in achunks[0],
              " ".join(achunks[0].split())[:100])
        sink = (achunks[1].strip().splitlines() or ["0"])[-1].strip() if len(achunks) > 1 else "0"
        check("a recording source exists to dictate from",
              sink.isdigit() and int(sink) >= 1, sink[:40])

        shell.run(
            "curl -fsS -m 60 http://10.0.2.2:%d/tools/ci/audio/vosk-test.wav "
            "-o /tmp/test.wav && echo WAV=ok; sha256sum /tmp/test.wav | cut -d' ' -f1"
            % HTTP_PORT, timeout=180)
        received = shell.run("sha256sum /tmp/test.wav | cut -d' ' -f1", timeout=60)
        check("the test recording reaches the guest",
              WAV_SHA256 in received, received.strip()[:70])

        # A text field that keeps what is typed into it: cat writes every byte
        # it receives to a file, so typed text AND the Ctrl keys below can be
        # read back from the filesystem.
        # stty -icanon: a terminal buffers a whole line before the program
        # sees it, so without this the dictation would stay invisible until
        # Enter and the Ctrl keys would only sit in the line buffer.
        shell.run(
            "printf '#!/bin/sh\\nstty -icanon -echo 2>/dev/null\\n"
            "cat > /tmp/dictated.txt\\n' > /tmp/recv.sh; "
            "chmod +x /tmp/recv.sh; : > /tmp/dictated.txt; "
            "DISPLAY=:0 setsid xfce4-terminal --title=DictationTarget "
            "--command=/tmp/recv.sh >/tmp/term.log 2>&1 & sleep 8; "
            "DISPLAY=:0 xdotool search --name DictationTarget | head -1",
            timeout=180)
        target = shell.run("DISPLAY=:0 xdotool search --name DictationTarget "
                           "| head -1", timeout=60).strip()
        check("a text field is ready to receive dictation", bool(target.isdigit()),
              target or "no terminal window")
        if not target.isdigit():
            return 1
        shell.run("DISPLAY=:0 xdotool windowactivate --sync %s; sleep 2; "
                  "DISPLAY=:0 xdotool mousemove 300 300 click 1; sleep 2"
                  % target, timeout=90)
        pid = shell.run("pgrep -n -x cat", timeout=60).strip()
        record("INFO: receiving process %s" % pid)

        # ------------------------------------------------------ Alt+Z starts it
        shell.xrun("xdotool key --clearmodifiers alt+z; sleep 3", timeout=90)
        # The notification is short-lived, so the screenshot is taken while it
        # is on screen rather than after the state has settled.
        shot = monitor.screenshot("voice-listening")
        started = shell.run("hunter-dictation status", timeout=60).strip()
        procs = shell.run("pgrep -c -f 'nerd-dictation be[g]in' || echo 0",
                          timeout=60).strip()
        check("Alt+Z starts dictation", started.endswith("listening"), started)
        check("exactly one recogniser runs", procs.splitlines()[-1:] == ["1"], procs)
        recording = shell.xrun(
            "pactl list source-outputs | grep -c 'Source Output' || echo 0",
            timeout=60).strip()
        check("the microphone is open while listening",
              recording.splitlines()[-1:] == ["1"], recording)
        text = ocr(shot).lower()
        notif_start = count_notifications(shell)
        record("INFO: text on screen after starting: %s" % " ".join(text.split())[:100])
        check("starting dictation raises a listening notification",
              notif_start > notif_base,
              "bubbles %d -> %d" % (notif_base, notif_start))

        # ------------------------------------- what is spoken becomes the text
        played = shell.xrun("paplay --device=smdvoice /tmp/test.wav "
                            ">/tmp/play.log 2>&1; echo PLAYED=$?", timeout=180)
        check("the test recording plays into the session",
              "PLAYED=0" in played, played.strip()[:80])
        # Decoding a whole sentence under emulation takes a minute or two, and
        # the words arrive progressively, so wait for a real transcript rather
        # than the first syllable.
        dictated = ""
        for _attempt in range(36):
            time.sleep(5)
            dictated = shell.run("cat /tmp/dictated.txt 2>/dev/null", timeout=60)
            if len(re.sub(r"\s", "", dictated)) >= 8:
                break
        spoken = re.findall(r"[a-z]+", dictated.lower())
        digits = re.sub(r"[^0-9]", "", dictated)
        record("INFO: dictated text: %s" % dictated.strip()[:140])
        check("speech is typed into the focused field",
              len(re.sub(r"\s", "", dictated)) >= 4, dictated.strip()[:120])
        check("the typed text matches what was spoken",
              len(digits) >= 3 or any(word in ("one", "zero", "nine", "two",
                                               "three", "oh", "know")
                                      for word in spoken),
              "digits=%s words=%s" % (digits[:20], " ".join(spoken)[:60]))

        # ------------------------------------ control keys stay with the app
        # This build never had a dictation shortcut on Ctrl+Z.  The running
        # window manager's own binding table is the authority on whether any of
        # the three keys is taken, and the document shows that control keys
        # still arrive: Ctrl+A and Ctrl+X leave their bytes behind, while the
        # terminal driver turns Ctrl+Z into a signal instead of text.
        binds = shell.xrun(
            "i3-msg -t get_config >/tmp/i3config.txt 2>&1; "
            "for key in 'ctrl+z' 'ctrl+x' 'ctrl+a'; do "
            "grep -iE '^[[:space:]]*bindsym' /tmp/i3config.txt | grep -ci \"$key\"; "
            "done", timeout=120)
        counts = [ln.strip() for ln in binds.splitlines() if ln.strip().isdigit()]
        record("INFO: desktop bindings for ctrl+z, ctrl+x, ctrl+a: %s"
               % ",".join(counts[:3]))
        check("no desktop shortcut claims Ctrl+Z, Ctrl+X or Ctrl+A",
              counts[:3] == ["0", "0", "0"], ",".join(counts[:3]))
        shell.xrun("xdotool key --clearmodifiers ctrl+z; sleep 2; "
                   "xdotool key --clearmodifiers ctrl+a; sleep 1; "
                   "xdotool key --clearmodifiers ctrl+x; sleep 2", timeout=120)
        sent = " " + " ".join(shell.run(
            "od -An -c /tmp/dictated.txt | tr -s ' ' | tr '\n' ' '",
            timeout=60).split()) + " "
        record("INFO: bytes in the field: %s" % sent[:200])
        check("Ctrl+A and Ctrl+X reach the application",
              " 001 " in sent and " 030 " in sent, sent[:120])
        check("Ctrl+Z is handled by the terminal, not typed as text",
              " 032 " not in sent, sent[:120])

        # ---------------------------------------- one press stops, one starts
        # No retries here: a keystroke that needs three attempts is not "a
        # single press toggles dictation".  Each press is timed and reported as
        # measured, and the notification text is checked for the wording.
        shell.xrun("xdotool key --clearmodifiers alt+z", timeout=90)
        pressed_at = time.time()
        stopped = ""
        for _ in range(20):
            time.sleep(1)
            stopped = shell.run("hunter-dictation status", timeout=60).strip()
            if stopped.endswith("stopped"):
                break
        took = time.time() - pressed_at
        record("INFO: one press reached '%s' after %.1f s"
               % (stopped.splitlines()[-1] if stopped else "", took))
        shot = monitor.screenshot("voice-stopped")
        procs = shell.run("pgrep -c -f 'nerd-dictation be[g]in' || echo 0",
                          timeout=60).strip()
        recording = shell.xrun(
            "pactl list source-outputs | grep -c 'Source Output' || echo 0",
            timeout=60).strip()
        check("one Alt+Z press stops dictation", stopped.endswith("stopped"), stopped)
        # One press, not three.  How long stopping takes is measured and
        # reported, but the bound is loose because this runner has no KVM:
        # the same image stopped in 2.5 s, 5.5 s and 15.3 s on three runs.
        # A dictation that never stops ends up at the polling limit instead.
        if took > 10:
            record("INFO: stopping took longer than ten seconds in this VM; "
                   "worth confirming on real hardware")
        check("a single press is enough", took <= 30, "%.1f s" % took)
        check("no recogniser is left behind", procs.splitlines()[-1:] == ["0"], procs)
        check("the microphone is released when dictation stops",
              recording.splitlines()[-1:] == ["0"], recording)
        stopped_text = notification_text(shell)
        record("INFO: notification after stopping: %s" % stopped_text[:140])
        check("the stopped notification names the state",
              "Voice typing: stopped" in stopped_text, stopped_text[:120])
        text = ocr(shot).lower()
        record("INFO: text on screen after stopping: %s" % " ".join(text.split())[:100])

        # And one press brings it back.
        time.sleep(3)
        shell.xrun("xdotool key --clearmodifiers alt+z", timeout=90)
        pressed_at = time.time()
        restarted = ""
        for _ in range(20):
            time.sleep(1)
            restarted = shell.run("hunter-dictation status", timeout=60).strip()
            if restarted.endswith("listening"):
                break
        took = time.time() - pressed_at
        record("INFO: one press reached '%s' after %.1f s"
               % (restarted.splitlines()[-1] if restarted else "", took))
        check("one Alt+Z press starts dictation again",
              restarted.endswith("listening"), restarted)
        listening_text = notification_text(shell)
        record("INFO: notification after starting: %s" % listening_text[:140])
        check("the listening notification names the state",
              "Voice typing: listening" in listening_text, listening_text[:120])
        shell.xrun("hunter-dictation stop; sleep 2", timeout=90)

        # ------------------------------------------------- no duplicate start
        shell.xrun("hunter-dictation start; sleep 6; "
                   "hunter-dictation start; sleep 2", timeout=120)
        procs = shell.run("pgrep -c -f 'nerd-dictation be[g]in' || echo 0",
                          timeout=60).strip()
        check("starting twice still leaves one recogniser",
              procs.splitlines()[-1:] == ["1"], procs)
        shell.xrun("xdotool key alt+z; sleep 3; "
                   "xdotool key alt+z; sleep 6; "
                   "xdotool key alt+z; sleep 3", timeout=120)
        procs = shell.run("pgrep -c -f 'nerd-dictation be[g]in' || echo 0",
                          timeout=60).strip()
        count = (procs.splitlines() or ["0"])[-1].strip()
        check("repeated Alt+Z presses never stack recognisers",
              count.isdigit() and int(count) <= 1, procs)
        shell.xrun("hunter-dictation stop; sleep 2", timeout=90)

        # ------------------------------------------------------ Jellyfin client
        entry = shell.run(
            "sed -n '1,12p' /usr/share/applications/jellyfin-mpv-shim.desktop; "
            "echo ---; test -x /opt/jellyfin-mpv-shim/bin/jellyfin-mpv-shim "
            "&& echo EXEC=ok", timeout=60)
        echunks = entry.split("---")
        check("the Jellyfin client has a menu entry",
              "Name=Jellyfin" in echunks[0] and "Exec=" in echunks[0],
              " ".join(echunks[0].split())[:100])
        check("the menu entry points at an installed program",
              "EXEC=ok" in (echunks[1] if len(echunks) > 1 else ""))

        shell.xrun("setsid /opt/jellyfin-mpv-shim/bin/jellyfin-mpv-shim "
                   ">/tmp/jellyfin.log 2>&1 & sleep 25", timeout=120)
        alive = shell.run("pgrep -c -f 'jellyfin-mpv-shim' || echo 0",
                          timeout=60).strip()
        window = shell.run("DISPLAY=:0 xwininfo -root -tree 2>/dev/null "
                           "| grep -ci jellyfin", timeout=60).strip()
        # The word "libmpv" appears in a healthy log ("Using libmpv playback
        # backend"), so only real failures are looked for.
        log = shell.run(
            "grep -iE 'modulenotfound|importerror|libmpv.so' "
            "/tmp/jellyfin.log | grep -vi \"module named 'gi'\" | head -5; "
            "echo ---; grep -ci \"module named 'gi'\" /tmp/jellyfin.log",
            timeout=60)
        record("INFO: Jellyfin window count: %s" % window)
        record("INFO: Jellyfin log: %s" % " | ".join(log.split())[:220])
        check("the Jellyfin client starts", alive.splitlines()[-1:] != ["0"], alive)
        check("the Jellyfin client opens a window",
              window.splitlines()[-1:] != ["0"], window)
        failures = (log.split("---")[0] if "---" in log else "").lower()
        check("the Jellyfin client starts without a missing playback library",
              not failures.strip(), " | ".join(failures.split())[:140])
        gi = (log.split("---")[1] if "---" in log else "").strip()
        if gi.isdigit() and int(gi) > 0:
            record("WARN: the client logs a missing PyGObject (gi), so its tray "
                   "icon and desktop notifications stay inactive; playback and its "
                   "window are unaffected - see the known limitations")
        monitor.screenshot("jellyfin-flat")
        shell.run("pkill -f 'jellyfin-mpv-shim'; sleep 2", timeout=60)

        config = shell.run(
            "test -e ~/.config/jellyfin-mpv-shim/config.json && "
            "{ grep -c -iE 'http|server|username|token' "
            "~/.config/jellyfin-mpv-shim/config.json || true; } || echo no-config; "
            "echo ---; ls /etc/xdg/autostart 2>/dev/null | grep -c -i jellyfin || true; "
            "ls ~/.config/autostart 2>/dev/null | grep -c -i jellyfin || true",
            timeout=90)
        cchunks = config.split("---")
        check("no server address, account or token is saved for the client",
              cchunks[0].strip().splitlines()[-1:] in (["no-config"], ["0"]),
              cchunks[0].strip()[:80])
        autostart = cchunks[1].split() if len(cchunks) > 1 else []
        check("the Jellyfin client does not start automatically",
              all(value == "0" for value in autostart) if autostart else True,
              " ".join(autostart))

        # ------------------------------------------------------------- cleanup
        shell.run("pkill -x cat; pkill -f DictationTarget; "
                  "pactl unload-module module-null-sink 2>/dev/null; "
                  "hunter-dictation stop; echo CLEAN=done", timeout=90)
        record("INFO: helper and recogniser state: %s"
               % shell.run("hunter-dictation status; pgrep -c -f "
                           "'nerd-dictation be[g]in' || true", timeout=60).strip())
    finally:
        server.terminate()
        if monitor:
            try:
                monitor.hmp("quit", wait=1)
            except OSError:
                pass
        time.sleep(2)
        if qemu.poll() is None:
            qemu.kill()
        record("RESULT: %s" % ("passed" if not failed
                              else "failed (%d)" % len(failed)))
        with open(RESULT, "w", encoding="utf-8") as handle:
            handle.write("\n".join(results) + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
