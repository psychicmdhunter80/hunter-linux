"""One-shot: documentation for the findings measured on Craig."""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def edit(path, pairs):
    target = ROOT / path
    text = target.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
    for old, new in pairs:
        if old not in text:
            raise SystemExit("MISSING in %s: %r" % (path, old[:70]))
        text = text.replace(old, new, 1)
    target.write_bytes(text.encode("utf-8"))


edit("REPAIR-REPORT.md", [
    ("""**Not proven here:** the VM has a QEMU adapter, not Intel Bay Trail, so the test
can only prove that TearFree is *not* forced onto unrelated graphics. Whether
the picture is tear-free on the Chromebook needs a physical playback test.""",
     """There were two bugs, and both had to be fixed before the file survived a boot:

1. `hunter-graphics` was committed with Windows line endings, so its shebang was
   unreadable and the unit failed with "No such file or directory" instead of
   running. The whole tree is now normalised to LF by
   `tools/normalize-line-endings.py`, and the unit is active in the tests.
2. The PCI test searched for `8086:<id>.*VGA`, but `lspci -nn` prints the class
   first - `00:02.0 VGA compatible controller [0300]: Intel ... [8086:0f31]` -
   so it never matched on the Chromebook and the service deleted
   `20-intel.conf` again on every boot. It now searches `VGA.*8086:<id>`, and a
   boot-test check feeds it a real Chromebook line to prove the match.

**Not proven here:** the VM has a QEMU adapter, not Intel Bay Trail, so the test
can only prove that TearFree is *not* forced onto unrelated graphics. Whether
the picture is tear-free on the Chromebook needs a physical playback test."""),
    ("""The ALSA hardware values from the original machine (Speaker raw 20, Digital raw
15, headphone attenuation raw 18) belong to its chtmax98090 codec and are
deliberately not applied here. The separate fifteen-seconds-of-silence
observation is untouched and remains unexplained.""",
     """On the Chromebook, PipeWire at 125 % was still not the whole fix: the codec's
UCM startup left `Speaker Volume` at raw 10 (-14 dB), so the same sink level was
quieter than the level tuned by hand at raw 20 (0 dB). `hunter-audio-hw.service`
now handles that, scoped to hardware: it looks for a max98090 codec in
`/proc/asound`, and only then backs up `EnableSeq.conf` to
`EnableSeq.conf.smd-backup`, changes **only** the `Speaker Volume` line to raw
20, and sets the running mixer with `amixer` before the sound server starts.
Machines without that codec are left untouched, and the boot test asserts that
no UCM file was edited on the virtual machine.

**The delayed Jellyfin audio.** On the Chromebook the same playback started with
about fifteen seconds of silence, with repeated ALSA XRUNs and PipeWire logging
`snd_pcm_avail after recover: Broken pipe`. The default quantum was too small
for the codec. `/etc/pipewire/pipewire.conf.d/50-hunter-quantum.conf` pins
`default.clock.quantum`, `min-quantum` and `max-quantum` to **2048**; on the
installed system a forced quantum of 2048 gave immediate audio across several
browser tabs and still worked after a reboot. This is a sound-server setting,
not a Jellyfin one, so it applies to every application."""),
    ("""### 0.4 Resource use""",
     """### 0.7 Jellyfin playback

The Jellyfin MPV shim decoded in software, which dropped frames on Bay Trail.
1.3 ships Debian's `i965-va-driver` and a shim `mpv.conf` with
`hwdec=auto-safe` - auto-safe keeps the software path for machines without
VA-API, so the same default file is safe everywhere. A short measurement on the
Chromebook showed no dropped frames, but longer runs still dropped some, so
hardware decoding is a clear improvement rather than a guarantee.
`display-resample` is deliberately absent: it was tried and made dropping worse.

The CPU governor was also tested on the Chromebook and made no noticeable
difference, so 1.3 does not switch to performance mode and adds no governor
work.

### 0.4 Resource use"""),
])

edit("RELEASE-NOTES-1.3.md", [
    ("""* **Speaker volume.** `hunter-volume` reproduces the level Hunter tuned by hand""",
     """* **Jellyfin playback.** The ISO ships Debian's `i965-va-driver` and an
  `mpv.conf` for the Jellyfin MPV shim with `hwdec=auto-safe`, so the Chromebook
  decodes in hardware instead of software; machines without the driver fall
  back to software. `display-resample` is not set - it made frame dropping worse
  in testing.
* **Speaker volume.** `hunter-volume` reproduces the level Hunter tuned by hand"""),
    ("""  of it. It is a sink-level setting, so nothing is specific to Jellyfin. The""",
     """  of it. It is a sink-level setting, so nothing is specific to Jellyfin. On
  the Chromebook the codec's own startup level (raw 10, -14 dB) was also raised
  to the accepted raw 20 (0 dB) by `hunter-audio-hw.service`, which backs up the
  UCM file first and does nothing at all on machines without that codec. The
  delayed Jellyfin audio is addressed by pinning the PipeWire quantum to 2048,
  the value that produced immediate audio on the installed system. The"""),
])

edit("README.md", [
    ("""Jellyfin. The volume keys keep working normally on top of it.""",
     """Jellyfin. The volume keys keep working normally on top of it. On the
Chromebook the codec's quiet startup level is corrected by
`hunter-audio-hw.service`, which only acts on max98090 hardware and backs up the
UCM file it edits. PipeWire's quantum is pinned to 2048 in
`/etc/pipewire/pipewire.conf.d/50-hunter-quantum.conf`, which is what removed the
silent start in Jellyfin on that machine."""),
])

edit("Test-Report.md", [
    ("""**Additions in this build:** the speaker-volume policy (`hunter-volume`) and
the TearFree self-report (`hunter-graphics --report`). TearFree itself is the 1.1
implementation, now with checks that the unit is enabled, that it ran, and that
the Intel driver is not forced onto the VM's virtual adapter.""",
     """**Additions in this build:** the speaker-volume policy (`hunter-volume`), the
hardware-scoped codec fix (`hunter-audio-hw`), the pinned PipeWire quantum, the
VA-API driver with the shim's `mpv.conf`, and the TearFree self-report
(`hunter-graphics --report`). TearFree itself is the 1.1 implementation, now with
a corrected `lspci` match, checks that the unit is enabled and active, that the
Intel driver is not forced onto the VM's virtual adapter, and a check that feeds
the matcher a real Chromebook `lspci` line."""),
])

print("documentation updated for Craig's findings")
