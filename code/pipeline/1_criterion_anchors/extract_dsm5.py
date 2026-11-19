#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pypdf import PdfReader


def load_config(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_pdf_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    pages = []
    for page in reader.pages:
        txt = page.extract_text() or ""
        pages.append(txt)
    return "\n\n".join(pages)


def apply_text_replacements(
    text: str, replacements: Optional[List[Dict[str, Any]]] = None
) -> str:
    if not replacements:
        return text

    import sys as _sys
    for i, rule in enumerate(replacements, 1):
        mode = rule.get("mode", "literal")
        if mode == "region":
            start = rule["start_pattern"]
            end = rule["end_pattern"]
            replacement = rule["replacement"]
            include_anchors = rule.get("include_anchors", False)
            if include_anchors:
                pat = re.compile(start + r".*?" + end, re.DOTALL)
                new_text, n = pat.subn(replacement, text, count=1)
            else:
                pat = re.compile(
                    r"(" + start + r")(.*?)(" + end + r")", re.DOTALL,
                )
                new_text, n = pat.subn(r"\1" + replacement + r"\3", text, count=1)
            _sys.stderr.write(
                f"  [text_replacements] rule {i} (region): {'fired' if n else 'no match'}"
                + (f" — {rule['comment']}" if rule.get("comment") else "") + "\n"
            )
            text = new_text
        elif mode == "literal":
            find = rule["find"]
            replace = rule["replace"]
            n = text.count(find)
            text = text.replace(find, replace)
            _sys.stderr.write(
                f"  [text_replacements] rule {i} (literal): {find!r} -> {replace!r} "
                f"({n} occurrence(s))"
                + (f" — {rule['comment']}" if rule.get("comment") else "") + "\n"
            )
        else:
            _sys.stderr.write(
                f"  [text_replacements] rule {i}: unknown mode {mode!r}, skipped\n"
            )
    return text


def normalize_unicode_and_layout(text: str,
                                  options: Optional[Dict[str, Any]] = None) -> str:
    options = options or {}

    text = re.sub(r"(\w)­\s*\n\s*(\w)", r"\1\2", text)

    replacements = {
        "­": "",
        "‐": "-",
        "‑": "-",
        "‒": "-",
        "–": "-",
        "—": "-",
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "ﬁ": "fi",
        "ﬂ": "fl",
        "ﾾ": "",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)

    hyphen_min = options.get("hyphen_join_min_chars", 1)
    if hyphen_min == 1:
        text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    else:
        pat = r"([A-Za-z]{" + str(hyphen_min) + r",})-\s*\n\s*(\w)"
        text = re.sub(pat, r"\1\2", text)

    if options.get("criterion_marker_rejoin", False):
        text = re.sub(
            r"(?m)^([A-Z]|\d+)[ \t]*\n[ \t]*\.[ \t]*\n[ \t]*",
            r"\1. ",
            text,
        )

    if options.get("paren_note_rejoin", False):
        text = re.sub(r"\(\s*\nNote:\s*", "(Note: ", text)

    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def strip_chapter_bounds(text: str, start_anchor: str, end_anchor: str,
                          start_keep_match: bool = True) -> str:
    m = re.search(start_anchor, text, flags=re.IGNORECASE | re.MULTILINE)
    if m:
        text = (text[m.start():] if start_keep_match else text[m.end():]).strip()
    if end_anchor:
        m = re.search(end_anchor, text, flags=re.IGNORECASE | re.MULTILINE)
        if m:
            text = text[:m.start()].strip()
    return text


def find_heading_positions(text: str,
                            headings: List[Dict[str, str]]
                            ) -> List[Tuple[int, int, str]]:
    hits = []
    for h in headings:
        m = re.search(h["regex"], text, flags=re.IGNORECASE)
        if m:
            hits.append((m.start(), m.end(), h["name"]))
    hits.sort(key=lambda x: x[0])
    return hits


def clean_section_text(text: str, strip_patterns: List[str]) -> str:
    for pat in strip_patterns:
        text = re.sub(pat, "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def trim_diagnostic_criteria(text: str, anchors: List[str]) -> str:
    cut_points = []
    for pat in anchors:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            cut_points.append(m.start())
    if cut_points:
        text = text[:min(cut_points)]
    text = re.sub(
        r"Specify current severity:.*?(?=(?:\n?[A-E]\.)|\Z)",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return text.strip()


def split_sections(text: str,
                    headings: List[Dict[str, str]],
                    strip_patterns: List[str],
                    trim_anchors: List[str]) -> "OrderedDict[str, str]":
    hits = find_heading_positions(text, headings)
    sections: OrderedDict[str, str] = OrderedDict()
    if not hits:
        return sections
    for i, (_, end, name) in enumerate(hits):
        next_start = hits[i + 1][0] if i + 1 < len(hits) else len(text)
        body = text[end:next_start].strip()
        body = clean_section_text(body, strip_patterns)
        if name == "Diagnostic Criteria":
            body = trim_diagnostic_criteria(body, trim_anchors)
        sections[name] = body
    return sections


def find_heading_positions_multi(text: str,
                                  headings: List[Dict[str, str]]
                                  ) -> List[Tuple[int, int, str]]:
    hits = []
    for h in headings:
        for m in re.finditer(h["regex"], text, flags=re.IGNORECASE):
            hits.append((m.start(), m.end(), h["name"]))
    hits.sort(key=lambda x: x[0])
    return hits


def split_sections_multi(text: str,
                         headings: List[Dict[str, str]],
                         strip_patterns: List[str],
                         trim_anchors: List[str]
                         ) -> List[Tuple[str, str]]:
    hits = find_heading_positions_multi(text, headings)
    out: List[Tuple[str, str]] = []
    if not hits:
        return out
    for i, (_, end, name) in enumerate(hits):
        next_start = hits[i + 1][0] if i + 1 < len(hits) else len(text)
        body = text[end:next_start].strip()
        body = clean_section_text(body, strip_patterns)
        if name == "Diagnostic Criteria":
            body = trim_diagnostic_criteria(body, trim_anchors)
        out.append((name, body))
    return out


def write_sections_multi(sections: List[Tuple[str, str]], outdir: Path) -> None:
    for idx, (heading, body) in enumerate(sections, start=1):
        fname = f"{idx:02d}_{filename_slug(heading)}.txt"
        content = f"{heading}\n" + ("=" * len(heading)) + "\n\n" + body.strip() + "\n"
        _safe_write(outdir / fname, content)


def write_core_file_multi(sections: List[Tuple[str, str]],
                          core_headings: List[str], outdir: Path,
                          disorder_id: str, include_headings: bool = True) -> None:
    core_set = set(core_headings)
    parts = []
    for heading, body in sections:
        if heading not in core_set:
            continue
        body = body.strip()
        if not body:
            continue
        if include_headings:
            parts.append(f"{heading}\n{'=' * len(heading)}\n{body}")
        else:
            parts.append(body)
    core_text = "\n\n".join(parts).strip()
    fname = f"{disorder_id}_core_phenotype_only.txt"
    _safe_write(outdir / fname, core_text + "\n")


def write_json_multi(sections: List[Tuple[str, str]], outdir: Path,
                     disorder_id: str) -> None:
    fname = f"{disorder_id}_sections.json"
    path = outdir / fname
    if path.exists():
        path.unlink()
    payload = [{"heading": h, "body": b} for h, b in sections]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def filename_slug(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s


def _safe_write(path: Path, content: str) -> None:
    if path.exists():
        path.unlink()
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def write_sections(sections: "OrderedDict[str, str]", outdir: Path) -> None:
    for idx, (heading, body) in enumerate(sections.items(), start=1):
        fname = f"{idx:02d}_{filename_slug(heading)}.txt"
        content = f"{heading}\n" + ("=" * len(heading)) + "\n\n" + body.strip() + "\n"
        _safe_write(outdir / fname, content)


def write_core_file(sections: "OrderedDict[str, str]",
                     core_headings: List[str], outdir: Path,
                     disorder_id: str, include_headings: bool = True) -> None:
    parts = []
    for heading in core_headings:
        body = sections.get(heading, "").strip()
        if not body:
            continue
        if include_headings:
            parts.append(f"{heading}\n{'=' * len(heading)}\n{body}")
        else:
            parts.append(body)
    core_text = "\n\n".join(parts).strip()
    fname = f"{disorder_id}_core_phenotype_only.txt"
    _safe_write(outdir / fname, core_text + "\n")


def write_json(sections: "OrderedDict[str, str]", outdir: Path,
                disorder_id: str) -> None:
    fname = f"{disorder_id}_sections.json"
    path = outdir / fname
    if path.exists():
        path.unlink()
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(sections, f, indent=2, ensure_ascii=False)


def write_raw_stripped(text: str, outdir: Path, disorder_id: str) -> None:
    fname = f"{disorder_id}_raw_stripped_before_heading_split.txt"
    _safe_write(outdir / fname, text + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=str, required=True,
                     help="Path to disorder_config.json (e.g., asd.disorder.json)")
    ap.add_argument("--pdf", type=str, default=None,
                     help="Override pdf_input from config")
    ap.add_argument("--outdir", type=str, default=None,
                     help="Override outdir from config (use for parity-test runs)")
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    disorder_id = cfg["disorder"]["id"]
    s0 = cfg["stage0_dsm5_extraction"]

    pdf_path = Path(args.pdf or s0["pdf_input"])
    outdir = Path(args.outdir or s0["outdir"])
    outdir.mkdir(parents=True, exist_ok=True)

    headings = s0["headings_to_extract"]
    core_headings = s0.get(
        "core_phenotype_headings", ["Diagnostic Criteria", "Diagnostic Features"]
    )
    strip_patterns = s0.get("running_header_strip_patterns", [])
    trim_anchors = s0.get(
        "criteria_trim_anchors", [r"\bNote:\b", r"\bSpecify if:\b"]
    )
    text_norm_opts = s0.get("text_normalization", {})
    start_anchor = s0["chapter_start_anchor"]
    end_anchor = s0.get("chapter_end_anchor", "")
    start_keep = s0.get("chapter_start_anchor_keep", True)

    print(f"=== extract_dsm5: disorder={disorder_id} ===")
    print(f"  pdf:    {pdf_path}")
    print(f"  outdir: {outdir.resolve()}")
    print()

    raw = extract_pdf_text(pdf_path)

    text_replacements = s0.get("text_replacements", [])
    if text_replacements:
        print(f"Applying {len(text_replacements)} text-replacement rule(s):")
        raw = apply_text_replacements(raw, text_replacements)

    text = normalize_unicode_and_layout(raw, text_norm_opts)
    text = strip_chapter_bounds(text, start_anchor, end_anchor, start_keep)

    multi_block = s0.get("multi_block_headings", False)

    if multi_block:
        sections_list = split_sections_multi(text, headings, strip_patterns, trim_anchors)
        if not sections_list:
            raise RuntimeError(
                f"No DSM {disorder_id} headings detected. Check PDF extraction quality."
            )
        write_sections_multi(sections_list, outdir)
        write_core_file_multi(sections_list, core_headings, outdir, disorder_id)
        write_json_multi(sections_list, outdir, disorder_id)
        write_raw_stripped(text, outdir, disorder_id)

        from collections import Counter as _Counter
        name_counts = _Counter(name for name, _ in sections_list)
        print(f"Detected {len(sections_list)} section block(s) "
              f"across {name_counts.get('Diagnostic Criteria', 0)} Diagnostic Criteria blocks:")
        for name, n in name_counts.items():
            print(f"  - {name}  (x{n})")
        print()
        print("Core phenotype headings (multi-block):")
        for h in core_headings:
            n = name_counts.get(h, 0)
            marker = f"found x{n}" if n else "NOT FOUND"
            print(f"  - {h}  ({marker})")
        if name_counts.get("Diagnostic Criteria", 0) < 2:
            print()
            print("  [!] WARNING: multi_block_headings is on but fewer than 2 "
                  "Diagnostic Criteria blocks were found. Verify the chapter anchors "
                  "and heading regexes against the rendered (possibly OCR-garbled) text.")
        return 0

    sections = split_sections(text, headings, strip_patterns, trim_anchors)
    if not sections:
        raise RuntimeError(
            f"No DSM {disorder_id} headings detected. Check PDF extraction quality."
        )

    write_sections(sections, outdir)
    write_core_file(sections, core_headings, outdir, disorder_id)
    write_json(sections, outdir, disorder_id)
    write_raw_stripped(text, outdir, disorder_id)

    print(f"Detected {len(sections)} section(s):")
    for h in sections:
        print(f"  - {h}  ({len(sections[h]):,} chars)")
    print()
    print("Core phenotype headings:")
    for h in core_headings:
        marker = "found" if h in sections else "NOT FOUND"
        print(f"  - {h}  ({marker})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
