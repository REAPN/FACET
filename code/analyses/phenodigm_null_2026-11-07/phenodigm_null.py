#!/usr/bin/env python3
import sys, json, argparse, collections, csv, time
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / "audit/geneclust_2026-10-08")); sys.path.insert(0, str(ROOT))
import common
common.U = ROOT; common.B = ROOT / "benchmark"
from common import GOLD, auc, load_gold, load_arm3, load_summary, cluster_keys, cluster_boot, pct
import _pilot_multi_2026 as PM
OUT = ROOT / "audit/phenodigm_null_2026-11-07"; OUT.mkdir(parents=True, exist_ok=True)
PIL = {"ASD": ("asd", "_pilot_asd_2026"), "SCZ": ("scz", "_pilot_scz_2026"), "IDD": ("id", "_pilot_id_2026"), "NCD": ("ncd", "_pilot_ncd_2026")}
CAP = 200


def behavioral_terms():
    par = collections.defaultdict(set); cur = None
    for line in open(ROOT / "MPheno_OBO.ontology", encoding="utf-8", errors="replace"):
        line = line.rstrip("\n")
        if line == "[Term]": cur = None
        elif line.startswith("id: MP:"): cur = line[4:]
        elif line.startswith("is_a: MP:") and cur: par[cur].add(line[6:16])
    ch = collections.defaultdict(set)
    for c, ps in par.items():
        for p in ps: ch[p].add(c)
    out = set(); stack = ["MP:0004924"]
    while stack:
        t = stack.pop()
        if t in out: continue
        out.add(t); stack.extend(ch[t])
    return out


def bma_of_sets(M, colmax, idx):
    n_t = M.shape[0]
    h2m = M[:, idx].max(axis=2).sum(axis=0) / n_t
    m2h = colmax[idx].mean(axis=1)
    return 0.5 * (h2m + m2h)


def score(D, n_perm, stratified, seed=1):
    d, pil = PIL[D]
    cfg = json.load(open(ROOT / pil / "baseline_scores/99_baseline_run_config__B1_phenodigm_arm3_2026.json"))
    targets = PM.read_targets(ROOT / cfg["hpo_targets"])
    geno = pd.read_csv(ROOT / "_pilot_multi_2026/_geno_long_reduced.csv")
    pair = PM.read_pair_sim(ROOT / cfg["similarity_table"], set(targets), set(geno["mp_id"]), cfg["similarity_column"])
    universe = sorted(geno["mp_id"].unique()); mp_index = {m: i for i, m in enumerate(universe)}
    n_t, n_m = len(targets), len(universe)
    M = np.zeros((n_t, n_m)); t_index = {h: i for i, h in enumerate(targets)}
    M[pair["hp_id"].map(t_index).to_numpy(), pair["mp_id"].map(mp_index).to_numpy()] = pair["similarity"].to_numpy()
    colmax = M.max(axis=0)
    obs = load_arm3(pil)
    g = geno.copy(); g["ix"] = g["mp_id"].map(mp_index)
    groups = {gid: sub["ix"].to_numpy() for gid, sub in g.groupby("genotype_id")}
    chk = list(groups)[:200]
    rec = np.array([bma_of_sets(M, colmax, groups[x][None, :])[0] for x in chk]); ref = obs.reindex(chk).to_numpy()
    assert np.allclose(rec, ref, atol=1e-9), "BMA recomputation does not match the arm 3 scores of record"
    beh = behavioral_terms() if stratified else None
    uni = np.arange(n_m)
    if stratified:
        isb = np.array([m in beh for m in universe]); ub, uo = uni[isb], uni[~isb]
    rng = np.random.default_rng(seed)
    depth = {gid: min(len(ix), CAP) for gid, ix in groups.items()}
    if stratified:
        bdepth = {gid: int(min(sum(isb[ix]), depth[gid])) for gid, ix in groups.items()}
        strata = sorted(set((depth[x], bdepth[x]) for x in groups))
    else:
        strata = sorted(set((depth[x], None) for x in groups))
    null = {}; t0 = time.time(); CH = 1000
    for (k, b) in strata:
        if k == 0: continue
        vals = np.empty(n_perm)
        for s in range(0, n_perm, CH):
            n = min(CH, n_perm - s)
            if stratified:
                parts = []
                if b > 0: parts.append(np.stack([rng.choice(ub, size=b, replace=False) for _ in range(n)]))
                if k - b > 0: parts.append(np.stack([rng.choice(uo, size=k - b, replace=False) for _ in range(n)]))
                idx = np.concatenate(parts, axis=1)
            else:
                idx = np.stack([rng.choice(uni, size=k, replace=False) for _ in range(n)])
            vals[s:s + n] = bma_of_sets(M, colmax, idx)
        null[(k, b)] = np.sort(vals)
    print(f"{D}: null built over {len(strata)} strata in {time.time() - t0:.0f}s", flush=True)
    rows = []
    for gid, ix in groups.items():
        k = depth[gid]; b = bdepth[gid] if stratified else None; arr = null.get((k, b))
        if arr is None: continue
        o = float(obs.get(gid, np.nan))
        if np.isnan(o): o = bma_of_sets(M, colmax, ix[None, :])[0]
        n_ge = int(len(arr) - np.searchsorted(arr, o, side="left")); p = (1 + n_ge) / (len(arr) + 1)
        rows.append(dict(genotype_id=gid, depth_k=k, depth_b=b, bma_score=o, p_value=p, neg_log10_p=min(4.0, -float(np.log10(p)))))
    tag = "stratified" if stratified else "sizematched"
    df = pd.DataFrame(rows); df.to_csv(OUT / f"{D}_phenodigm_null_{tag}.tsv", sep="\t", index=False)
    return df.set_index("genotype_id")["neg_log10_p"], tag


