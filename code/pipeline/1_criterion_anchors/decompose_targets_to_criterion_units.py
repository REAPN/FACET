#!/usr/bin/env python3
import argparse, csv, hashlib, json, os, sys, time
from pathlib import Path

SCHEMA = {
    "name": "target_unit_attribution",
    "schema": {
        "type": "object", "additionalProperties": False,
        "properties": {
            "item_id": {"type": "string"},
            "second_item_id": {"type": "string"},
            "attributable": {"type": "boolean"},
            "confidence": {"type": "number"},
            "needs_manual_review": {"type": "boolean"},
            "reason": {"type": "string"},
        },
        "required": ["item_id", "second_item_id", "attributable", "confidence",
                     "needs_manual_review", "reason"],
    },
    "strict": True,
}


def build_prompt(spec, criteria, stems):
    from criterion_prompt import _unit_block
    blocks = "\n\n".join(_unit_block(spec, it, criteria, stems) for it in spec["items"])
    units = [i["item_id"] for i in spec["items"]]
    return f"""You attribute a HUMAN phenotype to the DSM-5-TR diagnostic unit it instantiates, for
{spec.get('disorder_long', spec['disorder'])}.

This is the mirror of the mouse-side task. There the question was which unit an MP term instantiates.
Here the phenotype is a human one, resolved from the DSM text itself into a Human Phenotype Ontology
term, so attribution should usually be possible and clean. The units below are quoted verbatim from
DSM-5-TR and are the same strings used to judge the mouse vocabulary.

{blocks}

HOW TO DECIDE
  - Choose the ONE unit the phenotype most directly instantiates and put it in `item_id`.
  - If it genuinely instantiates a second unit as well, name that in `second_item_id`, else "none".
  - A phenotype that belongs to this disorder but to NO scored unit, for example an associated
    feature, an onset statement, a severity specifier or an exclusion, is NOT attributable: set
    item_id to "none" and attributable to false. Do not force it into the nearest unit.
  - Judge against the unit's own verbatim text, not against the disorder in general. A phenotype
    about the disorder as a whole, with no unit that names it, is "none".
  - Set needs_manual_review when two units are genuinely close and the choice would change a count.

Valid `item_id` values: {", ".join(units)}, or "none".
Return JSON only."""


