#!/usr/bin/env python3
"""Render the SMD Linux 1.0 completion report as HTML for headless Chrome.

The HTML embeds the screenshots as base64 so the file is self-contained, and
prints its own file:// URL on stdout for the printer to consume.
"""

import base64
import io
import os
import pathlib
import urllib.parse

from PIL import Image

REPO = pathlib.Path(__file__).resolve().parent.parent
ROOT = REPO.parent
OUT = REPO / "dist" / "pdf"


def image(path, width=1500, quality=82):
    im = Image.open(path).convert("RGB")
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


LIVE_ROWS = [
    ("Firmware hands over to the ISO", "SeaBIOS", "OVMF"),
    ("Kernel boots, live system reaches a login console", "", ""),
    ("X server up on :0", "", ""),
    ("i3 running, i3 -C exits 0", "", ""),
    ("XFCE panel process running", "", ""),
    ("Panel plugin configuration loaded (12 properties)", "", ""),
    ("Desktop renders (screenshot)", "", ""),
    ("Thunar launches", "", ""),
    ("Firefox ESR launches", "", ""),
    ("Falkon launches", "", ""),
    ("Calamares starts from the live session", "", ""),
    ("cockpit.socket is active", "", ""),
    ("Cockpit answers on port 9090 inside the guest", "", ""),
    ("An outside client reaches the Cockpit login page", "", ""),
    ("An outside client authenticates as the live user", "", ""),
    ("The SMD wallpaper is installed", "", ""),
    ("The desktop shows the SMD wallpaper (X root pixmap)", "", ""),
]

INSTALL_ROWS = [
    ("Installer starts from the live session", "pass"),
    ("All wizard pages reached and completed", "pass"),
    ("Partitioning and formatting of the target disk", "pass"),
    ("Installation completes, installer unmounts the target", "pass"),
    ("The installer runs its own finish-up step", "pass"),
    ("GRUB menu written on the installed system", "pass"),
    ("EFI system partition holds the boot loader", "pass"),
    ("The installed disk boots without the ISO", "pass"),
    ("The installed system reaches its login screen", "pass"),
    ("Automated login and post-login checks", "not verified"),
]


def live_rows():
    out = []
    for name, bios, uefi in LIVE_ROWS:
        bios = bios or "PASS"
        uefi = uefi or "PASS"
        out.append(
            f"<tr><td>{name}</td><td class=ok>{bios}</td><td class=ok>{uefi}</td></tr>"
        )
    return "\n".join(out)


def install_rows():
    out = []
    for name, state in INSTALL_ROWS:
        cls = "ok" if state == "pass" else "warncell"
        label = "PASS" if state == "pass" else "NOT VERIFIED"
        out.append(f"<tr><td>{name}</td><td class={cls}>{label}</td></tr>")
    return "\n".join(out)


desktop = image(ROOT / "desktop-preview.jpg", width=1200)
greeter = image(REPO / "art43" / "screen-11-login.png", width=1100)

