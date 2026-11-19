#!/usr/bin/env python3
import sys, json, collections, csv
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path.cwd(); OUT = ROOT / "audit/floor_sweep_record_2026-11-08"
sys.path.insert(0, str(ROOT / "audit/geneclust_2026-10-08"))
import common
common.U = ROOT; common.B = ROOT / "benchmark"
from common import GOLD, auc, load_gold, load_summary, cluster_keys, cluster_boot
N = {"ASD": "ASD", "SCZ": "SCZ", "IDD": "ID", "NCD": "NCD"}; ARMS = ["floor060", "floor065"]; MARGIN = 0.05
POSC = collections.defaultdict(set)
LABELS = "labels_corrected_2026-11-02.tsv"
for r in csv.DictReader(open(ROOT / "audit/geneclust_2026-10-08" / LABELS), delimiter="\t"):
    if r["label_corrected"] == "1": POSC[r["disorder"]].add(r["genotype_id"])
key, _ = cluster_keys(load_summary())
def scores(D, a):
    p = pd.read_csv(ROOT / f"_judgeswap/runs/{N[D]}_{a}_s4_poloff/04_per_genotype_pvalue.tsv", sep="\t")
    return p[p.analysis_mode == "strict"].set_index("genotype_id")["neg_log10_p"]
out = {}; L = ["# Raised judgment floor on the run of record: support AUROC (2026-11-08)", "",
               "| Disorder | universe | record (0.57) | floor 0.60 | 0.60 minus record (90% interval) | floor 0.65 | 0.65 minus record (90% interval) |", "|---|---|---|---|---|---|---|"]
WANT = [d for d in sys.argv[1:] if d in GOLD] or list(GOLD)
for D in WANT:
    con, h, f, _, _ = GOLD[D]; have = [a for a in ARMS if (ROOT / f"_judgeswap/runs/{N[D]}_{a}_s4_poloff/04_per_genotype_pvalue.tsv").exists()]
    out[D] = {}
    for pool, run in (("headline", h), ("full pool", f)):
        g = load_gold(run, con); y = g.genotype_id.isin(POSC[D]).astype(int).to_numpy(); cl = g.genotype_id.map(key).fillna("SINGLETON:x").to_numpy()
        S = {"record": g.score_a.to_numpy()}
        for a in have: S[a] = g.genotype_id.map(scores(D, a)).fillna(0).to_numpy()
        draws, drop = cluster_boot(y, S, cl, 2000, 20261008); r = {"auroc": {a: round(auc(y, S[a]), 4) for a in S}}
        cells = []
        for a in ARMS:
            if a not in S: cells += ["not run", ""]; continue
            d = draws[a] - draws["record"]; lo, hi = np.percentile(d, [5, 95]); diff = auc(y, S[a]) - auc(y, S["record"])
            v = "equivalent" if (lo > -MARGIN and hi < MARGIN) else ("not equivalent" if (lo > MARGIN or hi < -MARGIN) else "inconclusive")
            r[a] = {"diff": round(diff, 4), "ci90": [round(lo, 4), round(hi, 4)], "ci95": [round(x, 4) for x in np.percentile(d, [2.5, 97.5])], "verdict": v}
            cells += [f"{auc(y, S[a]):.3f}", f"{diff:+.3f} ({lo:+.3f} to {hi:+.3f}), {v}"]
        out[D][pool] = r
        L.append(f"| {D} | {pool} | {auc(y, S['record']):.3f} | " + " | ".join(cells) + " |")
L += ["", "Arms built by build_floor_arms.py (fill-judged pairs below the floor un-judged); counts in build_floor_arms.json. Coverage AUROC is not recomputed here."]
tag = "" if WANT == list(GOLD) else "_" + "_".join(WANT)
L.insert(1, f"Labels: {LABELS}.")
(OUT / f"RESULT_floor_arms{tag}.md").write_text("\n".join(L) + "\n"); (OUT / f"RESULT_floor_arms{tag}.json").write_text(json.dumps(out, indent=1)); print("\n".join(L))
