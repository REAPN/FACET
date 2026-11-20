#!/usr/bin/env python3
import argparse, json, os, re, sys
from pathlib import Path

LETTER_RE = re.compile(r"^([A-F])\s*\.\s+(.*)$")
NUMBER_RE = re.compile(r"^\s*(\d)\s*\.\s+(.*)$")
TAIL_RE = re.compile(r"^\s*(Specify if|Specify whether|Note:|Coding note|The following course)", re.I)


def _norm(s):
    return re.sub(r"\s+", " ", s).strip()


def load_spec(spec_path):
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    for req in ("disorder", "criteria_txt", "items", "scored_grain"):
        if req not in spec:
            sys.exit(f"spec {spec_path} is missing required key {req}")
    return spec


def _fence(raw, section):
    if not section:
        return raw
    start = raw.find(section["start"])
    if start < 0:
        sys.exit(f"section start not found in criteria file: {section['start']!r}")
    rest = raw[start + len(section["start"]):]
    if section.get("end"):
        end = rest.find(section["end"])
        if end >= 0:
            rest = rest[:end]
    return rest


def extract(spec, root="."):
    path = Path(root) / spec["criteria_txt"]
    if not path.exists():
        sys.exit(f"criteria file not found: {path}")
    raw = _fence(path.read_text(encoding="utf-8", errors="replace"), spec.get("section"))
    lines = [ln.rstrip() for ln in raw.splitlines()]

    blocks, order = {}, []
    cur_letter, cur_num = None, None
    stem_buf, num_buf = [], {}
    for ln in lines:
        if TAIL_RE.match(ln):
            cur_letter, cur_num = None, None
            continue
        m_letter = LETTER_RE.match(ln)
        if m_letter:
            cur_letter = m_letter.group(1)
            cur_num = None
            stem_buf = [m_letter.group(2)]
            num_buf = {}
            blocks[cur_letter] = {"stem": stem_buf, "nums": num_buf}
            order.append(cur_letter)
            continue
        if cur_letter is None:
            continue
        m_num = NUMBER_RE.match(ln)
        if m_num:
            cur_num = m_num.group(1)
            num_buf[cur_num] = [m_num.group(2)]
            continue
        (num_buf[cur_num] if cur_num else stem_buf).append(ln.strip())

    items, stems, missing = {}, {}, []
    for it in spec["items"]:
        letter, num = it["letter"], it.get("number")
        blk = blocks.get(letter)
        if not blk:
            missing.append(f"{it['item_id']} (criterion {letter} not found)")
            continue
        stems[letter] = _norm(" ".join(blk["stem"]))
        if it["extract"] == "lettered_item":
            if num not in blk["nums"]:
                missing.append(f"{it['item_id']} (item {num} not found under criterion {letter})")
                continue
            items[it["item_id"]] = _norm(" ".join(blk["nums"][num]))
        elif it["extract"] == "lettered_criterion":
            parts = [_norm(" ".join(blk["stem"]))]
            for k in sorted(blk["nums"]):
                parts.append(f"{k}. " + _norm(" ".join(blk["nums"][k])))
            items[it["item_id"]] = _norm(" ".join(parts))
        else:
            sys.exit(f"unknown extract mode {it['extract']!r} for {it['item_id']}")
        if not items.get(it["item_id"]):
            missing.append(f"{it['item_id']} (extracted empty)")

    if missing:
        sys.exit("EXTRACTION FAILED, nothing will run until this is fixed:\n  " + "\n  ".join(missing))
    return items, stems, raw


def item_directions(spec):
    return {it["item_id"]: it.get("direction", "either") for it in spec["items"]}


def component_enum(spec):
    out = []
    for it in spec["items"]:
        for c in it.get("components", []):
            if c not in out:
                out.append(c)
    return out + ["not_applicable", "none"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True, help="path to criterion_specs/<DISORDER>.json")
    a = ap.parse_args()
    root = os.environ.get("FACET_ROOT", ".")
    spec = load_spec(a.spec)
    items, stems, _ = extract(spec, root)

    print(f"DISORDER      {spec['disorder']}  ({spec.get('disorder_long','')})")
    print(f"SOURCE        {spec['criteria_txt']}")
    if spec.get("section"):
        print(f"SECTION FENCE {spec['section']['start']!r} to {spec['section'].get('end')!r}")
    print(f"SCORED GRAIN  {spec['scored_grain']}  ({len(spec['items'])} scored units)")
    print(f"COUNTING RULE {spec['counting_rule']}")
    print()
    for it in spec["items"]:
        iid = it["item_id"]
        print(f"--- {iid}  direction={it.get('direction')}"
              + ("  FLOOR" if it.get("floor") else ""))
        print(f"    stem     : {stems.get(it['letter'],'')[:300]}")
        print(f"    text     : {items[iid]}")
        comps = it.get("components", [])
        if comps:
            print(f"    components ({len(comps)}, illustrative, NOT scored): {', '.join(comps)}")
        print()
    excl = spec.get("excluded_criteria", {})
    if excl:
        print("NOT SCORED:")
        for k, v in excl.items():
            print(f"    {k}. {v}")
    print(f"\ncomponent enum for the output schema: {component_enum(spec)}")


if __name__ == "__main__":
    main()