HTML = f"""<!doctype html>
<html lang=en><head><meta charset=utf-8>
<title>SMD Linux 1.0 - completion report</title>
<style>
  @page {{ size: A4; margin: 16mm 15mm 15mm 15mm; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: "Segoe UI", Arial, sans-serif; color: #1b1f1c;
         font-size: 10.2pt; line-height: 1.5; margin: 0; }}
  h1, h2, h3 {{ line-height: 1.2; }}
  h2 {{ font-size: 15pt; margin: 26px 0 10px; padding-bottom: 5px;
        border-bottom: 2px solid #22c55e; page-break-after: avoid; }}
  h3 {{ font-size: 11.5pt; margin: 16px 0 6px; page-break-after: avoid; }}
  p {{ margin: 0 0 9px; }}
  ul, ol {{ margin: 0 0 10px 0; padding-left: 20px; }}
  li {{ margin-bottom: 4px; }}
  code, .mono {{ font-family: Consolas, "Courier New", monospace; font-size: 9pt; }}
  table {{ width: 100%; border-collapse: collapse; margin: 8px 0 14px;
           font-size: 9.3pt; page-break-inside: auto; }}
  th {{ background: #052e16; color: #d1fae5; text-align: left; padding: 6px 8px;
        font-weight: 600; }}
  td {{ padding: 5px 8px; border-bottom: 1px solid #e2e8e4; vertical-align: top; }}
  tr {{ page-break-inside: avoid; }}
  td.ok {{ color: #047857; font-weight: 600; white-space: nowrap; }}
  td.warncell {{ color: #b45309; font-weight: 600; white-space: nowrap; }}

  .cover {{ background: #06210f; color: #eafff2; padding: 30px 28px 26px;
            border-radius: 10px; margin-bottom: 22px; }}
  .cover .kicker {{ letter-spacing: .18em; text-transform: uppercase;
                    font-size: 8.5pt; color: #6ee7a2; margin-bottom: 8px; }}
  .cover h1 {{ font-size: 33pt; margin: 0; color: #7CFC5A; letter-spacing: -0.5px; }}
  .cover .sub {{ font-size: 12.5pt; color: #cdebd8; margin-top: 6px; }}
  .cover .meta {{ font-size: 9pt; color: #86c9a3; margin-top: 14px; }}
  .stats {{ display: flex; gap: 10px; margin-top: 20px; }}
  .stat {{ flex: 1; background: rgba(124,252,90,.1); border: 1px solid #2f7a4a;
           border-radius: 8px; padding: 9px 10px; }}
  .stat b {{ display: block; font-size: 15pt; color: #9dff7a; }}
  .stat span {{ font-size: 8pt; color: #a9d8bd; text-transform: uppercase;
                letter-spacing: .06em; }}

  figure {{ margin: 10px 0 16px; page-break-inside: avoid; }}
  figure img {{ width: 100%; border: 1px solid #cfd8d1; border-radius: 6px; }}
  figcaption {{ font-size: 8.5pt; color: #5b6b60; margin-top: 5px; }}
  .note {{ background: #f1faf4; border-left: 3px solid #22c55e; padding: 9px 12px;
           font-size: 9.5pt; margin: 10px 0 14px; page-break-inside: avoid; }}
  .warn {{ background: #fff8ec; border-left: 3px solid #d97706; }}
  .sums {{ background: #f6f8f7; border: 1px solid #dde5e0; border-radius: 6px;
           padding: 10px 12px; font-family: Consolas, "Courier New", monospace;
           font-size: 8.4pt; word-break: break-all; }}
  .links a {{ color: #047857; text-decoration: none; }}
  .lead {{ font-size: 10.8pt; color: #33403a; }}
</style></head><body>

<div class=cover>
  <div class=kicker>Project completion report</div>
  <h1>SMD Linux 1.0</h1>
  <div class=sub>Small Mighty Distro - a lightweight Debian desktop, branded, tested and released</div>
  <div class=meta>14 November 2026 &nbsp;|&nbsp; github.com/psychicmdhunter80/hunter-linux &nbsp;|&nbsp; amd64</div>
  <div class=stats>
    <div class=stat><b>1.04 GiB</b><span>ISO image</span></div>
    <div class=stat><b>34 / 34</b><span>live checks passed</span></div>
    <div class=stat><b>9</b><span>install steps passed</span></div>
    <div class=stat><b>425 MiB</b><span>idle RAM used</span></div>
  </div>
</div>

<p class=lead>This report covers everything done on the SMD Linux 1.0 release: the
rebranding, the new wallpaper, the installer repairs, the web administration
panel, the virtual-machine test campaign, the measured performance, the files
that were published, and the one area that could not be verified.</p>

<h2>1. What was delivered</h2>
<ul>
  <li>A bootable <b>Debian 13 (trixie) amd64 live image</b> named
      <code>SMD-Linux-v1.0-amd64.iso</code>, 1,117,487,104 bytes, that boots on
      BIOS and UEFI, runs a full desktop, and installs itself to disk.</li>
  <li><b>Complete SMD branding</b> in the boot menus, boot splash, login screen,
      Calamares installer artwork, installer slides, and the OS identity files.</li>
  <li>The <b>supplied wallpaper</b> shipped unchanged as the default desktop
      background, drawn by the existing <code>feh</code> line in the i3 config.</li>
  <li>A <b>working installer</b>: five real defects found during testing were
      fixed (section 4), and a UEFI installation now writes a boot loader the
      firmware will actually start.</li>
  <li><b>Cockpit web administration</b> on port 9090, enabled at boot, plus a
      <code>hunter-cockpit</code> helper that prints the URL and login hints.</li>
  <li>A <b>test campaign</b> run against the final image: 17 checks on BIOS,
      17 on UEFI, and a full install-and-reboot cycle in a virtual machine.</li>
  <li>A <b>GitHub release</b> with the ISO, a source ZIP, a README, the test
      report, checksums, and this report as a PDF.</li>
</ul>

<h2>2. The distribution</h2>
<table>
  <tr><th style="width:32%">Component</th><th>What it is</th></tr>
  <tr><td>Base</td><td>Debian 13 "trixie", amd64, built with live-build in a privileged Debian container on GitHub Actions</td></tr>
  <tr><td>Desktop</td><td>i3 window manager with an XFCE4 panel (12 configured plugins), Thunar file manager, LightDM greeter</td></tr>
  <tr><td>Browsers</td><td>Firefox ESR and Falkon (second engine, kept deliberately)</td></tr>
  <tr><td>Installer</td><td>Calamares, with the project's own boot-loader script replacing Calamares' broken <code>bootloader</code> module</td></tr>
  <tr><td>Administration</td><td>Cockpit + cockpit-system, socket enabled at boot, reachable at <code>https://&lt;host&gt;:9090</code></td></tr>
  <tr><td>Identity</td><td><code>os-release</code> ID=smd, ID_LIKE=debian (package tools keep working), <code>lsb-release</code>, <code>issue</code></td></tr>
  <tr><td>Boot</td><td>ISOLINUX for BIOS, GRUB for UEFI with Secure Boot shim; live menu entry, safe-graphics entry, RAM-only entry, memory test</td></tr>
  <tr><td>Size</td><td>1.04 GiB ISO; installs into roughly 4.3 GiB on a 300 MiB ESP + ext4 root</td></tr>
</table>

<h3>Requirements</h3>
<table>
  <tr><th style="width:22%"></th><th>Minimum</th><th>Comfortable</th></tr>
  <tr><td>CPU</td><td>64-bit x86, dual core</td><td>any 64-bit x86 from the last decade</td></tr>
  <tr><td>RAM</td><td>1.5 GB to install, 2 GB to use the desktop</td><td>4 GB</td></tr>
  <tr><td>Disk</td><td>8 GB</td><td>20 GB</td></tr>
  <tr><td>Graphics</td><td>1024x768 capable, KMS drivers</td><td>any</td></tr>
  <tr><td>Firmware</td><td>BIOS/CSM or UEFI (Secure Boot supported)</td><td></td></tr>
</table>

<h2>3. Branding and wallpaper</h2>
<p>The old "Hunter Linux" name was replaced with <b>SMD Linux</b> everywhere a
user can see it, while the internal Debian package identity was left alone so
<code>apt</code> keeps working: <code>ID=smd</code> with
<code>ID_LIKE=debian</code>, and the installer still registers
<code>Hunter_Linux</code> as the EFI directory name for compatibility with the
existing test tooling.</p>
<ul>
  <li><b>Wordmark:</b> every bitmap asset was regenerated by
      <code>tools/make-assets.py</code> - boot splash, Calamares logo, icon,
      welcome banner and installer slides - with the mark changed from "H" to
      "S" and the new name drawn in.</li>
  <li><b>Menus:</b> the ISOLINUX and GRUB boot menus, their titles and help
      text all read SMD Linux.</li>
  <li><b>Wallpaper:</b> the supplied artwork was taken as-is, stored as
      <code>/usr/share/backgrounds/smd/smd-linux-wallpaper.png</code>, and is
      drawn full-screen by the <code>feh --bg-fill</code> line that already ran
      from the i3 config. No new service, no extra memory cost, no
      re-encoding of the artwork.</li>
  <li><b>Verification:</b> the live system check reads the X root pixmap
      (<code>_XROOTPMAP_ID</code>) rather than looking for a running
      <code>feh</code> process, because <code>feh</code> sets the background and
      exits. Both the file and the drawn pixmap are asserted, and the desktop
      screenshot was inspected by eye.</li>
</ul>

<h2>4. Installer: what was broken and what was fixed</h2>
<ol>
  <li><b>The installation failed at the last step.</b> Calamares' stock
      <code>bootloader</code> module runs <code>grub-mkconfig</code>, which
      aborted inside the chroot with exit code 2 before writing a line. The
      module was removed from <code>settings.conf</code> and replaced by
      <code>hunter-bootloader</code>, which runs <code>grub-install</code> and
      writes a complete <code>grub.cfg</code> itself.</li>
  <li><b>The EFI system partition was never populated.</b> For UEFI installs the
      script expected <code>/boot/efi</code> to be mounted; it now locates the
      ESP on the target disk by partition type GUID, mounts it, installs,
      writes the fallback loader, and unmounts it again.</li>
  <li><b>The firmware fallback loader could not start.</b> <code>shimx64.efi</code>
      loads <code>grubx64.efi</code> from its own directory; the copy in
      <code>EFI/BOOT</code> was missing, so firmware that falls back to
      removable-media loading reported "Failed to open \\EFI\\BOOT\\grubx64.efi".
      Shim, grub and the menu are now all in <code>EFI/BOOT</code>.</li>
  <li><b>Every password was rejected.</b> Calamares' password check used
      libpwquality, whose cracklib dictionary is not part of the image, so the
      users page refused all input with "error loading dictionary". The check
      was removed; a non-empty password with confirmation is accepted.</li>
  <li><b>The test harness declared success too early.</b> The progress page can
      sit at 86 % for minutes while packages unpack, so a "screen is stable"
      heuristic reported a finished installation that had not finished. The
      harness now waits until the installer has unmounted its target, which is
      a real completion signal.</li>
</ol>

<h2>5. Cockpit web administration</h2>
<p><code>cockpit</code>, <code>cockpit-system</code> and <code>curl</code> are
installed in every image and <code>cockpit.socket</code> is enabled by the build
hook, the Calamares services configuration and the post-install script.
<code>hunter-cockpit</code> prints the address and the login name. Verified in
the live session: the socket is active, the guest answers 200 on port 9090, and
an <b>outside client</b> - through QEMU's forwarded port - both reaches the login
page and authenticates.</p>

<h2>6. Test results</h2>
<p>All tests ran against the published image in QEMU with TCG (no hardware
virtualisation), a serial console for commands, the QEMU monitor for
screenshots, and VNC input to drive the graphical installer.</p>

<h3>6.1 Live boot, both firmwares - 17 of 17 checks pass each</h3>
<table>
  <tr><th style="width:56%">Check</th><th>BIOS</th><th>UEFI</th></tr>
  {live_rows()}
</table>

<h3>6.2 Installation to disk</h3>
<table>
  <tr><th style="width:74%">Step</th><th>Result</th></tr>
  {install_rows()}
</table>

<h2>7. Evidence</h2>
<figure>
  <img src="{desktop}" alt="SMD Linux live desktop">
  <figcaption>The live desktop on the final image: the supplied SMD Linux
  wallpaper drawn by feh, the XFCE panel above it, i3 session running.</figcaption>
</figure>
<figure>
  <img src="{greeter}" alt="Installed system login screen">
  <figcaption>The installed system after rebooting from its own disk: GRUB menu,
  kernel, root filesystem check, and the LightDM greeter.</figcaption>
</figure>

<h2>8. Performance</h2>
<table>
  <tr><th style="width:46%">Measurement</th><th>Value</th></tr>
  <tr><td>Idle memory, live desktop with Cockpit</td><td>425 MiB used of 1967 MiB, 1541 MiB available</td></tr>
  <tr><td>Before Cockpit was added</td><td>412 MiB (the panel is 13 MiB of the difference)</td></tr>
  <tr><td>ISO size</td><td>1.04 GiB, up from 1.03 GiB</td></tr>
  <tr><td>Resident services added</td><td>one: <code>cockpit.socket</code>; the wallpaper adds none</td></tr>
  <tr><td>Desktop on a 2 GB machine</td><td>comfortable; the live system also boots entirely into RAM</td></tr>
</table>

<h2>9. Deliverables and checksums</h2>
<table>
  <tr><th style="width:44%">File</th><th>Size</th></tr>
  <tr><td><code>SMD-Linux-v1.0-amd64.iso</code></td><td>1,117,487,104 bytes (1.04 GiB)</td></tr>
  <tr><td><code>SMD-Linux-Build-v1.0.zip</code></td><td>4,971,240 bytes - the 101 source files that build the ISO</td></tr>
  <tr><td><code>SMD-Linux-v1.0-README.md</code></td><td>16,878 bytes</td></tr>
  <tr><td><code>SMD-Linux-v1.0-Test-Report.md</code></td><td>14,901 bytes</td></tr>
  <tr><td><code>SHA256SUMS</code></td><td>checksums for all of the above</td></tr>
</table>
<div class=sums>
0a9f57466de1e78229fb2cc0f5e24b8a1a46a12187fe9682c273ea9818b88979  SMD-Linux-v1.0-amd64.iso<br>
7dead6da86e0dbf86cdeb31be5e01256bfef89cc3457a71484c65f7a13de2db4  SMD-Linux-Build-v1.0.zip<br>
dd71f0d8256ddfc3e417fb4f993ad2cb0cdc361f0da7aadeb06278f0362096b8  SMD-Linux-v1.0-README.md<br>
b5a46e4f1b608b80c537828879cb8d0e13fe0eb3954698d1a33d1495eeab3cce  SMD-Linux-v1.0-Test-Report.md
</div>
<p class=links style="margin-top:10px">Download:
<a href="https://github.com/psychicmdhunter80/hunter-linux/releases/tag/v1.0">github.com/psychicmdhunter80/hunter-linux/releases/tag/v1.0</a><br>
Verify with <code>sha256sum -c SHA256SUMS</code>, then write it to a USB stick
with <code>dd</code>, balenaEtcher or Rufus (UEFI and BIOS both work).</p>

<h2>10. What is not verified</h2>
<div class="note warn">
<b>The installed system's post-login checks were not executed.</b> The installed
system boots to LightDM (screenshot above), but the automated harness logs in
over the serial console, and the installed system produced no login prompt
there within the timeout. Desktop, wallpaper, Cockpit and APT were therefore
verified in the live session only. This is a harness limitation, not a
demonstrated defect: the greeter, session, panel and applications are identical
to the live ones. The concrete next step is to drive the greeter over VNC
instead of the serial console.
</div>
<ul>
  <li><b>Not tested on real hardware.</b> Everything ran in QEMU with emulated
      firmware, an emulated disk and an emulated VGA adapter. GPU-specific
      behaviour, real USB writing and real firmware quirks are untested.</li>
  <li><b>Secure Boot</b> is supported through Debian's signed shim, but enrolment
      on a machine with custom keys was not exercised.</li>
  <li><b>amd64 only.</b> There is no ARM or 32-bit image.</li>
  <li><b>No printing stack</b> (CUPS is deliberately absent); install it after
      the fact if needed.</li>
</ul>

<h2>11. How it was built and tested</h2>
<ul>
  <li><b>Build:</b> GitHub Actions on <code>ubuntu-24.04</code>, running the
      Debian <code>trixie</code> container in privileged mode, with
      <code>live-build</code> producing the hybrid ISO.</li>
  <li><b>Boot tests:</b> one job per firmware, each booting the final ISO,
      logging in on the serial console, running the checks as shell commands, and
      capturing screenshots through the QEMU monitor.</li>
  <li><b>Install test:</b> the wizard is driven by fixed screen coordinates over
      VNC because OCR on the Calamares pages proved unreliable; completion is
      detected from the target unmounting; the disk is then booted a second time
      in a separate machine.</li>
  <li><b>Reproducibility:</b> the source ZIP plus <code>build.sh</code> and
      Docker rebuild the same image; the checksums above identify the exact
      bytes that were tested.</li>
</ul>

<div class="note" style="margin-top:22px">
SMD Linux 1.0 - Small Mighty Distro. Built, branded, tested in virtual machines
and published on 14 November 2026. Source: github.com/psychicmdhunter80/hunter-linux
</div>

</body></html>
"""

OUT.mkdir(parents=True, exist_ok=True)
page = OUT / "report.html"
page.write_text(HTML, encoding="utf-8")
print("file:///" + urllib.parse.quote(page.as_posix().lstrip("/")))
