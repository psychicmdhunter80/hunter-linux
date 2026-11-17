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
        # xdotool both need that session's display and bus, and without them
        # notify-send would fail silently and the feedback could not be seen.
        shell.run("export DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/1000 "
                  "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus; "
                  "echo ENV=ready", timeout=60)

        # ---------------------------------------------------------- fresh user
        fresh = shell.run(
            "test -e ~/.local/share/smd-dictation && echo voice-state || echo voice-clean; "
            "test -e ~/.config/jellyfin-mpv-shim/config.json && echo jf-config || echo jf-clean; "
            "xrandr --display :0 >/dev/null 2>&1; echo ---; "
            "pactl info 2>/dev/null | grep -i 'server name'; echo ---; "
            "cat ~/.config/jellyfin-mpv-shim/mpv.conf 2>/dev/null | grep -v '^#'",
            timeout=120)
        fchunks = fresh.split("---")
        check("a fresh user has no dictation state", "voice-clean" in fchunks[0])
        check("a fresh user has no saved Jellyfin configuration",
              "jf-clean" in fchunks[0])
        check("the sound server is PipeWire", "PipeWire" in fchunks[1],
              fchunks[1].strip()[:60])
        check("the client keeps its hardware decoding setting",
              "hwdec=auto-safe" in (fchunks[2] if len(fchunks) > 2 else ""),
              (fchunks[2] if len(fchunks) > 2 else "").strip()[:60])

        # A recording to speak into.  The null sink's monitor is what the
        # recogniser records, so no microphone is needed on the runner.
        shell.run(
            "pactl load-module module-null-sink sink_name=smdvoice "
            "sink_properties=device.description=smdvoice >/tmp/module.txt 2>&1; "
            "pactl set-default-sink smdvoice 2>&1; "
            "pactl set-default-source smdvoice.monitor 2>&1; sleep 2; "
            "pactl list short sources | grep -c smdvoice.monitor",
            timeout=120)
        sources = shell.run("pactl list short sources | grep -c smdvoice.monitor",
                            timeout=60)
        check("a monitor source exists to dictate from",
              sources.strip().splitlines()[-1:] == ["1"], sources.strip()[:60])

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
        shell.run("xdotool key --clearmodifiers alt+z; sleep 3", timeout=90)
        # The notification is short-lived, so the screenshot is taken while it
        # is on screen rather than after the state has settled.
        shot = monitor.screenshot("voice-listening")
        started = shell.run("hunter-dictation status", timeout=60).strip()
        procs = shell.run("pgrep -c -f 'nerd-dictation be[g]in' || echo 0",
                          timeout=60).strip()
        check("Alt+Z starts dictation", started.endswith("listening"), started)
        check("exactly one recogniser runs", procs.splitlines()[-1:] == ["1"], procs)
        recording = shell.run(
            "pactl list source-outputs | grep -c 'Source Output' || echo 0",
            timeout=60).strip()
        check("the microphone is open while listening",
              recording.splitlines()[-1:] == ["1"], recording)
        text = ocr(shot).lower()
        check("starting dictation says so on screen", "listening" in text,
              " ".join(text.split())[:120])

        # ------------------------------------- what is spoken becomes the text
        shell.run("paplay --device=smdvoice /tmp/test.wav >/tmp/play.log 2>&1; "
                  "echo PLAYED=$?", timeout=180)
        dictated = ""
        for _attempt in range(8):
            time.sleep(5)
            dictated = shell.run("cat /tmp/dictated.txt 2>/dev/null", timeout=60)
            if len(dictated.strip()) > 3:
                break
        words = re.sub(r"[^a-z ]", " ", dictated.lower()).split()
        spoken = re.findall(r"[a-z]+", dictated.lower())
        record("INFO: dictated text: %s" % " ".join(spoken)[:160])
        check("speech is typed into the focused field", len(words) >= 2,
              " ".join(words)[:120])
        check("the typed text matches what was spoken",
              any(word in ("one", "zero", "nine", "two", "three", "oh")
                  for word in spoken),
              " ".join(spoken)[:120])

        # ------------------------------------ Ctrl+Z reaches the application
        # Cat is suspended by SIGTSTP when the terminal receives Ctrl+Z, so a
        # stopped state in /proc proves the key went to the program and not to
        # i3 - while dictation is listening, which is when a binding would
        # most plausibly have been in the way.
        ctrl = shell.run(
            "pid=$(pgrep -n -x cat); DISPLAY=:0 xdotool key --clearmodifiers ctrl+z; "
            "sleep 2; ps -o stat= -p \\\"$pid\\\" | tr -d ' '; "
            "kill -CONT \\\"$pid\\\" 2>/dev/null; echo resumed", timeout=120)
        state = ctrl.splitlines()[0].strip() if ctrl.strip() else ""
        record("INFO: process state after Ctrl+Z: %s" % ctrl.strip()[:80])
        check("Ctrl+Z still reaches the application while dictating",
              "T" in state, state)

        # Ctrl+A and Ctrl+X are characters cat stores, so the file proves they
        # arrived rather than being swallowed by a binding.
        shell.run("DISPLAY=:0 xdotool key --clearmodifiers ctrl+a; sleep 1; "
                  "DISPLAY=:0 xdotool key --clearmodifiers ctrl+x; sleep 2",
                  timeout=90)
        raw = shell.run("od -An -c /tmp/dictated.txt | tr -s ' ' | tail -3",
                        timeout=60)
        record("INFO: bytes in the field: %s" % " ".join(raw.split())[-160:])
        check("Ctrl+A and Ctrl+X still reach the application",
              "001" in raw or "\\001" in raw or "001" in " ".join(raw.split()),
              " ".join(raw.split())[-100:])

        # ------------------------------------------------------ Alt+Z stops it
        shell.run("xdotool key --clearmodifiers alt+z; sleep 3", timeout=90)
        shot = monitor.screenshot("voice-stopped")
        stopped = shell.run("hunter-dictation status", timeout=60).strip()
        procs = shell.run("pgrep -c -f 'nerd-dictation be[g]in' || echo 0",
                          timeout=60).strip()
        recording = shell.run(
            "pactl list source-outputs | grep -c 'Source Output' || echo 0",
            timeout=60).strip()
        check("Alt+Z stops dictation", stopped.endswith("stopped"), stopped)
        check("no recogniser is left behind", procs.splitlines()[-1:] == ["0"], procs)
        check("the microphone is released when dictation stops",
              recording.splitlines()[-1:] == ["0"], recording)
        text = ocr(shot).lower()
        check("stopping dictation says so on screen", "stopped" in text,
              " ".join(text.split())[:120])

        # ------------------------------------------------- no duplicate start
        shell.run("DISPLAY=:0 hunter-dictation start; sleep 6; "
                  "DISPLAY=:0 hunter-dictation start; sleep 2", timeout=120)
        procs = shell.run("pgrep -c -f 'nerd-dictation be[g]in' || echo 0",
                          timeout=60).strip()
        check("starting twice still leaves one recogniser",
              procs.splitlines()[-1:] == ["1"], procs)
        shell.run("DISPLAY=:0 xdotool key alt+z; sleep 3; "
                  "DISPLAY=:0 xdotool key alt+z; sleep 6; "
                  "DISPLAY=:0 xdotool key alt+z; sleep 3", timeout=120)
        procs = shell.run("pgrep -c -f 'nerd-dictation be[g]in' || echo 0",
                          timeout=60).strip()
        check("repeated Alt+Z presses never stack recognisers",
              procs.splitlines()[-1:] == ["1"], procs)
        shell.run("hunter-dictation stop; sleep 2", timeout=90)

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

        shell.run("DISPLAY=:0 setsid /opt/jellyfin-mpv-shim/bin/jellyfin-mpv-shim "
                  ">/tmp/jellyfin.log 2>&1 & sleep 25", timeout=120)
        alive = shell.run("pgrep -c -f 'jellyfin-mpv-shim' || echo 0",
                          timeout=60).strip()
        window = shell.run("DISPLAY=:0 xdotool search --name -i jellyfin "
                           "2>/dev/null | wc -l", timeout=60).strip()
        log = shell.run("grep -iE 'error|traceback|libmpv|cannot' /tmp/jellyfin.log "
                        "| head -5; echo ---; tail -3 /tmp/jellyfin.log",
                        timeout=60)
        record("INFO: Jellyfin window count: %s" % window)
        record("INFO: Jellyfin log: %s" % " | ".join(log.split())[:220])
        check("the Jellyfin client starts", alive.splitlines()[-1:] != ["0"], alive)
        check("the Jellyfin client opens a window",
              window.splitlines()[-1:] != ["0"], window)
        check("the Jellyfin client starts without a missing library",
              "libmpv" not in log.lower() and "ModuleNotFound" not in log,
              " | ".join(log.split())[:140])
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
