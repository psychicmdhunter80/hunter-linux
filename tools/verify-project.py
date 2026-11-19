#!/usr/bin/env python3
"""Static checks for the SMD Linux build project.

This does not build an ISO. It validates everything that can be checked
without a Debian build host: YAML/XML syntax, desktop entries, shell syntax,
package lists, cross-references between the Calamares sequence and the module
configuration files, branding assets and line endings.

    python3 tools/verify-project.py [--live-build PATH]

--live-build points at a live-build source tree or /usr/share/live/build; when
given, every option used in auto/config is checked against the options that
live-build actually supports.
"""

import os
import re
import subprocess
import tempfile
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROOT = os.path.join(ROOT, "config", "includes.chroot")
CALAMARES = os.path.join(CHROOT, "etc", "calamares")

# Modules shipped by calamares 3.3.14-1 in Debian 13.
CALAMARES_MODULES = set("""
bootloader contextualprocess displaymanager dracut dracutlukscfg dummycpp
dummyprocess dummypython finished finishedq fsresizer fstab grubcfg hostinfo
hwclock initcpio initcpiocfg initramfs initramfscfg interactiveterminal
keyboard keyboardq license locale localecfg localeq luksbootkeyfile
luksopenswaphookcfg machineid mkinitfs mount netinstall networkcfg notesqml
oemid openrcdmcryptcfg packagechooser packagechooserq packages partition
plymouthcfg preservefiles rawfs removeuser services-openrc services-systemd
shellprocess summary summaryq tracking umount unpackfs unpackfsc users usersq
welcome welcomeq zfs zfshostid
""".split())

failures = []
warnings = []


def fail(message):
    failures.append(message)


def warn(message):
    warnings.append(message)


def read(path):
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return handle.read()


def walk(directory, suffix=None):
    for base, _dirs, files in os.walk(directory):
        for name in sorted(files):
            if suffix is None or name.endswith(suffix):
                yield os.path.join(base, name)


def check_line_endings():
    for path in walk(ROOT):
        if path.endswith((".png", ".zip", ".wav", ".pdf")):
            continue
        try:
            text = read(path)
        except UnicodeDecodeError:
            warn("%s is not UTF-8 text" % path)
            continue
        if "\r\n" in text:
            fail("%s uses CRLF line endings" % os.path.relpath(path, ROOT))
        if text and not text.endswith("\n"):
            warn("%s has no trailing newline" % os.path.relpath(path, ROOT))


def check_yaml():
    try:
        import yaml
    except ImportError:
        warn("PyYAML is not installed: YAML files were not parsed")
        return
    for path in sorted(os.listdir(os.path.join(CALAMARES, "modules"))):
        full = os.path.join(CALAMARES, "modules", path)
        try:
            data = yaml.safe_load(read(full))
        except Exception as error:  # noqa: BLE001 - report any parse error
            fail("%s: YAML error: %s" % (os.path.relpath(full, ROOT), error))
            continue
        if data is not None and not isinstance(data, dict):
            fail("%s: top level is not a mapping" % os.path.relpath(full, ROOT))
    for name in ("settings.conf", os.path.join("branding", "hunter", "branding.desc")):
        full = os.path.join(CALAMARES, name)
        try:
            yaml.safe_load(read(full))
        except Exception as error:  # noqa: BLE001
            fail("%s: YAML error: %s" % (os.path.relpath(full, ROOT), error))


def check_xml():
    count = 0
    for path in walk(CHROOT, ".xml"):
        try:
            ET.parse(path)
            count += 1
        except ET.ParseError as error:
            fail("%s: XML error: %s" % (os.path.relpath(path, ROOT), error))
    return count


def check_desktop_entries():
    count = 0
    for path in walk(ROOT, ".desktop"):
        text = read(path)
        if "[Desktop Entry]" not in text:
            fail("%s: missing [Desktop Entry]" % os.path.relpath(path, ROOT))
            continue
        for key in ("Type", "Name", "Exec"):
            if not re.search(r"^%s=" % key, text, re.M):
                fail("%s: missing %s=" % (os.path.relpath(path, ROOT), key))
        if "Exec=" in text and "\t" in text:
            warn("%s contains a tab character" % os.path.relpath(path, ROOT))
        count += 1
    return count


