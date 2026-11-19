#!/usr/bin/env python3
import argparse, csv, os, sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disorder", required=True)
    ap.add_argument("--target_units", default=None,
                    help="defaults to target_units_{D}/03_target_criterion_units.tsv")
    ap.add_argument("--out", default=None,
                    help="defaults to target_units_{D}/04_noncriterion_hpo_ids.txt")
    a = ap.parse_args()
    root = Path(os.environ.get("FACET_ROOT", "."))
    src = Path(a.target_units or f"target_units_{a.disorder}/03_target_criterion_units.tsv")
    dst = Path(a.out or f"target_units_{a.disorder}/04_noncriterion_hpo_ids.txt")
    p = root / src
    if not p.exists():
        sys.exit(f"{a.disorder}: {p} not found. Run decompose_targets_to_criterion_units.py first.")
    with p.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))

    drop = [r for r in rows if (r.get("item_id") or "none").strip() == "none"
            or str(r.get("attributable", "")).strip().lower() not in ("true", "1")]
    keep = [r for r in rows if r not in drop]
    out = root / dst
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(r["hpo_id"] for r in drop) + ("\n" if drop else ""), encoding="utf-8")

    print(f"{a.disorder}: {len(rows)} targets, {len(keep)} carry a scored criterion, "
          f"{len(drop)} do not")
    for r in drop:
        print(f"    excluded  {r['hpo_id']:12s} {r.get('hpo_label','')[:52]:52s} "
              f"conf {r.get('confidence','')}")
    print(f"  wrote {out}")
    print("  use as: asd_face_validity_scoring.py --exclude_hpo_ids_file " + str(dst))
    print("  REPORT BOTH ARMS. Excluding non-criterion anchors is a sensitivity analysis, not a "
          "correction, until the project rules on it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
