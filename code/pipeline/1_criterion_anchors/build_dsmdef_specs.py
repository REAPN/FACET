#!/usr/bin/env python3
import argparse, hashlib, json, os, re, sys
from pathlib import Path

CACHE = "_dsm5tr_cache/dsm5tr_full.txt"
TRANSLATE = {"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"', "\u00ad": "",
             "\u2014": " ", "\u2013": "-", "\u2212": "-", "\u2010": "-", "\u00a0": " ",
             "\ufb01": "fi", "\ufb02": "fl"}


def _norm(s):
    for k, v in TRANSLATE.items():
        s = s.replace(k, v)
    return re.sub(r"\s+", " ", s).strip()

WIRING = {
    "SCZ": {"A1": "A1", "A2": "A2", "A3": "A3", "A4": "A4", "A5": "A5"},
    "NCD": {"A": "A"},
    "ID":  {"B": "B"},
    "ASD": {"A1": "A1", "B1": "B1"},
}
FROZEN = {
    "SCZ": "2e0ef3fd3cb3d7c4",
    "NCD": "57580272d8a03d7d",
    "ID":  "b7cfb366113f8d11",
    "ASD": "80b0be655b9b7886",
}
PROTECTED = ("disorder", "disorder_long", "criteria_txt", "section", "counting_rule", "scored_grain",
             "scored_grain_note", "excluded_criteria", "rules", "prompt_version")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disorders", default="SCZ,NCD,ID,ASD",
                    help="comma separated subset to build")
    ap.add_argument("--spec_version", default="2026-07-28_dsmdef_pilot")
    ap.add_argument("--no_frozen_check", action="store_true",
                    help="the frozen shas are the PILOT shas; pass this when building production specs")
    a = ap.parse_args()
    want = [x.strip() for x in a.disorders.split(",") if x.strip()]
    root = Path(os.environ.get("FACET_ROOT", "."))
    defs = json.loads((root / "_dsm_definitions.json").read_text(encoding="utf-8"))
    cache_sha = defs["cache_sha256"]
    print(f"definitions from {defs['pdf']}, cache sha256 {cache_sha[:32]}\n")

    for D, wiring in WIRING.items():
        if D not in want:
            continue
        blk = defs["disorders"][D]
        src = json.loads((root / "criterion_specs" / f"{D}.json").read_text(encoding="utf-8"))
        out = json.loads(json.dumps(src))

        kind = "definitional" if blk["kind"] == "definitional" else blk["kind"]
        out["spec_version"] = a.spec_version
        kindword = ("PILOT VARIANT, not production." if "pilot" in a.spec_version
                    else "PRODUCTION VARIANT.")
        out["variant_note"] = (
            f"{kindword} Identical to {D}.json except that scored units carry "
            f"DSM-5-TR's own definitional text, extracted from DSM 5 TR-APA 2022.pdf with page citations "
            f"by extract_dsm_definitions.py. Source: {blk['source']} ({kind}). "
            f"Contiguous verbatim: {blk['contiguous']}.")
        if blk.get("control_note"):
            out["control_note"] = blk["control_note"]
        if blk.get("reconstruction_note"):
            out["reconstruction_note"] = blk["reconstruction_note"]

        hit = 0
        for it in out["items"]:
            key = wiring.get(it["item_id"])
            if not key:
                continue
            ent = blk["by_item"][key]
            it["dsm_definition"] = ent["text"]
            it["dsm_definition_citation"] = ent["citation"]
            it["dsm_definition_source"] = blk["source"]
            hit += 1
        if hit != len(wiring):
            sys.exit(f"{D}: wired {hit} of {len(wiring)} units, spec item ids do not match WIRING")

        for k in PROTECTED:
            if src.get(k) != out.get(k):
                sys.exit(f"{D}: protected key {k} changed, refusing to write")
        for si, oi in zip(src["items"], out["items"]):
            for k in si:
                if si[k] != oi[k]:
                    sys.exit(f"{D}: item {si['item_id']} key {k} changed, refusing to write")

        corpus = _norm((root / CACHE).read_text(encoding="utf-8", errors="replace")).lower()
        for it in out["items"]:
            dd = it.get("dsm_definition")
            if not dd:
                continue
            for chunk in [c.strip() for c in dd.split("\n") if c.strip()]:
                if not chunk.rstrip().endswith((".", "!", "?", ")")):
                    sys.exit(f"{D}: unit {it['item_id']} definition ends mid-sentence: ...{chunk[-60:]!r}")
                if blk["contiguous"]:
                    if chunk.lower() not in corpus:
                        sys.exit(f"{D}: unit {it['item_id']} definition is NOT a verbatim PDF substring")
                else:
                    miss = [t for t in re.findall(r"[a-z]{4,}", chunk.lower()) if t not in corpus]
                    if miss:
                        sys.exit(f"{D}: unit {it['item_id']} reconstructed tokens absent from PDF: {miss[:5]}")

        p = root / "criterion_specs" / f"{D}_dsmdef.json"
        p.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
        spec_sha = hashlib.sha256(p.read_bytes()).hexdigest()[:16]

        sys.path.insert(0, str(root))
        from criterion_spec import load_spec, extract
        from criterion_prompt import build_developer_prompt
        sp = load_spec(str(p))
        criteria, stems, _ = extract(sp, str(root))
        prompt = build_developer_prompt(sp, criteria, stems, mode="joint")
        prom_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
        chars = sum(len(it.get("dsm_definition") or "") for it in out["items"])
        print(f"  {D:4s} units_with_definition {hit}  definition_chars {chars:5d}  "
              f"spec_sha {spec_sha}  prompt_sha {prom_sha}"
              + ("" if (a.no_frozen_check or FROZEN.get(D) in (None, prom_sha))
                 else f"  *** DRIFT, frozen {FROZEN[D]}"))
    print("\nspecs written. Record the prompt_sha values in the pre-registration and the run sheet.")


if __name__ == "__main__":
    main()