def check_shell():
    count = 0
    scripts = [os.path.join(ROOT, "auto", "config"), os.path.join(ROOT, "build.sh")]
    scripts += list(walk(os.path.join(ROOT, "config", "hooks")))
    scripts += list(walk(os.path.join(CHROOT, "usr", "local")))
    for path in scripts:
        if os.path.isdir(path):
            continue
        if path.endswith(".pyc") or "__pycache__" in path:
            fail("%s: compiled Python left in the tree"
                 % os.path.relpath(path, ROOT))
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                first = handle.readline()
        except OSError:
            continue
        if "python" in first:
            # Python helpers are checked with Python, not with bash. The
            # bytecode cache goes to a throwaway directory: py_compile would
            # otherwise leave a __pycache__ next to the helper, which the
            # compiled-Python check below then (rightly) refuses.
            with tempfile.TemporaryDirectory() as cache:
                env = dict(os.environ, PYTHONPYCACHEPREFIX=cache)
                result = subprocess.run(
                    [sys.executable, "-m", "py_compile", path],
                    capture_output=True, text=True, env=env
                )
        else:
            result = subprocess.run(
                ["bash", "-n", path], capture_output=True, text=True
            )
        if result.returncode != 0:
            fail("%s: shell syntax error: %s"
                 % (os.path.relpath(path, ROOT), result.stderr.strip()))
        count += 1
    # Hooks must be executable once deployed; live-build runs them through sh.
    for path in walk(os.path.join(ROOT, "config", "hooks")):
        if not path.endswith(".hook.chroot"):
            warn("%s does not end in .hook.chroot" % os.path.relpath(path, ROOT))
    return count


