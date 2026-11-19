#!/usr/bin/env python3
import argparse, glob, os, re, subprocess, sys
from pathlib import Path

from criterion_spec import load_spec, extract

DSM_TR_PDF = "DSM 5 TR-APA 2022.pdf"
CACHE = "_dsm5tr_cache/dsm5tr_full.txt"

TRANSLATE = {
    "\u2019": "'",
    "\u2018": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u00ad": "",
    "\u2014": " ",
    "\u2013": "-",
    "\u2212": "-",
    "\u2010": "-",
    "\u00a0": " ",
    "\ufb01": "fi",
    "\ufb02": "fl",
}

FURNITURE = re.compile(
    r"^\s*(=+|-+|#|Diagnostic Criteria\s*$|Diagnostic Features\s*$|Specify|Note:|Coding note|"
    r"\d+\s*$|[A-F]\.\s*$)", re.I)


def norm(s):
    for k, v in TRANSLATE.items():
        s = s.replace(k, v)
    return re.sub(r"\s+", " ", s).strip()


def full_text(root):
    cache = Path(root) / CACHE
    if cache.exists() and cache.stat().st_size > 1_000_000:
        return cache.read_text(encoding="utf-8", errors="replace")
    pdf = Path(root) / DSM_TR_PDF
    if not pdf.exists():
        sys.exit(f"cannot verify: {pdf} not found. This is the ONLY accepted source of truth.")
    cache.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["pdftotext", "-layout", str(pdf), str(cache)], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"pdftotext failed: {r.stderr[:400]}")
    return cache.read_text(encoding="utf-8", errors="replace")


def gate(specs, tr, root, lines):
    failures = []
    for sp in specs:
        spec = load_spec(sp)
        criteria, _, _ = extract(spec, root)
        for it in spec["items"]:
            iid = it["item_id"]
            txt = norm(criteria[iid])
            ok = txt in tr
            if not ok:
                frags = [f for f in re.split(r"(?<=[.;:]) ", txt) if len(f) > 40]
                miss = [f for f in frags if f not in tr]
                ok = bool(frags) and not miss
                if not ok:
                    failures.append((spec["disorder"], iid, miss[:2] if frags else [txt[:160]]))
            lines.append(f"| {spec['disorder']} | {iid} | {'PASS' if ok else '**FAIL**'} | "
                         f"{len(txt)} | `{spec['criteria_txt']}` |")
            print(f"  {spec['disorder']:4s} {iid:3s}  {'PASS' if ok else 'FAIL'}")
    return failures


def sweep(paths, tr, root, lines):
    lines.append("\n## Whole-file sweep\n")
    lines.append("Sentences of 40 characters or more, checked against the PDF. Absent sentences are "
                 "either transcription errors or interpolations. Headings and structure are skipped.\n")
    lines.append("| file | sentences | in DSM-5-TR | absent | absent percent |")
    lines.append("|---|---|---|---|---|")
    detail = []
    for p in paths:
        f = Path(root) / p if not os.path.isabs(p) else Path(p)
        if not f.exists():
            continue
        raw = f.read_text(encoding="utf-8", errors="replace")
        body = "\n".join(ln for ln in raw.splitlines() if not FURNITURE.match(ln))
        sents = [norm(s) for s in re.split(r"(?<=[.:;])\s+", body)]
        sents = [s for s in sents if len(s) >= 40]
        absent = [s for s in sents if s not in tr]
        pct = 100 * len(absent) / max(1, len(sents))
        rel = str(f.relative_to(Path(root))) if str(f).startswith(str(root)) else str(f)
        lines.append(f"| `{rel}` | {len(sents)} | {len(sents)-len(absent)} | {len(absent)} | {pct:.0f}% |")
        print(f"  {rel:64s} {len(sents)-len(absent):4d}/{len(sents):4d} in DSM   {len(absent)} absent")
        if absent:
            detail.append((rel, absent))
    if detail:
        lines.append("\n### Sentences NOT found in DSM-5-TR\n")
        lines.append("Read these. A near-miss is a transcription error and should be corrected against "
                     "the PDF. A sentence with no DSM counterpart at all is an INTERPOLATION and the file "
                     "must not be quoted to any classifier.\n")
        for rel, absent in detail:
            lines.append(f"\n**`{rel}`**, {len(absent)} absent\n")
            for s in absent[:40]:
                lines.append(f"- {s[:260]}")
            if len(absent) > 40:
                lines.append(f"- ... and {len(absent)-40} more")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--specs", nargs="+", help="gate mode: criterion_specs/*.json")
    ap.add_argument("--sweep_files", nargs="+", help="sweep mode: whole preprocessed text files")
    ap.add_argument("--report")
    a = ap.parse_args()
    if not a.specs and not a.sweep_files:
        sys.exit("give --specs, --sweep_files, or both")
    root = os.environ.get("FACET_ROOT", ".")

    tr = norm(full_text(root))
    print(f"DSM-5-TR full text: {len(tr):,} normalised characters\n")

    lines = ["# Criterion provenance verification\n",
             "Checked against `DSM 5 TR-APA 2022.pdf` after normalising whitespace, curly quotes, soft "
             "hyphens and dash-family characters.\n"]
    failures = []
    if a.specs:
        specs = [s for pat in a.specs for s in (glob.glob(pat) or [pat])]
        lines += ["\n## Gate: every scored unit\n",
                  "A FAIL means the pipeline would quote text that is not in DSM-5-TR.\n",
                  "| disorder | unit | in DSM-5-TR | chars | source file |", "|---|---|---|---|---|"]
        failures = gate(specs, tr, root, lines)
        lines.append("")
        if failures:
            lines.append("### Gate failures\n")
            for d, iid, miss in failures:
                lines.append(f"- **{d} {iid}** not found. First missing fragment: "
                             f"`{miss[0][:200] if miss else ''}`")
        else:
            lines.append("All scored units verified verbatim against DSM-5-TR.\n")

    if a.sweep_files:
        paths = [s for pat in a.sweep_files for s in (glob.glob(os.path.join(root, pat)) or [pat])]
        sweep(sorted(paths), tr, root, lines)

    if a.report:
        p = Path(root) / a.report
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\nwrote {p}")
    if failures:
        sys.exit(f"\n{len(failures)} unit(s) FAILED provenance. Nothing should run until this is fixed.")
    if a.specs:
        print("\nall scored units verified verbatim against DSM-5-TR")


if __name__ == "__main__":
    main()
