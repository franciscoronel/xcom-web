#!/usr/bin/env python3
"""Package the extracted X-COM Apocalypse files into a js-dos bundle.

Bundle layout (js-dos v7.xx format):
  .jsdos/dosbox.conf  — REQUIRED js-dos config (same as dosbox.conf)
  .jsdos/jsdos.json   — optional extra config
  XCOM3/              — the game files (writable C: drive for saves)

CRITICAL (root cause of the "stuck at extraction" bug): js-dos's `_zip_to_fs`
creates only the immediate parent directory of each entry; it does NOT
recursively create grandparent directories. Directories that hold only
subdirectories (e.g. XCOM3/RAWSOUND) therefore never get created, and the first
file under them fails with "No such file or directory" (which surfaces as a
silent worker crash / stuck loading bar).

Fix: emit explicit directory entries (trailing "/") for every directory, ordered
parent-before-child (sorted by path depth), with the root XCOM3/ included. This
lets every intermediate directory be created before any file/child references it.

Archive is UNCOMPRESSED (ZIP_STORED) — js-dos Game Studio does the same for
performance. XCOM3 is a full install, so the CD is not required (DOSBox >= 0.73).
"""
import zipfile
import os
import sys

SRC = "/opt/data/dosgame/xcom_apoc"
OUT = "/opt/data/home/xcom-web/game/xcom.jsdos"
CONF = "/opt/data/home/xcom-web/game/dosbox.conf"

JSDOS_JSON = """{
  "version": "7.xx"
}
"""


def collect_dirs(base_dir):
    """Return all directory paths (relative to SRC) under base_dir, plus base_dir
    itself, sorted parent-before-child (by depth, then name)."""
    dirs = set()
    base_rel = os.path.relpath(base_dir, SRC)
    dirs.add(base_rel)  # e.g. "XCOM3"
    for root, dnames, fnames in os.walk(base_dir):
        for d in dnames:
            full = os.path.join(root, d)
            dirs.add(os.path.relpath(full, SRC))
    return sorted(dirs, key=lambda p: (p.count("/"), p))


def main():
    if not os.path.isdir(os.path.join(SRC, "XCOM3")):
        print("ERROR: XCOM3 dir not found under", SRC)
        sys.exit(1)
    if not os.path.exists(CONF):
        print("ERROR: dosbox.conf not found at", CONF)
        sys.exit(1)
    if os.path.exists(OUT):
        os.remove(OUT)

    count = 0
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_STORED) as z:
        # js-dos config dir + files
        z.writestr(".jsdos/", b"")
        z.writestr(".jsdos/dosbox.conf", open(CONF, "rb").read())
        z.writestr(".jsdos/jsdos.json", JSDOS_JSON)
        count += 3

        # Directory entries, parent-before-child (root XCOM3/ first).
        for d in collect_dirs(os.path.join(SRC, "XCOM3")):
            z.writestr(d + "/", b"")
            count += 1

        # All game files.
        for root, dirs, files in os.walk(os.path.join(SRC, "XCOM3")):
            for f in files:
                full = os.path.join(root, f)
                arc = os.path.relpath(full, SRC)
                z.write(full, arc)
                count += 1

    size = os.path.getsize(OUT)
    print(f"Bundle written: {OUT} ({count} entries, {size/1024/1024:.1f} MB, uncompressed)")


if __name__ == "__main__":
    main()
