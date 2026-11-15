"""Rewrite every text file in the project with LF line endings.

The repository is consumed by Linux tools - shell shebangs, live-build hooks,
Calamares YAML - and `tools/verify-project.py` already treats CRLF as a failure.
Windows editors reintroduce it, and a CRLF shebang makes a script unrunnable
("No such file or directory"), so normalise the whole tree.
"""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKIP = {".git", "art", "dist", "iso13", "iso13f", "k11", "m12", "p12", "q12",
        "r12", "s13", "t13", "u13", "v13", "w13", "__pycache__"}


def main():
    changed = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix in {".png", ".zip", ".iso", ".pyc"}:
            continue
        relative = path.relative_to(ROOT)
        if any(part in SKIP for part in relative.parts):
            continue
        data = path.read_bytes()
        if b"\r" not in data:
            continue
        path.write_bytes(data.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
        changed.append(str(relative))
    print("normalised %d files" % len(changed))
    for name in changed:
        print("  " + name)


if __name__ == "__main__":
    main()