def _is_permanent(e):
    s = f"{type(e).__name__} {e}".lower()
    for marker in ("insufficient_quota", "exceeded your current quota", "billing",
                   "invalid_api_key", "authenticationerror", "permissiondenied",
                   "badrequesterror", "model_not_found"):
        if marker in s:
            return marker
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disorder", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--targets", required=True, help="stage 1 07_final_resolved_hpo_terms.tsv")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--model", default="gpt-5.4")
    ap.add_argument("--catalog", default="mappability_catalog/catalog_by_phenotype.tsv")
    ap.add_argument("--dry_run", action="store_true", help="render and hash the prompt, make no call")
    a = ap.parse_args()
    root = Path(os.environ.get("FACET_ROOT", "."))
    sys.path.insert(0, str(root))
    from criterion_spec import load_spec, extract

    spec = load_spec(str(root / a.spec))
    criteria, stems, _ = extract(spec, str(root))
    dev = build_prompt(spec, criteria, stems)
    sha = hashlib.sha256(dev.encode("utf-8")).hexdigest()
    units = [i["item_id"] for i in spec["items"]]

    with (root / a.targets).open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    print(f"{a.disorder}: {len(rows)} targets, {len(units)} units {units}, prompt sha {sha[:16]}")
    if a.dry_run:
        print(f"  dry run, no calls. prompt is {len(dev)} chars.")
        return 0

    from openai import OpenAI
    client = OpenAI()
    out = root / a.outdir
    out.mkdir(parents=True, exist_ok=True)
    raw = out / "02_target_units_raw.jsonl"
    done = {}
    if raw.exists():
        for line in raw.open(encoding="utf-8"):
            try:
                r = json.loads(line)
                if r.get("prompt_sha") == sha:
                    done[r["hpo_id"]] = r
            except Exception:
                pass
        print(f"  resuming, {len(done)} rows already carry this prompt sha")

    results = []
    with raw.open("a", encoding="utf-8") as fh:
        for i, r in enumerate(rows, 1):
            if r["hpo_id"] in done:
                results.append(done[r["hpo_id"]]); continue
            user = (f"HPO term: {r.get('hpo_label','')}\n"
                    f"HPO id: {r.get('hpo_id','')}\n"
                    f"Normalized phenotype as extracted from the DSM text: "
                    f"{r.get('normalized_phenotype','')}\n"
                    f"Centrality recorded at stage 1: {r.get('centrality','')}\n"
                    f"Rationale recorded at stage 1: {(r.get('rationale','') or '')[:400]}")
            for attempt in range(5):
                try:
                    resp = client.chat.completions.create(
                        model=a.model,
                        messages=[{"role": "developer", "content": dev},
                                  {"role": "user", "content": user}],
                        response_format={"type": "json_schema", "json_schema": SCHEMA})
                    break
                except Exception as e:
                    perm = _is_permanent(e)
                    if perm:
                        sys.exit(f"\nPERMANENT API ERROR ({perm}), not retrying. "
                                 f"{len(results)} of {len(rows)} targets completed and are saved in "
                                 f"{raw}; re-running this command resumes from there.\n  {e}")
                    if attempt == 4:
                        raise
                    w = min(90, 4 * (2 ** attempt))
                    print(f"    retry {attempt+1} after {w}s: {type(e).__name__}", flush=True)
                    time.sleep(w)
            p = json.loads(resp.choices[0].message.content)
            if p.get("item_id") not in units + ["none"]:
                sys.exit(f"model returned item_id {p.get('item_id')!r}, not one of {units}")
            rec = {"disorder": spec["disorder"], "hpo_id": r["hpo_id"],
                   "hpo_label": r.get("hpo_label", ""), "category": r.get("category", ""),
                   "centrality": r.get("centrality", ""), **p,
                   "prompt_sha": sha, "spec_version": spec.get("spec_version", ""),
                   "model": getattr(resp, "model", a.model)}
            fh.write(json.dumps(rec) + "\n"); fh.flush()
            results.append(rec)
            print(f"  [{i}/{len(rows)}] {r.get('hpo_label','')[:44]:44s} -> {p['item_id']}", flush=True)

    cols = ["disorder", "hpo_id", "hpo_label", "category", "centrality", "item_id",
            "second_item_id", "attributable", "confidence", "needs_manual_review", "reason",
            "prompt_sha", "spec_version", "model"]
    with (out / "03_target_criterion_units.tsv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter="\t", extrasaction="ignore")
        w.writeheader(); w.writerows(results)
    print(f"  wrote {out/'03_target_criterion_units.tsv'} ({len(results)} rows)")

    cat = {}
    cp = root / a.catalog
    if cp.exists():
        for r in csv.DictReader(cp.open(encoding="utf-8"), delimiter="\t"):
            if r["disorder"] == spec["disorder"]:
                cat[r["hpo_id"]] = r["criterion_id"].split(".", 1)[1]
    both = [r for r in results if r["hpo_id"] in cat]
    if both:
        cat_units = {cat[r["hpo_id"]] for r in both}
        same_grain = cat_units <= set(units + ["none"])
        n_diff = sum(1 for r in both if r["item_id"] != cat[r["hpo_id"]])
        print(f"  DIFF against the older mappability attribution, for inspection only. It is not a "
              f"control: it predates this design, its elaboration tier learned from the quarantined "
              f"category vocabulary, and it is not independent of what it would be validating.")
        print(f"    {len(both)} shared targets, "
              f"{'same grain' if same_grain else 'DIFFERENT GRAIN, so a row-by-row diff is not meaningful'}"
              f", {n_diff} differ")
        if same_grain:
            for r in both:
                if r["item_id"] != cat[r["hpo_id"]]:
                    print(f"      differs: {r['hpo_label'][:44]:44s} criterion-grounded="
                          f"{r['item_id']:5s} older={cat[r['hpo_id']]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
