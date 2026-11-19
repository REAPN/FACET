#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from collections import OrderedDict
from pathlib import Path

from pypdf import PdfReader


HEADINGS = OrderedDict([
    ("Diagnostic Criteria", r"Diagnostic Criteria(?:\s+F3[23](?:\.[0-9x]+)?)?"),
    ("Coding and Recording Procedures",
     r"Coding and Recording Procedures|Recording Procedures"),
    ("Specifiers", r"Specifiers"),
    ("Diagnostic Features", r"Diagnostic Features"),
    ("Associated Features Supporting Diagnosis",
     r"Associated Features Supporting Diagnosis|Associated Features"),
    ("Prevalence", r"Prevalence"),
    ("Development and Course", r"Development and Course"),
    ("Risk and Prognostic Factors", r"Risk and Prognostic Factors"),
    ("Culture-Related Diagnostic Issues",
     r"Culture-Related Diagnostic Issues"),
    ("Sex- and Gender-Related Diagnostic Issues",
     r"Sex-?\s*and Gender-Related Diagnostic Issues|Gender-Related Diagnostic Issues"),
    ("Association With Suicidal Thoughts or Behavior",
     r"Association With Suicidal Thoughts or Behavior|Suicide Risk"),
    ("Functional Consequences of Major Depressive Disorder",
     r"Functional Consequences of Major Depressive Disorder"),
    ("Differential Diagnosis", r"Differential Diagnosis"),
    ("Comorbidity", r"Comorbidity"),
])

DEFAULT_CORE_HEADINGS = [
    "Diagnostic Criteria",
    "Diagnostic Features",
]


def extract_pdf_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    pages = []
    for page in reader.pages:
        txt = page.extract_text() or ""
        pages.append(txt)
    return "\n\n".join(pages)


def normalize_unicode_and_layout(text: str) -> str:
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
        "￾": "",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)

    text = re.sub(r"([A-Za-z]{2,})-\s*\n\s*(\w)", r"\1\2", text)

    text = re.sub(
        r"(?m)^([A-Z]|\d+)[ \t]*\n[ \t]*\.[ \t]*\n[ \t]*",
        r"\1. ",
        text,
    )
    text = re.sub(r"\(\s*\nNote:\s*", "(Note: ", text)

    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)

    text = re.sub(r"\n{3,}", "\n\n", text)

    text = re.sub(r"[ \t]{2,}", " ", text)

    return text.strip()


def strip_before_mdd_start(text: str) -> str:
    m = re.search(r"(?m)^\s*Major Depressive Disorder\s*$", text, flags=re.IGNORECASE)
    if m:
        return text[m.end():].strip()
    m = re.search(HEADINGS["Diagnostic Criteria"], text, flags=re.IGNORECASE)
    return text[m.start():].strip() if m else text.strip()


def strip_pdd_spillover(text: str) -> str:
    m = re.search(r"(?m)^\s*Persistent Depressive Disorder\s*$",
                  text, flags=re.IGNORECASE)
    if m:
        return text[:m.start()].strip()
    m = re.search(r"Persistent Depressive Disorder", text, flags=re.IGNORECASE)
    return text[:m.start()].strip() if m else text.strip()


def find_heading_positions(text):
    hits = []
    for heading_name, pattern in HEADINGS.items():
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            hits.append((m.start(), m.end(), heading_name))
    hits.sort(key=lambda x: x[0])
    return hits


def clean_section_text(text: str) -> str:
    text = re.sub(r"(?mi)^\s*Major Depressive Disorder\s*$", "", text)
    text = re.sub(r"(?mi)^\s*Depressive Disorders\s*$", "", text)
    text = re.sub(r"(?mi)^\s*DSM-5(?:-TR)?\s*$", "", text)
    text = re.sub(r"(?mi)^\s*\d+\s*$", "", text)

    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def trim_diagnostic_criteria(text: str) -> str:
    cut_points = []
    m = re.search(r"\bSpecify if:\b", text, flags=re.IGNORECASE)
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


def split_sections(text):
    hits = find_heading_positions(text)
    sections = OrderedDict()

    if not hits:
        return sections

    for i, (_, end, heading_name) in enumerate(hits):
        next_start = hits[i + 1][0] if i + 1 < len(hits) else len(text)
        section_body = text[end:next_start].strip()
        section_body = clean_section_text(section_body)

        if heading_name == "Diagnostic Criteria":
            section_body = trim_diagnostic_criteria(section_body)

        sections[heading_name] = section_body

    return sections


def filename_slug(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def write_sections(sections, outdir: Path) -> None:
    for idx, (heading, body) in enumerate(sections.items(), start=1):
        fname = f"{idx:02d}_{filename_slug(heading)}.txt"
        with open(outdir / fname, "w", encoding="utf-8") as f:
            f.write(f"{heading}\n")
            f.write("=" * len(heading) + "\n\n")
            f.write(body.strip() + "\n")


def write_core_file(sections, core_headings, outdir: Path,
                    include_headings: bool = True) -> None:
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

    with open(outdir / "MDD_core_phenotype_only.txt", "w", encoding="utf-8") as f:
        f.write(core_text + "\n")


def write_json(sections, outdir: Path) -> None:
    with open(outdir / "MDD_sections.json", "w", encoding="utf-8") as f:
        json.dump(sections, f, indent=2, ensure_ascii=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_path", type=str, help="Path to DSM5_MDD.pdf")
    parser.add_argument("--outdir", type=str, default="DSM5_MDD_preprocessed",
                        help="Output folder")
    parser.add_argument("--include-development-course", action="store_true",
                        help="Also include 'Development and Course' in MDD_core_phenotype_only.txt")
    parser.add_argument("--include-associated-features", action="store_true",
                        help="Also include 'Associated Features Supporting Diagnosis' in MDD_core_phenotype_only.txt")
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    raw = extract_pdf_text(pdf_path)
    text = normalize_unicode_and_layout(raw)
    text = strip_before_mdd_start(text)
    text = strip_pdd_spillover(text)

    sections = split_sections(text)
    if not sections:
        raise RuntimeError("No DSM MDD headings were detected. Check PDF extraction quality.")

    write_sections(sections, outdir)
    write_json(sections, outdir)

    core_headings = list(DEFAULT_CORE_HEADINGS)
    if args.include_development_course:
        core_headings.append("Development and Course")
    if args.include_associated_features:
        core_headings.append("Associated Features Supporting Diagnosis")

    write_core_file(sections, core_headings, outdir)

    with open(outdir / "MDD_raw_stripped_before_heading_split.txt", "w", encoding="utf-8") as f:
        f.write(text + "\n")

    print(f"Done. Wrote outputs to: {outdir.resolve()}")
    print(f"Detected {len(sections)} section(s):")
    for h in sections:
        print(f"  - {h}  ({len(sections[h]):,} chars)")
    print("\nCore phenotype headings used:")
    for h in core_headings:
        print(f"  - {h}")


if __name__ == "__main__":
    main()
