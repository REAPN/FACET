import csv, collections
import numpy as np, pandas as pd
csv.field_size_limit(10**9)
F = {"ASD": "asd_pair_rerank_v3_broad_v3", "SCZ": "scz_pair_rerank_v1", "IDD": "intellectualdisability_pair_rerank_v1", "NCD": "neurocognitive_pair_rerank_v1_ncdB_cf"}
U = {"ASD": "ASD", "SCZ": "SCZ", "IDD": "ID", "NCD": "NCD"}
SC = {"ASD": {"A1", "A2", "A3", "B1", "B2", "B3", "B4"}, "SCZ": {"A1", "A2", "A3", "A4", "A5"}, "IDD": {"A", "B"}, "NCD": {"A", "B"}}
GOLD = {"ASD": ("A1prime", "run_2026-07-28_criterion_v1_asd_poloff_strict"), "SCZ": ("A2", "run_2026-07-28_criterion_v1_scz_poloff_strict"),
        "IDD": ("A2", "run_2026-09-10_topup_intellectualdisability_poloff_strict"), "NCD": ("A2", "run_2026-07-28_criterion_v1_neurocognitive_cf_poloff_strict")}
S = {}
for r in csv.DictReader(open("broad_benchmark_setup/01_all_genotype_summary.csv", encoding="utf-8")):
    S[r["genotype_id"]] = set(x.strip() for x in r["mp_ids"].split("|") if x.strip()) if r["mp_ids"] else set()
lab = pd.read_csv("audit/geneclust_2026-10-08/labels_corrected_2026-11-02.tsv", sep="\t", dtype=str)
def auc(y, s):
    r = pd.Series(s).rank().values; n1 = y.sum(); n0 = len(y) - n1
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)
par = collections.defaultdict(set); cur = None
for l in open("MPheno_OBO.ontology", encoding="utf-8"):
    l = l.strip()
    if l.startswith("id: MP:"): cur = l[4:]
    elif l.startswith("is_a: MP:") and cur: par[cur].add(l[6:16])
ch = collections.defaultdict(set)
for c, ps in par.items():
    for p in ps: ch[p].add(c)
beh = set(); st = ["MP:0004924"]
while st:
    x = st.pop()
    if x in beh: continue
    beh.add(x); st.extend(ch[x])
def binf(n): return 0 if n == 0 else 1 if n <= 2 else 2 if n <= 5 else 3 if n <= 10 else 4
def wauc(y, s, w):
    df = pd.DataFrame({"s": s, "y": y, "w": w}); num = 0.0; below = 0.0; tot_neg = df.w[df.y == 0].sum()
    for sv, grp in df.groupby("s", sort=True):
        tie_neg = grp.w[grp.y == 0].sum(); pos_w = grp.w[grp.y == 1].sum(); num += pos_w * (below + 0.5 * tie_neg); below += tie_neg
    return num / (df.w[df.y == 1].sum() * tot_neg)
print("| Disorder | support score | retrieval only, no LLM | retrieval, admitted pairs only | support score, depth matched | retrieval only, depth matched |")
print("|---|---|---|---|---|---|")
for D, f in [("NCD", F["NCD"])]:
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
        vals = [1 - np.prod([1 - s for s in v]) for v in units.values()]
        return float(np.sum(vals)) / len(SC[D])
    mall = build(t); madm = build(t[t.strict_eligible == "True"])
    g = pd.read_csv(f"benchmark/{GOLD[D][1]}/paired/08_score_pair_diffs.tsv", sep="\t", dtype={"n_mp_threshold": str})
    g = g[(g.contrast == GOLD[D][0]) & (g.n_mp_threshold == "4")]
    pos = set(lab[(lab.disorder == D) & (lab.label_corrected == "1") & (lab.in_k4_pool == "1")].genotype_id)
    y = g.genotype_id.isin(pos).astype(int).values
    s_all = np.array([score(mall, x) for x in g.genotype_id]); s_adm = np.array([score(madm, x) for x in g.genotype_id])
    nb = np.array([len(S.get(x, set()) & beh) for x in g.genotype_id]); b = np.array([binf(n) for n in nb]); w = np.ones(len(y))
    for k in range(5):
        pk = ((b == k) & (y == 1)).sum() / max(1, (y == 1).sum()); nk = ((b == k) & (y == 0)).sum()
        w[(b == k) & (y == 0)] = (pk * (y == 0).sum() / nk) if nk else 0
    print(f"| {D} | {auc(y, g.score_a.values):.3f} | {auc(y, s_all):.3f} | {auc(y, s_adm):.3f} | {wauc(y, g.score_a.values, w):.3f} | {wauc(y, s_all, w):.3f} |")
