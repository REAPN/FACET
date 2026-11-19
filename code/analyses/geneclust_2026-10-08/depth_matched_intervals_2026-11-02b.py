import sys, csv, json, collections
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path.cwd(); sys.path.insert(0, str(ROOT / "audit/geneclust_2026-10-08"))
import common; common.U = ROOT; common.B = ROOT / "benchmark"
from common import GOLD, load_summary, cluster_keys, cluster_index, pct
csv.field_size_limit(10**9)
exec(open("audit/geneclust_2026-10-08/llm_ablation_2026-11-02.py").read().split("print(\"| Disorder | support score | retrieval only")[0].replace("labels_corrected_2026-10-08.tsv", "labels_corrected_2026-11-02.tsv"))
Ssum = load_summary(); key, _ = cluster_keys(Ssum)
def binf(n): return 0 if n == 0 else 1 if n <= 2 else 2 if n <= 5 else 3 if n <= 10 else 4
def wauc_fast(y, s, w):
    o = np.argsort(s, kind="stable"); s2, y2, w2 = s[o], y[o], w[o]
    starts = np.r_[0, np.nonzero(np.diff(s2))[0] + 1]
    neg = np.add.reduceat(w2 * (y2 == 0), starts); posw = np.add.reduceat(w2 * (y2 == 1), starts)
    below = np.cumsum(neg) - neg + 0.5 * neg
    return float((posw * below).sum() / (posw.sum() * neg.sum()))
out = {}
for D, f in F.items():
    t = pd.read_csv(f"{f}/03_reranked_pairs_filled.tsv", sep="\t", dtype=str, keep_default_na=False)
    u = pd.read_csv(f"DSM5-Mouse-Map/inputs/target_units_{U[D]}.tsv", sep="\t", dtype=str)
    unit = dict(zip(u.hpo_id, u.item_id)); att = dict(zip(u.hpo_id, u.attributable.str.lower() == "true"))
    t = t[t.hpo_id.map(lambda h: att.get(h, False) and unit.get(h) in SC[D])].copy()
    t["ts"] = t.transparent_score.astype(float); t["unit"] = t.hpo_id.map(unit)
    def build(sub):
        m = collections.defaultdict(dict)
        for h, mp, un, s in zip(sub.hpo_id, sub.mp_id, sub.unit, sub.ts):
            k = (un, h); m[mp][k] = max(m[mp].get(k, 0.0), s)
        return m
    def score(m, g):
        best = {}
        for mp in S.get(g, ()):
            for k, s in m.get(mp, {}).items():
                if s > best.get(k, 0.0): best[k] = s
        units = collections.defaultdict(list)
        for (un, h), s in best.items(): units[un].append(s)
        if not units: return 0.0
        return float(np.sum([1 - np.prod([1 - s for s in v]) for v in units.values()])) / len(SC[D])
    mall = build(t); madm = build(t[t.strict_eligible == "True"])
    g = pd.read_csv(f"benchmark/{GOLD[D][1]}/paired/08_score_pair_diffs.tsv", sep="\t", dtype={"n_mp_threshold": str})
    g = g[(g.contrast == GOLD[D][0]) & (g.n_mp_threshold == "4")].reset_index(drop=True)
    pos = set(lab[(lab.disorder == D) & (lab.label_corrected == "1") & (lab.in_k4_pool == "1")].genotype_id)
    y = g.genotype_id.isin(pos).astype(int).values
    sup = g.score_a.values.astype(float); ret = np.array([score(mall, x) for x in g.genotype_id]); adm = np.array([score(madm, x) for x in g.genotype_id])
    nb = np.array([len(S.get(x, set()) & beh) for x in g.genotype_id], float); b = np.array([binf(int(n)) for n in nb])
    cl = g.genotype_id.map(key).fillna("SINGLETON:x").to_numpy(); codes, members = cluster_index(cl); K = len(members)
    def weights(yy, bb):
        w = np.ones(len(yy))
        for k in range(5):
            pk = ((bb == k) & (yy == 1)).sum() / max(1, (yy == 1).sum()); nk = ((bb == k) & (yy == 0)).sum()
            w[(bb == k) & (yy == 0)] = (pk * (yy == 0).sum() / nk) if nk else 0
        return w
    w0 = weights(y, b)
    point = {"support": wauc_fast(y, sup, w0), "retrieval": wauc_fast(y, ret, w0), "count": wauc_fast(y, nb, w0), "admitted": wauc_fast(y, adm, w0)}
    rng = np.random.default_rng(20261008); draws = {k: [] for k in point}; dd = []
    for _ in range(2000):
        pick = rng.integers(0, K, K); mult = np.bincount(pick, minlength=K)[codes].astype(float)
        if (y[mult > 0] == 1).sum() < 2: continue
        yy, bb = y, b
        w = np.ones(len(yy))
        for k in range(5):
            pk = (mult[(bb == k) & (yy == 1)]).sum() / max(1e-9, mult[yy == 1].sum()); nk = mult[(bb == k) & (yy == 0)].sum()
            w[(bb == k) & (yy == 0)] = (pk * mult[yy == 0].sum() / nk) if nk else 0
        wm = w * mult
        a = {k: wauc_fast(y, v, wm) for k, v in (("support", sup), ("retrieval", ret), ("count", nb), ("admitted", adm))}
        for k in a: draws[k].append(a[k])
        dd.append(a["support"] - a["retrieval"])
    r = {k: dict(auroc=round(point[k], 4), ci_gene=list(np.round(pct(np.array(draws[k])), 4))) for k in point}
    dd = np.array(dd); r["support_minus_retrieval"] = dict(diff=round(point["support"] - point["retrieval"], 4), ci_gene=list(np.round(pct(dd), 4)), p=float(min(1.0, 2 * min((dd <= 0).mean(), (dd >= 0).mean()))))
    out[D] = r; print(D, json.dumps(r), flush=True)
json.dump(out, open("audit/geneclust_2026-10-08/depth_matched_intervals_2026-11-02b.json", "w"), indent=1)