def check_package_lists():
    lists_dir = os.path.join(ROOT, "config", "package-lists")
    total = 0
    for path in walk(lists_dir, ".list.chroot"):
        seen = set()
        for number, line in enumerate(read(path).splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped != line:
                fail("%s:%d: leading or trailing whitespace"
                     % (os.path.relpath(path, ROOT), number))
            if " " in stripped:
                fail("%s:%d: more than one package on a line"
                     % (os.path.relpath(path, ROOT), number))
            if not re.match(r"^[a-z0-9][a-z0-9+.-]+$", stripped):
                fail("%s:%d: '%s' is not a valid package name"
                     % (os.path.relpath(path, ROOT), number, stripped))
            if stripped in seen:
                fail("%s:%d: duplicate package %s"
                     % (os.path.relpath(path, ROOT), number, stripped))
            seen.add(stripped)
            total += 1
    if total == 0:
        fail("no packages listed")
    return total


def check_calamares():
    try:
        import yaml
    except ImportError:
        return None
    settings = yaml.safe_load(read(os.path.join(CALAMARES, "settings.conf")))
    modules_dir = os.path.join(CALAMARES, "modules")
    configured = {name[:-5] for name in os.listdir(modules_dir) if name.endswith(".conf")}
    used = []
    for phase in settings.get("sequence", []):
        for key, values in phase.items():
            for entry in values:
                name = entry.split("@")[0]
                used.append(name)
                if name not in CALAMARES_MODULES and name not in configured:
                    fail("settings.conf: unknown module '%s'" % name)
                if name in CALAMARES_MODULES and name not in configured:
                    warn("settings.conf: module '%s' has no .conf (defaults used)" % name)
    for name in sorted(configured - set(used)):
        warn("module config %s.conf is never used in the sequence" % name)

    branding = settings.get("branding")
    branding_dir = os.path.join(CALAMARES, "branding", str(branding))
    if not os.path.isdir(branding_dir):
        fail("settings.conf: branding directory %s missing" % branding_dir)
        return len(used)
    desc = yaml.safe_load(read(os.path.join(branding_dir, "branding.desc")))
    for image in (desc.get("images") or {}).values():
        if image and not os.path.exists(os.path.join(branding_dir, image)):
            fail("branding: missing image %s" % image)
    slideshow = desc.get("slideshow")
    if slideshow and not os.path.exists(os.path.join(branding_dir, slideshow)):
        fail("branding: missing slideshow %s" % slideshow)
    if desc.get("slideshowAPI") != 2:
        warn("branding: slideshowAPI is not 2")
    return len(used)


def check_bootloaders():
    isolinux = os.path.join(ROOT, "config", "bootloaders", "isolinux")
    grub = os.path.join(ROOT, "config", "bootloaders", "grub-pc")
    for path in (os.path.join(isolinux, "menu.cfg"),
                 os.path.join(isolinux, "stdmenu.cfg"),
                 os.path.join(isolinux, "live.cfg.in"),
                 os.path.join(isolinux, "isolinux.cfg"),
                 os.path.join(grub, "grub.cfg"),
                 os.path.join(grub, "live-theme", "theme.txt")):
        if not os.path.exists(path):
            fail("missing bootloader file %s" % os.path.relpath(path, ROOT))
    if not os.path.exists(os.path.join(isolinux, "splash.png")):
        fail("missing isolinux splash.png")
    if not os.path.exists(os.path.join(grub, "splash.png")):
        fail("missing grub splash.png")
    for item in (os.path.join(isolinux, "stdmenu.cfg"),
                 os.path.join(isolinux, "menu.cfg"),
                 os.path.join(isolinux, "live.cfg.in")):
        if os.path.exists(item) and "splash.png" in read(item) and \
           not os.path.exists(os.path.join(isolinux, "splash.png")):
            fail("stdmenu.cfg references a missing splash.png")
    menu = read(os.path.join(isolinux, "menu.cfg"))
    for token in ("include live.cfg", "Advanced Boot Options"):
        if token not in menu:
            fail("isolinux menu.cfg is missing '%s'" % token)
    if "@OPTIONAL_INSTALLER_INCLUDE@" in menu:
        fail("isolinux menu.cfg still contains a live-build placeholder")


def check_autoconfig(live_build=None):
    text = read(os.path.join(ROOT, "auto", "config"))
    options = sorted(set(re.findall(r"^\s*(--[a-z0-9-]+)", text, re.M)))
    if not options:
        fail("auto/config has no lb config options")
    if live_build:
        config_script = None
        for candidate in (os.path.join(live_build, "scripts", "build", "config"),
                          os.path.join(live_build, "bin", "lb_config"),
                          os.path.join(live_build, "lb_config")):
            if os.path.exists(candidate):
                config_script = candidate
                break
        if not config_script:
            warn("could not find live-build's config script under %s" % live_build)
            return options
        supported = read(config_script)
        for option in options:
            if option not in supported:
                fail("auto/config uses unsupported option %s" % option)
    return options


def check_references():
    """Every path referenced from a shipped script or desktop file must exist."""
    referenced = {
        "/usr/local/bin/hunter-session": os.path.join(
            CHROOT, "usr", "local", "bin", "hunter-session"),
        "/usr/local/bin/hunter-power": os.path.join(
            CHROOT, "usr", "local", "bin", "hunter-power"),
        "/usr/local/bin/hunter-install": os.path.join(
            CHROOT, "usr", "local", "bin", "hunter-install"),
        "/usr/local/sbin/hunter-postinstall": os.path.join(
            CHROOT, "usr", "local", "sbin", "hunter-postinstall"),
        "/usr/share/backgrounds/hunter/wallpaper.png": os.path.join(
            CHROOT, "usr", "share", "backgrounds", "hunter", "wallpaper.png"),
        "/usr/share/doc/hunter-linux/shortcuts.html": os.path.join(
            CHROOT, "usr", "share", "doc", "hunter-linux", "shortcuts.html"),
        "/usr/share/icons/hicolor/scalable/apps/hunter-linux.svg": os.path.join(
            CHROOT, "usr", "share", "icons", "hicolor", "scalable", "apps",
            "hunter-linux.svg"),
    }
    for name, path in referenced.items():
        if not os.path.exists(path):
            fail("referenced path %s does not exist in the image" % name)
    for name in ("hunter-install.desktop", "hunter-power.desktop",
                 "hunter-shortcuts.desktop"):
        if not os.path.exists(os.path.join(CHROOT, "usr", "share", "applications", name)):
            fail("missing application entry %s" % name)


def check_version_labels():
    """Every label the image shows must carry the version auto/config builds.

    The 1.4 image still called itself 1.3 in the installer because the
    Calamares branding was never bumped; this keeps that from happening again.
    """
    # VERSION is the one place the release version is written.  Everything
    # else - the image name, the ISO label, the installer strings, the drawn
    # artwork - is derived from it, so a stale number in one of them is a
    # defect in the derivation, not something to fix by hand.
    version = read(os.path.join(ROOT, "VERSION")).strip()
    if not re.match(r"^[0-9]+\.[0-9]+(\.[0-9]+)?$", version):
        fail("VERSION does not hold a version: %r" % version)
        return None
    derived = [
        ("image name", "auto/config", r'--image-name "SMD-Linux-v\$\{VERSION\}"'),
        ("ISO label", "auto/config", r'--iso-volume "SMD_LINUX_\$\{VOLUME\}"'),
        ("ISO application", "auto/config", r'--iso-application "SMD Linux \$\{VERSION\}"'),
        ("image filename", "build.sh", r'IMAGE_NAME="SMD-Linux-v\$\{VERSION\}-amd64\.iso"'),
        ("artwork version", "tools/make-assets.py", r'"VERSION"'),
        ("build workflow name", ".github/workflows/build.yml",
         r'-amd64\.iso'),
    ]
    for name, path, pattern in derived:
        found = re.search(pattern, read(os.path.join(ROOT, path)))
        if not found:
            fail("%s is no longer derived from VERSION in %s" % (name, path))

    labels = [
        ("Calamares productName", "etc/calamares/branding/hunter/branding.desc",
         r'productName:\s+"SMD Linux ([0-9.]+)"'),
        ("Calamares version", "etc/calamares/branding/hunter/branding.desc",
         r'\bversion:\s+"([0-9.]+)"'),
        ("Calamares versionedName", "etc/calamares/branding/hunter/branding.desc",
         r'versionedName:\s+"SMD Linux ([0-9.]+)"'),
        ("/etc/issue", "etc/issue", r"SMD Linux ([0-9.]+)"),
        ("/etc/os-release", "etc/os-release", r'PRETTY_NAME="SMD Linux ([0-9.]+)"'),
        ("/etc/lsb-release", "etc/lsb-release",
         r'DISTRIB_DESCRIPTION="SMD Linux ([0-9.]+)"'),
        ("shortcuts page", "usr/share/doc/hunter-linux/shortcuts.html",
         r"Keyboard shortcuts &mdash; version ([0-9.]+)"),
        ("GRUB theme title", "../bootloaders/grub-pc/live-theme/theme.txt",
         r'title-text:\s+"SMD Linux ([0-9.]+)"'),
        ("VERSION file", "../../VERSION", r"^\s*([0-9.]+)\s*$"),
        ("README on the disc", "../../config/includes.binary/README.txt",
         r"^SMD LINUX ([0-9.]+)"),
    ]
    for name, path, pattern in labels:
        full = os.path.normpath(os.path.join(CHROOT, path))
        if not os.path.exists(full):
            fail("version label %s: %s is missing" % (name, path))
            continue
        found = re.search(pattern, read(full))
        if not found:
            fail("version label %s: no version found in %s" % (name, path))
        elif found.group(1) != version:
            fail("version label %s says %s but the image builds %s"
                 % (name, found.group(1), version))
    # The disc's README also tells the reader which file to write.
    disc = read(os.path.join(ROOT, "config", "includes.binary", "README.txt"))
    for named in re.findall(r"SMD-Linux-v([0-9.]+)-amd64\.iso", disc):
        if named != version:
            fail("the README on the disc points at the %s image" % named)

    # The artwork is the one place a version is drawn rather than written, so
    # the generator itself must have none of its own.
    assets = read(os.path.join(ROOT, "tools", "make-assets.py"))
    for found in re.findall(r'"(?:VERSION |version )?([0-9]+\.[0-9]+)"',
                            assets):
        fail("make-assets.py draws a hardcoded version %s" % found)

    return version


def check_voice_typing():
    """Alt+Z must be wired end to end, and Ctrl must stay the application's.

    The image once carried a dictation setup elsewhere but no code for it here,
    and a binding is easy to add without the program it calls.  These checks
    tie the key, the menu entry, the toggle and the engine together.
    """
    i3 = read(os.path.join(CHROOT, "etc", "skel", ".config", "i3", "config"))
    if not re.search(r"^bindsym\s+\$mod\+z\s+exec\s+[^\n]*hunter-dictation\s+toggle",
                     i3, re.M):
        fail("i3: Alt+Z is not bound to hunter-dictation toggle")
    # Ctrl+Z is Undo, Ctrl+X is Cut and Ctrl+A is Select All.  Binding any of
    # them would swallow the key from the focused application.
    for key in ("Control+z", "Control+x", "Control+a"):
        if re.search(r"^bindsym[^\n]*\b%s\b" % re.escape(key), i3, re.M | re.I):
            fail("i3: %s is bound, which would take Undo/Cut/Select All from "
                 "the application" % key)

    entry = os.path.join(CHROOT, "usr", "share", "applications",
                         "smd-dictation.desktop")
    if not os.path.exists(entry):
        fail("missing application entry smd-dictation.desktop")
    elif "hunter-dictation toggle" not in read(entry):
        fail("smd-dictation.desktop does not run hunter-dictation toggle")

    toggle_path = os.path.join(CHROOT, "usr", "local", "bin", "hunter-dictation")
    if not os.path.exists(toggle_path):
        fail("missing /usr/local/bin/hunter-dictation")
        return
    toggle = read(toggle_path)
    engine = re.search(r"^NERD=(/usr/share/nerd-dictation/\S+)$", toggle, re.M)
    if not engine:
        fail("hunter-dictation does not name the dictation engine")
    elif not os.path.exists(os.path.join(CHROOT, engine.group(1).lstrip("/"))):
        fail("the dictation engine %s is not in the image" % engine.group(1))
    model = re.search(r"^MODEL=/usr/share/vosk/(\S+)$", toggle, re.M)
    if not model:
        fail("hunter-dictation does not name the speech model")
    else:
        hook = read(os.path.join(ROOT, "config", "hooks", "live",
                                 "0360-smd-clients.hook.chroot"))
        if model.group(1) not in hook:
            fail("the build hook does not install the model hunter-dictation uses")
    if "--vosk-model-dir" not in toggle:
        fail("hunter-dictation does not pass the model to the engine")
    # Only what the script actually sends counts: its comments talk about
    # Ctrl+Z on purpose.
    if re.search(r"xdotool[^\n]*ctrl\+z", toggle, re.I):
        fail("hunter-dictation sends Ctrl+Z, which would take Undo away")
    if re.search(r"/home/[a-z]", toggle):
        fail("hunter-dictation hardcodes a home directory")

    sheet = read(os.path.join(CHROOT, "usr", "share", "doc", "hunter-linux",
                              "shortcuts.html"))
    if "<kbd>Z</kbd>" not in sheet:
        fail("the shortcut sheet does not document Alt+Z")


def check_jellyfin():
    """The client, its menu entry and the absence of anyone's account.

    A configuration directory for the shim once existed while the shim itself
    was never installed, so the entry and the package are checked separately.
    """
    entry = os.path.join(CHROOT, "usr", "share", "applications",
                         "jellyfin-mpv-shim.desktop")
    if not os.path.exists(entry):
        fail("missing application entry jellyfin-mpv-shim.desktop")
    else:
        exe = re.search(r"^Exec=(\S+)$", read(entry), re.M)
        if not exe or not exe.group(1).startswith("/opt/jellyfin-mpv-shim/"):
            fail("the Jellyfin entry does not run the client from its "
                 "virtualenv")

    hook_path = os.path.join(ROOT, "config", "hooks", "live",
                             "0360-smd-clients.hook.chroot")
    if not os.path.exists(hook_path):
        fail("the hook that installs the non-Debian clients is missing")
        return
    hook = read(hook_path)
    if not re.search(r'jellyfin-mpv-shim==\$\{?JELLYFIN_VERSION', hook):
        fail("the build hook does not install the Jellyfin client at a pinned "
             "version")
    if "import jellyfin_mpv_shim" not in hook:
        fail("the build hook does not prove the Jellyfin client imports")

    # Late on the image, nothing may start it: the user starts the client.
    autostart = os.path.join(CHROOT, "etc", "xdg", "autostart")
    if os.path.isdir(autostart):
        for name in os.listdir(autostart):
            if "jellyfin" in name.lower():
                fail("etc/xdg/autostart/%s starts the Jellyfin client" % name)

    skel = os.path.join(CHROOT, "etc", "skel", ".config", "jellyfin-mpv-shim")
    if os.path.isdir(skel):
        for name in sorted(os.listdir(skel)):
            if name != "mpv.conf":
                fail("etc/skel/.config/jellyfin-mpv-shim/%s would ship a saved "
                     "setting" % name)
        settings = os.path.join(skel, "mpv.conf")
        if os.path.exists(settings) and "hwdec=auto-safe" not in read(settings):
            fail("the client's hardware decoding setting was changed")


def main():
    live_build = None
    if "--live-build" in sys.argv:
        live_build = sys.argv[sys.argv.index("--live-build") + 1]

    check_line_endings()
    check_yaml()
    xml_count = check_xml()
    desktop_count = check_desktop_entries()
    shell_count = check_shell()
    package_count = check_package_lists()
    module_count = check_calamares()
    check_bootloaders()
    options = check_autoconfig(live_build)
    check_references()
    check_voice_typing()
    check_jellyfin()
    version = check_version_labels()

    print("SMD Linux project verification")
    print("  XML files parsed:        %d" % xml_count)
    print("  desktop entries checked: %d" % desktop_count)
    print("  shell scripts checked:   %d" % shell_count)
    print("  packages listed:         %d" % package_count)
    if module_count is not None:
        print("  calamares modules used:  %d" % module_count)
    print("  lb config options:       %d" % len(options))
    print("  version labels agree:    %s" % (version or "not checked"))
    if live_build:
        print("  options checked against live-build: yes")
    print()

    for message in warnings:
        print("WARNING: %s" % message)
    for message in failures:
        print("FAIL:    %s" % message)

    if failures:
        print("\n%d problem(s) found." % len(failures))
        return 1
    print("All static checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
