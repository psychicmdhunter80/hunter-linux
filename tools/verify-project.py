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
        if path.endswith(".png") or path.endswith(".zip"):
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

    print("SMD Linux project verification")
    print("  XML files parsed:        %d" % xml_count)
    print("  desktop entries checked: %d" % desktop_count)
    print("  shell scripts checked:   %d" % shell_count)
    print("  packages listed:         %d" % package_count)
    if module_count is not None:
        print("  calamares modules used:  %d" % module_count)
    print("  lb config options:       %d" % len(options))
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