def evaluate(D, pn, tag):
    S = load_summary(); key, _ = cluster_keys(S)
    POSC = set(r["genotype_id"] for r in csv.DictReader(open(ROOT / "audit/geneclust_2026-10-08/labels_corrected_2026-11-02.tsv"), delimiter="\t")
               if r["disorder"] == D and r["label_corrected"] == "1")
    con, h, f, pil, _ = GOLD[D]; g = load_gold(h, con); ids = g.genotype_id.to_numpy()
    y = np.array([int(x in POSC) for x in ids]); cl = np.array([key.get(x, "SINGLETON:" + x) for x in ids])
    raw = load_arm3(pil)
    sc = {"facet": g.score_a.to_numpy(), "pheno_raw": g.genotype_id.map(raw).fillna(0).to_numpy(), "pheno_null": g.genotype_id.map(pn).fillna(0).to_numpy()}
    draws, drop = cluster_boot(y, sc, cl, 2000, 20261008)
    r = dict(disorder=D, null=tag, n=int(len(y)), n_pos=int(y.sum()))
    for k in sc: r[f"auroc_{k}"] = round(float(auc(y, sc[k])), 4); r[f"ci_{k}"] = [round(float(v), 4) for v in pct(draws[k])]
    for a, b in (("facet", "pheno_raw"), ("facet", "pheno_null"), ("pheno_null", "pheno_raw")):
        d = draws[a] - draws[b]
        r[f"delta_{a}_minus_{b}"] = round(r[f"auroc_{a}"] - r[f"auroc_{b}"], 4); r[f"ci_{a}_minus_{b}"] = [round(float(v), 4) for v in pct(d)]
        r[f"p_{a}_minus_{b}"] = float(min(1.0, 2 * min((d <= 0).mean(), (d >= 0).mean())))
    r["ceiling_pos_pheno_null"] = int((sc["pheno_null"][y == 1] >= 3.9999).sum()); r["ceiling_pos_facet"] = int((sc["facet"][y == 1] >= 3.9999).sum())
    json.dump(r, open(OUT / f"RESULT_{D}_{tag}.json", "w"), indent=1); print(json.dumps(r), flush=True)
    return r


def report():
    L = ["# PhenoDigm referred to the permutation null (corrected labels 2026-11-02, headline universe, K4)", "",
         "PhenoDigm recomputed (arm 3, full profile) is referred to the same null construction as the support score: random MP sets of the genotype's own size, 10,000 draws, p one plus the count at or above the observed over draws plus one, minus log10 p capped at 4. Intervals: 95% gene-clustered bootstrap, 2,000 replicates.", "",
         "| Disorder | null | n (curated) | FACET support AUROC | PhenoDigm raw | PhenoDigm referred to the null | FACET minus PhenoDigm raw (95%, p) | FACET minus PhenoDigm referred (95%, p) | Referred minus raw (95%, p) |", "|---|---|---|---|---|---|---|---|---|"]
    f3 = lambda a, b: f"{a:.3f} ({b[0]:.3f} to {b[1]:.3f})"
    fd = lambda r, k: f"{r['delta_' + k]:+.3f} ({r['ci_' + k][0]:+.3f} to {r['ci_' + k][1]:+.3f}, p {r['p_' + k]:.3f})"
    for p in sorted(OUT.glob("RESULT_*_*.json")):
        r = json.load(open(p))
        L.append(f"| {r['disorder']} | {r['null']} | {r['n']} ({r['n_pos']}) | {f3(r['auroc_facet'], r['ci_facet'])} | {f3(r['auroc_pheno_raw'], r['ci_pheno_raw'])} | {f3(r['auroc_pheno_null'], r['ci_pheno_null'])} | {fd(r, 'facet_minus_pheno_raw')} | {fd(r, 'facet_minus_pheno_null')} | {fd(r, 'pheno_null_minus_pheno_raw')} |")
    (OUT / "RESULT_phenodigm_null.md").write_text("\n".join(L)); print("wrote", OUT / "RESULT_phenodigm_null.md")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--disorder", choices=list(PIL)); ap.add_argument("--n_permutations", type=int, default=10000)
    ap.add_argument("--stratified", action="store_true"); ap.add_argument("--report", action="store_true"); a = ap.parse_args()
    if a.report: report()
    else:
        pn, tag = score(a.disorder, a.n_permutations, a.stratified); evaluate(a.disorder, pn, tag)
