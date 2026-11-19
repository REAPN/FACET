#!/usr/bin/env python3
import sys, json, collections, csv
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / "audit/geneclust_2026-10-08"))
import common
common.U = ROOT; common.B = ROOT / "benchmark"
from common import GOLD, auc, load_gold, load_summary, cluster_keys, cluster_boot

N = {"ASD": "ASD", "SCZ": "SCZ", "IDD": "ID", "NCD": "NCD"}
RECORD_S4 = {"ASD": "asd_pvalue_broad_v3_poloff", "SCZ": "scz_pvalue_v1_poloff",
             "IDD": "intellectualdisability_pvalue_v1_topup20260910_poloff", "NCD": "neurocognitive_pvalue_v1_cf_poloff"}
OUT = ROOT / "audit/nulldepth_2026-11-07"; OUT.mkdir(parents=True, exist_ok=True)
POSC = collections.defaultdict(set)
for r in csv.DictReader(open(ROOT / "audit/geneclust_2026-10-08/labels_corrected_2026-11-02.tsv"), delimiter="\t"):
    if r["label_corrected"] == "1": POSC[r["disorder"]].add(r["genotype_id"])
S = load_summary(); key, _ = cluster_keys(S)

par = collections.defaultdict(set); cur = None
for l in open(ROOT / "MPheno_OBO.ontology", encoding="utf-8"):
    l = l.rstrip("\n")
    if l == "[Term]": cur = None
    elif l.startswith("id: MP:"): cur = l[4:]
    elif l.startswith("is_a: ") and cur: par[cur].add(l[6:16])
memo = {}
def anc(t):
    if t not in memo:
        s = set()
        for p in par.get(t, ()): s |= {p} | anc(p)
        memo[t] = s
    return memo[t]
def nbeh(g):
    return sum(1 for m in S[g]["mp_ids"].split("|") if m.strip() and (m.strip() == "MP:0004924" or "MP:0004924" in anc(m.strip()))) if g in S else 0
def stratum(g):
    n = nbeh(g); return 0 if n == 0 else 1 if n <= 2 else 2 if n <= 5 else 3 if n <= 10 else 4
def wauc(sp, kp, sn, kn):
    pc = np.bincount(kp, minlength=5) / len(kp); nc = np.bincount(kn, minlength=5)
    w = np.where(nc[kn] > 0, pc[kn] / np.maximum(nc[kn], 1), 0.0)
    if w.sum() == 0: return np.nan
    o = np.argsort(sn); sn, w = sn[o], w[o]; cw = np.concatenate([[0], np.cumsum(w)])
    lo = np.searchsorted(sn, sp, "left"); hi = np.searchsorted(sn, sp, "right")
    return float(np.mean((cw[lo] + 0.5 * (cw[hi] - cw[lo])) / cw[-1]))

def strict_p(path):
    p = pd.read_csv(path, sep="\t"); return p[p.analysis_mode == "strict"].set_index("genotype_id")

def main():
    out = {}; L = ["# Depth-stratified permutation null: consolidated result (corrected labels 2026-11-02, headline universe, K4)", "",
                   "Observed support scores are the record's in both columns. The null of record draws k random MP terms. The stratified null draws b behavioral terms (at or below MP:0004924) and k minus b other terms, so each genotype is compared with random annotation of the same size and the same behavioral depth. The score function is the record's.", "",
                   "| Disorder | n (curated) | Support AUROC, null of record | Support AUROC, stratified null | Difference (90% interval) | 95% interval | Behavioral count AUROC | Depth-matched support AUROC, record | Depth-matched, stratified | Ceiling ties, record | Ceiling ties, stratified |",
                   "|---|---|---|---|---|---|---|---|---|---|---|"]
    for D, (con, h, f, _, _) in GOLD.items():
        rec = strict_p(ROOT / RECORD_S4[D] / "04_per_genotype_pvalue.tsv")
        np_ = ROOT / f"_nulldepth/{N[D]}_s4_poloff/04_per_genotype_pvalue.tsv"
        if not np_.exists(): print(f"{D}: stratified run missing ({np_})"); continue
        st = strict_p(np_)
        g = load_gold(h, con); ids = g.genotype_id.to_numpy()
        y = np.array([int(x in POSC[D]) for x in ids]); cl = np.array([key.get(x, "SINGLETON:" + x) for x in ids])
        sc = {"record": g.score_a.to_numpy(),
              "stratified": g.genotype_id.map(st["neg_log10_p"]).fillna(0).clip(upper=4.0).to_numpy(),
              "beh": np.array([nbeh(x) for x in ids], float)}
        draws, drop = cluster_boot(y, sc, cl, 2000, 20261008)
        d = draws["stratified"] - draws["record"]; kk = np.array([stratum(x) for x in ids])
        r = dict(n=int(len(y)), n_pos=int(y.sum()), dropped=drop,
                 auroc_record=round(float(auc(y, sc["record"])), 4), auroc_stratified=round(float(auc(y, sc["stratified"])), 4),
                 auroc_beh=round(float(auc(y, sc["beh"])), 4),
                 diff=round(float(auc(y, sc["stratified"]) - auc(y, sc["record"])), 4),
                 ci90=[round(float(v), 4) for v in np.percentile(d, [5, 95])], ci95=[round(float(v), 4) for v in np.percentile(d, [2.5, 97.5])],
                 ci_stratified=[round(float(v), 4) for v in np.percentile(draws["stratified"], [2.5, 97.5])],
                 dm_record=round(wauc(sc["record"][y == 1], kk[y == 1], sc["record"][y == 0], kk[y == 0]), 4),
                 dm_stratified=round(wauc(sc["stratified"][y == 1], kk[y == 1], sc["stratified"][y == 0], kk[y == 0]), 4),
                 ceiling_record=int((sc["record"][y == 1] >= 3.9999).sum()), ceiling_stratified=int((sc["stratified"][y == 1] >= 3.9999).sum()),
                 n_strata=int(st.groupby(["depth_k", "depth_b"]).ngroups), draws=int(json.load(open(np_.parent / "05_run_config.json"))["n_permutations"]))
        out[D] = r
        L.append(f"| {D} | {r['n']} ({r['n_pos']}) | {r['auroc_record']:.3f} | {r['auroc_stratified']:.3f} ({r['ci_stratified'][0]:.3f} to {r['ci_stratified'][1]:.3f}) | {r['diff']:+.3f} ({r['ci90'][0]:+.3f} to {r['ci90'][1]:+.3f}) | {r['ci95'][0]:+.3f} to {r['ci95'][1]:+.3f} | {r['auroc_beh']:.3f} | {r['dm_record']:.3f} | {r['dm_stratified']:.3f} | {r['ceiling_record']} | {r['ceiling_stratified']} |")
        print(D, json.dumps(r), flush=True)
    L += ["", "Draws per stratum and strata: " + ", ".join(f"{D} {out[D]['draws']} draws over {out[D]['n_strata']} strata" for D in out)]
    (OUT / "RESULT_nulldepth.json").write_text(json.dumps(out, indent=1)); (OUT / "RESULT_nulldepth.md").write_text("\n".join(L))
    print("wrote", OUT / "RESULT_nulldepth.md")

if __name__ == "__main__":
    main()
