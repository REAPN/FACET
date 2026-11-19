#!/usr/bin/env python3
"""Rebuild the working tree the FACET scripts expect, from this repository.

Usage:
    python3 tools/make_worktree.py WORKDIR            copies every file to the path the scripts read it from
    python3 tools/make_worktree.py WORKDIR --link     symbolic links in place of copies
    cd WORKDIR && export FACET_ROOT=$PWD
"""
import csv, gzip, os, shutil, sys
from pathlib import Path

repo = Path(__file__).resolve().parent.parent
if len(sys.argv) < 2: sys.exit(__doc__)
work = Path(sys.argv[1]).resolve(); copy = "--link" not in sys.argv[2:]
n = 0
for r in csv.DictReader(open(repo / "MANIFEST.tsv", encoding="utf-8"), delimiter="\t"):
    if not r["original_path"]: continue
    src = repo / r["repo_path"]
    for orig in r["original_path"].split(" ; "):
        dst = work / orig
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() or dst.is_symlink(): dst.unlink()
        if "gzip of the original" in r["note"]:
            with gzip.open(src, "rb") as fi, open(dst, "wb") as fo: shutil.copyfileobj(fi, fo)
        elif copy: shutil.copy2(src, dst)
        else: os.symlink(src, dst)
        n += 1
print(n, "files placed under", work)
