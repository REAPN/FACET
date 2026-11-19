#!/usr/bin/env python3
import argparse, csv, hashlib, json, os, sys
from pathlib import Path

TIER_LABEL = {1: "strict_face_validity", 2: "broad_behavioral_support",
              3: "mechanistic_neural_support", 4: "generic_neurological_background",
              5: "off_target_or_uninformative"}
MODALITY_TIER = {"behavioral": 2, "anatomical": 3, "physiological": 3,
                 "developmental": 4, "other": 4}
OVERRIDE_COLS = ["relevance_tier", "tier_label"]
ADDED_COLS = ["criterion_unit", "criterion_component", "criterion_second_unit",
              "criterion_admissible", "criterion_admissible_directionaware",
              "criterion_qualifier_absent", "criterion_needs_manual_review",
              "criterion_judged", "criterion_spec_version", "criterion_prompt_sha"]


def read_tsv(p):
    with open(p, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def truthy(v):
    return str(v).strip().lower() in ("true", "1", "yes")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disorder", required=True)
    ap.add_argument("--run", required=True, help="path to the run's 03_taxonomy.tsv")
    ap.add_argument("--base_taxonomy", required=True,
                    help="THIS disorder's existing taxonomy, used only for disorder-invariant columns")
    ap.add_argument("--outdir", required=True)
    a = ap.parse_args()
    root = Path(os.environ.get("FACET_ROOT", "."))

    judged_rows = read_tsv(root / a.run)
    judged = {r["mp_id"]: r for r in judged_rows}
    if len(judged) != len(judged_rows):
        sys.exit(f"{a.disorder}: run has {len(judged_rows)} rows over {len(judged)} unique mp_id. "
                 f"A dict keyed on mp_id would silently keep the last and drop the rest.")
    base = read_tsv(root / a.base_taxonomy)
    base_ids = {r["mp_id"] for r in base}

    stray = [m for m in judged if m not in base_ids]
    stray_admitted = [m for m in stray if truthy(judged[m].get("admissible"))]
    if stray:
        print(f"  {len(stray)} judged terms are not annotated to any genotype in the pairing table "
              f"and are dropped, of which {len(stray_admitted)} were admissible.")
        if stray_admitted:
            print("    admissible but unpairable: "
                  + ", ".join(judged[m].get("mp_label", m) for m in stray_admitted[:12]))
    for m in stray:
        judged.pop(m)

    specs = {r.get("spec_version", "") for r in judged.values()}
    shas = {(r.get("prompt_sha", "") or "")[:16] for r in judged.values()}
    if len(specs) != 1 or len(shas) != 1:
        sys.exit(f"{a.disorder}: run is not internally consistent, spec_versions {specs}, shas {shas}")

    rows, counts = [], {t: 0 for t in TIER_LABEL}
    for b in base:
        m = b["mp_id"]
        j = judged.get(m)
        if j is None:
            tier, unit, comp, second = 5, "", "", ""
            da = qa = nmr = ""
            sv = sha = ""
        elif truthy(j.get("admissible_directionaware")):
            tier = 1
            unit = (j.get("item_id") or "").strip()
            comp = (j.get("component") or "").strip()
            second = (j.get("second_item_id") or "").strip()
            da, qa = j.get("admissible_directionaware", ""), j.get("qualifier_absent", "")
            nmr, sv, sha = j.get("needs_manual_review", ""), j.get("spec_version", ""), \
                (j.get("prompt_sha", "") or "")[:16]
        else:
            mod = (j.get("modality") or "").strip().lower()
            if mod not in MODALITY_TIER:
                print(f"  WARNING: unmapped modality {mod!r} on {m}, quarantined to tier 5 rather "
                      f"than admitted to the candidate universe")
            tier = MODALITY_TIER.get(mod, 5)
            unit = comp = second = ""
            da, qa = "", j.get("qualifier_absent", "")
            nmr, sv, sha = j.get("needs_manual_review", ""), j.get("spec_version", ""), \
                (j.get("prompt_sha", "") or "")[:16]
        counts[tier] += 1
        row = dict(b)
        row["relevance_tier"] = tier
        row["tier_label"] = TIER_LABEL[tier]
        row.update({"criterion_unit": unit, "criterion_component": comp,
                    "criterion_second_unit": second,
                    "criterion_admissible": "true" if (j is not None and truthy(j.get("admissible")))
                                            else ("false" if j is not None else ""),
                    "criterion_admissible_directionaware": da,
                    "criterion_qualifier_absent": qa, "criterion_needs_manual_review": nmr,
                    "criterion_judged": "true" if j is not None else "false",
                    "criterion_spec_version": sv, "criterion_prompt_sha": sha})
        rows.append(row)

    out = root / a.outdir
    out.mkdir(parents=True, exist_ok=True)
    p = out / "03_mp_term_taxonomy.tsv"
    base_cols = list(base[0].keys())
    out_cols = base_cols + [c for c in ADDED_COLS if c not in base_cols]
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=out_cols, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    gate134 = counts[1] + counts[3] + counts[4]
    gate1234 = gate134 + counts[2]
    cfg = {"disorder": a.disorder, "built": "build_stage2a_taxonomy.py",
           "source_run": a.run, "base_taxonomy_used_for_invariant_columns_only": a.base_taxonomy,
           "spec_version": specs.pop(), "prompt_sha16": shas.pop(),
           "rows": len(rows), "judged": len(judged),
           "tier_counts": {str(k): v for k, v in counts.items()},
           "candidate_universe_default_gate_1_3_4": gate134,
           "candidate_universe_with_tier2": gate1234,
           "tier_rule": "1 admissible; 2 refused behavioral; 3 refused anatomical or physiological; "
                        "4 refused developmental or other; 5 not in this disorder's scope",
           "provenance_rule": "every judgment column derives from this disorder's own run only",
           "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
    (out / "99_taxonomy_build_config.json").write_text(json.dumps(cfg, indent=1), encoding="utf-8")

    print(f"{a.disorder}: wrote {p}")
    print(f"  spec {cfg['spec_version']}  prompt {cfg['prompt_sha16']}  sha256 {cfg['sha256'][:16]}")
    for t in sorted(TIER_LABEL):
        print(f"    tier {t}  {TIER_LABEL[t]:32s} {counts[t]:6d}")
    print(f"  candidate universe, isin([1,3,4])                 : {gate134}")
    print(f"  candidate universe, isin([1,2,3,4])               : {gate1234}   <== all four configs "
          f"set include_tier2_mouse true, so THIS is the operative number")
    return 0


if __name__ == "__main__":
    sys.exit(main())
