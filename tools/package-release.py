#!/usr/bin/env python3
"""Package the SMD Linux build project as a release archive.

Creates, in the directory above this project:

    SMD-Linux-Build-v1.1.zip          the build sources, with file modes
    SMD-Linux-v1.1-README.md          user documentation
    SMD-Linux-v1.1-Test-Report.md     test status and measurements
    SHA256SUMS                           checksums of the files above

File permissions are stored in the archive (0755 for scripts), so the project
can be unzipped and built without a chmod step.

    python3 tools/package-release.py
"""

import hashlib
import os
import shutil
import sys
import zipfile

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.dirname(PROJECT)
PROJECT_NAME = os.path.basename(PROJECT)

ZIP_NAME = "SMD-Linux-Build-v1.1.zip"
ISO_NAME = "SMD-Linux-v1.1-amd64.iso"
DOCS = {
    "README.md": "SMD-Linux-v1.1-README.md",
    "Test-Report.md": "SMD-Linux-v1.1-Test-Report.md",
}

SKIP_DIRS = {".git", ".tmp", "__pycache__", "binary", "chroot", "cache",
             ".build", ".freebuff", "dist"}
SKIP_SUFFIXES = (".iso", ".pyc", ".zsync", ".sha256", ".log")


def executable(relative_path):
    parts = relative_path.replace(os.sep, "/")
    if parts in ("build.sh", "auto/config"):
        return True
    if parts.endswith(".sh") or parts.endswith(".py"):
        return True
    if "/hooks/" in parts:
        return True
    if "usr/local/bin/" in parts or "usr/local/sbin/" in parts:
        return True
    if "/skel/Desktop/" in parts and parts.endswith(".desktop"):
        return True
    return False


def collect():
    for base, dirs, files in os.walk(PROJECT):
        # "art" directories hold captured test artefacts, not project files.
        dirs[:] = sorted(d for d in dirs
                         if d not in SKIP_DIRS and not d.startswith("art"))
        for name in sorted(files):
            if name.endswith(SKIP_SUFFIXES):
                continue
            full = os.path.join(base, name)
            yield full, os.path.relpath(full, PROJECT)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    zip_path = os.path.join(OUTPUT_DIR, ZIP_NAME)
    if os.path.exists(zip_path):
        os.remove(zip_path)

    count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for full, relative in collect():
            arcname = "%s/%s" % (PROJECT_NAME, relative.replace(os.sep, "/"))
            info = zipfile.ZipInfo(arcname, date_time=(2026, 11, 14, 0, 0, 0))
            mode = 0o755 if executable(relative) else 0o644
            # create_system must be Unix (3), otherwise unzip ignores the
            # permission bits and every file ends up non-executable.
            info.create_system = 3
            info.external_attr = ((0o100000 | mode) << 16) | 0o20
            info.compress_type = zipfile.ZIP_DEFLATED
            with open(full, "rb") as handle:
                archive.writestr(info, handle.read())
            count += 1

    print("packed %d files into %s (%.1f kB)"
          % (count, ZIP_NAME, os.path.getsize(zip_path) / 1024.0))

    delivered = []
    for source, target in DOCS.items():
        destination = os.path.join(OUTPUT_DIR, target)
        shutil.copyfile(os.path.join(PROJECT, source), destination)
        delivered.append(destination)
        print("wrote %s" % target)

    sums_path = os.path.join(OUTPUT_DIR, "SHA256SUMS")
    iso_path = os.path.join(OUTPUT_DIR, ISO_NAME)
    files = [zip_path] + delivered
    if os.path.exists(iso_path):
        files.insert(0, iso_path)
    with open(sums_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("# SMD Linux 1.1 checksums - verify with: sha256sum -c SHA256SUMS\n")
        if os.path.exists(iso_path):
            handle.write("# The first entry is the bootable ISO image.\n")
        else:
            handle.write("# The ISO image is not present in this directory.\n")
        for path in files:
            handle.write("# size %s bytes  %s\n" % (os.path.getsize(path),
                                                     os.path.basename(path)))
            handle.write("%s  %s\n" % (sha256(path), os.path.basename(path)))
    print("wrote SHA256SUMS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
