#!/usr/bin/env python3
import argparse, csv, json, os, sys
from pathlib import Path

IC_MIN = 0.85


def load_rows(p):
    with open(p, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def truthy(v):
    return str(v).strip().lower() in ("true", "1", "yes")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--taxonomy", required=True, help="path to a run's 03_taxonomy.tsv")
    ap.add_argument("--spec", required=True, help="path to the criterion spec the run used")
    ap.add_argument("--include_provisional", action="store_true",
                    help="count provisional units in the denominator (the opt-in arm)")
    ap.add_argument("--both", action="store_true", help="print the opt-out and opt-in arms together")
    ap.add_argument("--direction_aware", action="store_true",
                    help="require admissible_directionaware rather than admissible")
    ap.add_argument("--ic_column", default="seco_ic")
    a = ap.parse_args()
    root = Path(os.environ.get("FACET_ROOT", "."))
    spec = json.loads((root / a.spec).read_text(encoding="utf-8"))
    rows = load_rows(root / a.taxonomy)

    all_units = [i["item_id"] for i in spec["items"]]
    prov = list(spec.get("provisional_units") or [])
    field = "admissible_directionaware" if a.direction_aware else "admissible"
    has_ic = bool(rows) and a.ic_column in rows[0]

    hit, deep, per = set(), set(), {}
    for r in rows:
        if not truthy(r.get(field)):
            continue
        u = (r.get("item_id") or "").strip()
        if u not in all_units:
            continue
        hit.add(u)
        per[u] = per.get(u, 0) + 1
        if has_ic:
            try:
                if float(r[a.ic_column]) >= IC_MIN:
                    deep.add(u)
            except (TypeError, ValueError):
                pass

    def report(include):
        units = all_units if include else [u for u in all_units if u not in prov]
        den = len(units)
        b = sorted(u for u in hit if u in units)
        d = sorted(u for u in deep if u in units)
        label = "opt-in, provisional included" if include else "primary, provisional excluded"
        print(f"\n  {label}")
        print(f"    denominator        {den}   units {', '.join(units)}")
        print(f"    breadth            {len(b)}/{den} ({len(b)/den:.0%})   met: "
              f"{', '.join(b) if b else 'none'}")
        if has_ic:
            print(f"    depth (IC>={IC_MIN})   {len(d)}/{den} ({len(d)/den:.0%})   met: "
                  f"{', '.join(d) if d else 'none'}")
        else:
            print(f"    depth              UNAVAILABLE, no `{a.ic_column}` column in this table. "
                  f"Depth is NOT equal to breadth; it is simply not computed here.")
        return {"denominator": den, "breadth": len(b), "units_met": b,
                "depth": (len(d) if has_ic else None)}

    print(f"{spec['disorder']}  grain {spec['scored_grain']}  rows {len(rows)}  "
          f"admission field `{field}`")
    print(f"  admissions per unit: " + ", ".join(f"{u}={per.get(u,0)}" for u in all_units))
    if prov:
        print(f"  PROVISIONAL units: {', '.join(prov)}. These were judged in the run on the same terms "
              f"as every other unit.")
    out = {}
    if a.both or not prov:
        out["primary"] = report(False)
        if prov:
            out["opt_in"] = report(True)
    else:
        out["selected"] = report(a.include_provisional)
    if prov and a.both:
        db = out["opt_in"]["breadth"] - out["primary"]["breadth"]
        print(f"\n  effect of the switch: breadth {out['primary']['breadth']}/"
              f"{out['primary']['denominator']} versus {out['opt_in']['breadth']}/"
              f"{out['opt_in']['denominator']}. The provisional unit "
              f"{'was met' if db else 'was NOT met'}, so including it "
              f"{'raises' if db else 'lowers'} the fraction from "
              f"{out['primary']['breadth']/out['primary']['denominator']:.0%} to "
              f"{out['opt_in']['breadth']/out['opt_in']['denominator']:.0%}.")
    print("\n  Denominators differ across disorders and units are not equally hard to satisfy. "
          "Report the fraction beside the raw count, and do not rank disorders on raw breadth.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
