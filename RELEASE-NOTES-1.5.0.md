# SMD Linux 1.5.0 - release notes

**Candidate for hardware acceptance.** 1.5.0 adds the two clients that were
agreed but missing from the 1.4 builds, and repairs the installation test.
It keeps the repaired tiling behaviour of 1.4.1.

| | |
| --- | --- |
| Image | `SMD-Linux-v1.5.0-amd64.iso` |
| Size | 1,134,166,016 bytes (1.06 GiB) |
| SHA-256 | `9820f5fab9c04bcc9d3a47c3d0e85f41873b0390d1ce597cd9aa3ccf61fa1952` |
| Build | Actions run `44196246894` |
| Source | `SMD-Linux-Build-v1.5.0.zip`, checksums in `SHA256SUMS` |
| Installed packages | 942 |

## Why 1.4.1 could not simply be reused

A configuration directory for the Jellyfin client existed, but the client
itself was never installed, and there was no voice typing code at all. Both are
new contents, so the image cannot keep the 1.4.1 name or its checksum, and the
1.4.1 results cannot be claimed for this file.

## 1. Jellyfin client

Jellyfin MPV Shim **3.3.0** - the same version Craig installed separately - is
now part of the image, with `mpv` 0.40.0 and `libmpv2` for playback.

* In the application menu as **Jellyfin**.
* Installed from PyPI into its own virtualenv at `/opt/jellyfin-mpv-shim`,
  because Debian does not package it and installing into the system interpreter
  would shadow Debian's own Python libraries for every other program.
* **Client only**: no Jellyfin server, no server address, no account, no
  credentials, no profile.
* **No autostart**: it runs when you open it.
* Its hardware decoding setting (`hwdec=auto-safe`) is unchanged from 1.4.
* The build fails if the client does not import or if `libmpv.so.2` cannot be
  loaded.

## 2. Voice typing on Alt+Z

Offline speech-to-text, with nerd-dictation and Vosk 0.3.45.

* **Alt+Z** starts listening; **Alt+Z** again stops it. The words are typed
  into whichever text field has the cursor.
* A notification says *listening* and then *stopped*. The same switch is in the
  application menu as **Voice Typing**.
* The **small English model ships on the image**, so the first use needs no
  network connection.
* Recording and recognition end together: the microphone stream is closed and
  the recogniser exits when it is switched off. Nothing listens in the
  background, and a second press can never start a second recogniser.
* **Ctrl+Z, Ctrl+X and Ctrl+A are untouched.** This build never had the
  experimental Ctrl+Z dictation binding, so there is no Undo to restore; the
  keys are simply not bound anywhere and keep reaching the application, which
  is now proved in the automated test.
* `Alt+Z` is documented on the shortcut sheet (desktop icon and Alt+F1).

The dictation engine is shipped unmodified in the source archive and the image,
with its licence and checksums in `/usr/share/doc/nerd-dictation/copyright`.

## 3. Tiling, installation and labels

* The 1.4.1 tiling fix is carried over unchanged: one window fills the desktop,
  two are equal halves, the third sits below the first on the left with the
  second full height on the right, and four make an even 2x2 grid. The tiling
  test now runs the guest at **1366x768**, Craig's own resolution, with the
  panel's strip excluded from the window area.
* The **dialog** check is real now. The previous version looked for the message
  text in the i3 tree, never found it, and recorded a pass anyway. A window that
  does not appear now fails the run.
* Every version label - installer branding, `/etc/issue`, `/etc/os-release`,
  `/etc/lsb-release`, the GRUB theme title, the shortcut sheet, the README on
  the disc and the generated artwork - says **1.5.0**, and the static check
  fails the build if any of them disagrees.
* The **installation test** failure on 1.4.1 was a harness defect, not an image
  defect: it attached to the serial console after taking two screenshots, and
  QEMU keeps no output for a client that connects later, so the login prompt of
  the installed system was lost. The port is now opened before the machine
  boots, an Enter re-requests a prompt, and the shell that runs the installed
  checks proves it is the installed disk rather than a live session. See
  `Test-Report.md` for what this run found.

## What is verified on this image

Automated, in virtual machines: live boot under BIOS and UEFI, branding,
panel, audio, Brave with its extensions, VLC, locking, the tiling layouts at
1366x768 with idle stability, the installer's version label with a screenshot,
Alt+Z start/stop with a known recording typed into a real text field, the
Jellyfin client starting and carrying its configuration, and installation to a
disposable disk followed by booting and logging into that disk. The exact
numbers and the run IDs are in `Test-Report.md`.

**Still for Craig's machine**, because no VM can answer them: loudness and
quality through the real speakers and headphones, playback and tearing on the
panel, the printed top-row keys, Wi-Fi against his access points,
suspend and lid behaviour, and the battery percentage. Dictation accuracy in a
real room, and playback from his own Jellyfin server, are likewise his to
confirm.

One known rough edge: the MPV Shim runs in its own virtual environment and
logs `No module named 'gi'` at start-up, so its tray icon and its own
notifications stay inactive. Playback and the window are unaffected. The
fix is `python3-gi` inside that environment, deferred rather than hidden.

Hunter has run this candidate on Craig: the tiling behaves correctly,
including four Brave windows settling into the intended 2x2 grid. Everything
else on the hardware list is still his to check, and the next-release requests
raised during this work are collected in `NEXT-RELEASE.md` rather than being
folded into 1.5.0.

## Upgrading and rollback

1.4.1, 1.4, 1.3 and 1.2 remain as they were; their tags (`v1.4`, `v1.3`,
`v1.2`) are untouched and point at the contents they always did. 1.5.0 has its
own ISO, its own checksum and its own source archive.

## Files in this delivery

```
SMD-Linux-v1.5.0-amd64.iso              the image
SMD-Linux-Build-v1.5.0.zip              sources, assets and build inputs
SMD-Linux-v1.5.0-README.md              user documentation
SMD-Linux-v1.5.0-Test-Report.md         test report
SMD-Linux-v1.5.0-RELEASE-NOTES.md       these notes
SMD-Linux-v1.5.0-Technical-Reference.md package manifest, provenance, limitations
SHA256SUMS                              checksums of everything above
```

Verify with `sha256sum -c SHA256SUMS`.
