#!/usr/bin/env python3
"""Write the exact package manifest of the image from its dpkg status file.

    package-manifest.py <path to var/lib/dpkg/status> [output file]

The live image keeps /var/lib/dpkg/status inside the squashfs, so the manifest
can be produced without booting anything: the status file is unpacked from the
ISO and parsed here.  Output is one "name version arch" line per installed
package, sorted, with a header that records how many there are.
"""

import sys


def parse(path):
    packages = []
    name = version = arch = None
    installed = False
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if not line:
                if installed and name and version:
                    packages.append((name, version, arch or "?"))
                name = version = arch = None
                installed = False
                continue
            if line.startswith("Package: "):
                name = line[len("Package: "):].strip()
            elif line.startswith("Version: "):
                version = line[len("Version: "):].strip()
            elif line.startswith("Architecture: "):
                arch = line[len("Architecture: "):].strip()
            elif line.startswith("Status: "):
                installed = line.rstrip().endswith(" installed")
    if installed and name and version:
        packages.append((name, version, arch or "?"))
    return sorted(packages)


def main():
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    packages = parse(sys.argv[1])
    lines = ["# SMD Linux package manifest - %d packages installed" % len(packages),
             "# name version architecture"]
    lines += ["%s %s %s" % entry for entry in packages]
    text = "\n".join(lines) + "\n"
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        print("wrote %s (%d packages)" % (sys.argv[2], len(packages)))
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
