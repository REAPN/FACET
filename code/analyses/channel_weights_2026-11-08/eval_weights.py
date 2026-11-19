#!/usr/bin/env python3
import sys, json, collections, csv
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path.cwd(); OUT = ROOT / "audit/channel_weights_2026-11-08"
sys.path.insert(0, str(ROOT / "audit/geneclust_2026-10-08"))
import common
common.U = ROOT; common.B = ROOT / "benchmark"
from common import GOLD, auc, load_gold, load_summary, cluster_keys, cluster_boot
N = {"ASD": "ASD", "SCZ": "SCZ", "IDD": "ID", "NCD": "NCD"}
ARMS = ["wequal", "wlexf1", "wnoemb", "wnolex", "wnores", "wnojac"]; MARGIN = 0.05
LABELS = "labels_corrected_2026-11-02.tsv"
POSC = collections.defaultdict(set)
for r in csv.DictReader(open(ROOT / "audit/geneclust_2026-10-08" / LABELS), delimiter="\t"):
    if r["label_corrected"] == "1": POSC[r["disorder"]].add(r["genotype_id"])
key, _ = cluster_keys(load_summary())
build = json.loads((OUT / "build_weight_arms.json").read_text())
def scores(D, a):
    p = pd.read_csv(ROOT / f"_judgeswap/runs/{N[D]}_{a}_s4_poloff/04_per_genotype_pvalue.tsv", sep="\t")
    return p[p.analysis_mode == "strict"].set_index("genotype_id")["neg_log10_p"]
out = {}
L = ["# Channel weights on the run of record: support AUROC (2026-11-08)", f"Labels: {LABELS}.", "",
     "| Disorder | universe | record | arm | strict admissions kept | pairs needing new judgment | arm AUROC | arm minus record (90% interval) |",
     "|---|---|---|---|---|---|---|---|"]
for D in GOLD:
    con, h, f, _, _ = GOLD[D]; out[D] = {}; b = build[N[D]]["arms"]
    for pool, run in (("headline", h), ("full pool", f)):
        g = load_gold(run, con); y = g.genotype_id.isin(POSC[D]).astype(int).to_numpy(); cl = g.genotype_id.map(key).fillna("SINGLETON:x").to_numpy()
        have = [a for a in ARMS if (ROOT / f"_judgeswap/runs/{N[D]}_{a}_s4_poloff/04_per_genotype_pvalue.tsv").exists()]
        S = {"record": g.score_a.to_numpy()}
        for a in have: S[a] = g.genotype_id.map(scores(D, a)).fillna(0).to_numpy()
        draws, _ = cluster_boot(y, S, cl, 2000, 20261008); r = {}
        for a in ARMS:
            kept = f"{b[a]['strict_arm']} of {b[a]['strict_record']}"; new = str(b[a]["need_new_judgment"])
            if a not in S:
                L.append(f"| {D} | {pool} | {auc(y, S['record']):.3f} | {a} | {kept} | {new} | not run | |"); continue
            d = draws[a] - draws["record"]; lo, hi = np.percentile(d, [5, 95]); diff = auc(y, S[a]) - auc(y, S["record"])
            v = "equivalent" if (lo > -MARGIN and hi < MARGIN) else ("not equivalent" if (lo > MARGIN or hi < -MARGIN) else "inconclusive")
            r[a] = {"auroc": round(auc(y, S[a]), 4), "diff": round(diff, 4), "ci90": [round(lo, 4), round(hi, 4)], "verdict": v}
            L.append(f"| {D} | {pool} | {auc(y, S['record']):.3f} | {a} | {kept} | {new} | {auc(y, S[a]):.3f} | {diff:+.3f} ({lo:+.3f} to {hi:+.3f}), {v} |")
        r["record"] = round(auc(y, S["record"]), 4); out[D][pool] = r
L += ["", "Arms built by build_weight_arms.py: recorded verdicts kept where the pair is still routed to the LLM, judged pairs that lose their route un-judged, newly routed pairs left unjudged (counted, not judged). Coverage AUROC not recomputed."]
(OUT / "RESULT_weight_arms.md").write_text("\n".join(L) + "\n"); (OUT / "RESULT_weight_arms.json").write_text(json.dumps(out, indent=1)); print("\n".join(L))
