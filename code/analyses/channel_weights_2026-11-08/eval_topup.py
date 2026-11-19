#!/usr/bin/env python3
import sys, json, collections, csv
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path.cwd(); OUT = ROOT / "audit/channel_weights_2026-11-08"
sys.path.insert(0, str(ROOT / "audit/geneclust_2026-10-08"))
import common
common.U = ROOT; common.B = ROOT / "benchmark"
from common import GOLD, auc, load_gold, load_summary, cluster_keys, cluster_boot
CELLS = [("SCZ", "SCZ", "wnolex"), ("NCD", "NCD", "wequal")]; MARGIN = 0.05
POSC = collections.defaultdict(set)
for r in csv.DictReader(open(ROOT / "audit/geneclust_2026-10-08/labels_corrected_2026-11-02.tsv"), delimiter="\t"):
    if r["label_corrected"] == "1": POSC[r["disorder"]].add(r["genotype_id"])
key, _ = cluster_keys(load_summary())
def scores(n, a):
    p = pd.read_csv(ROOT / f"_judgeswap/runs/{n}_{a}_s4_poloff/04_per_genotype_pvalue.tsv", sep="\t")
    return p[p.analysis_mode == "strict"].set_index("genotype_id")["neg_log10_p"]
out = {}; L = ["# Topped-up channel-weight arms: support AUROC (2026-11-09)", "Labels: labels_corrected_2026-11-02.tsv.", "",
               "| Disorder | universe | record | arm, verdicts of record only | arm, topped up | topped up minus record (90% interval) | topped up minus un-topped |", "|---|---|---|---|---|---|---|"]
for D, n, a in CELLS:
    con, h, f, _, _ = GOLD[D]; summ = json.loads((ROOT / f"_judgeswap/{n}_{a}_topup/04_topup_summary.json").read_text()); out[D] = {"topup": summ}
    for pool, run in (("headline", h), ("full pool", f)):
        g = load_gold(run, con); y = g.genotype_id.isin(POSC[D]).astype(int).to_numpy(); cl = g.genotype_id.map(key).fillna("SINGLETON:x").to_numpy()
        S = {"record": g.score_a.to_numpy(), "arm": g.genotype_id.map(scores(n, a)).fillna(0).to_numpy(), "topup": g.genotype_id.map(scores(n, a + "_topup")).fillna(0).to_numpy()}
        draws, _ = cluster_boot(y, S, cl, 2000, 20261008)
        d = draws["topup"] - draws["record"]; lo, hi = np.percentile(d, [5, 95]); diff = auc(y, S["topup"]) - auc(y, S["record"])
        v = "equivalent" if (lo > -MARGIN and hi < MARGIN) else ("not equivalent" if (lo > MARGIN or hi < -MARGIN) else "inconclusive")
        d2 = auc(y, S["topup"]) - auc(y, S["arm"])
        out[D][pool] = {"record": round(auc(y, S["record"]), 4), "arm": round(auc(y, S["arm"]), 4), "topup": round(auc(y, S["topup"]), 4), "diff": round(diff, 4), "ci90": [round(lo, 4), round(hi, 4)], "verdict": v}
        L.append(f"| {D} | {pool} | {auc(y, S['record']):.3f} | {auc(y, S['arm']):.3f} | {auc(y, S['topup']):.3f} | {diff:+.3f} ({lo:+.3f} to {hi:+.3f}), {v} | {d2:+.3f} |")
    L.append(f"| {D} | top-up | {summ['to_judge']} pairs judged, {summ['strict_among_new']} admitted strict | strict admissions {summ['strict_before']} | {summ['strict_after']} | | |")
(OUT / "RESULT_topup_arms.md").write_text("\n".join(L) + "\n"); (OUT / "RESULT_topup_arms.json").write_text(json.dumps(out, indent=1)); print("\n".join(L))
