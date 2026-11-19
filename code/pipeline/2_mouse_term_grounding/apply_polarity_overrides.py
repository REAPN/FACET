#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pandas as pd


OVERRIDES = [
    {
        "entity_id": "HP:0001344",
        "field": "functional_effect",
        "new_value": "less",
        "rationale": (
            "Absent speech = literally absent (observed=absent). "
            "Biological/functional interpretation is 'less' speech production. "
            "Original LLM annotation deferred to abnormal_unspecified, which "
            "downgrades comparison weight; the absent/less mapping is "
            "biologically clear and consistent with other communication-domain "
            "terms (HP:0002465 Poor speech is coded as less)."
        ),
    },
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", type=str, default="polarity_schema_v1")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    annot_path = outdir / "01_term_annotations.tsv"
    if not annot_path.exists():
        print(f"FAIL: {annot_path} not found. Run annotate_polarity_schema.py first.")
        return 1

    backup = outdir / "01_term_annotations.tsv.pre_override.bak"
    if not backup.exists():
        shutil.copy(annot_path, backup)
        print(f"backup -> {backup}")

    df = pd.read_csv(annot_path, sep="\t")

    audit_rows = []
    for ov in OVERRIDES:
        eid = ov["entity_id"]
        mask = df["entity_id"] == eid
        n = int(mask.sum())
        if n == 0:
            print(f"WARN: {eid} not in annotation file; skipping override.")
            continue
        old = df.loc[mask, ov["field"]].iloc[0]
        df.loc[mask, ov["field"]] = ov["new_value"]
        audit_rows.append({
            "entity_id": eid,
            "field": ov["field"],
            "old_value": old,
            "new_value": ov["new_value"],
            "rationale": ov["rationale"],
        })
        print(f"  {eid}: {ov['field']}  {old}  ->  {ov['new_value']}")

    df.to_csv(annot_path, sep="\t", index=False)
    pd.DataFrame(audit_rows).to_csv(outdir / "03_polarity_overrides.tsv",
                                    sep="\t", index=False)
    print(f"  wrote {annot_path}")
    print(f"  wrote {outdir / '03_polarity_overrides.tsv'}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
