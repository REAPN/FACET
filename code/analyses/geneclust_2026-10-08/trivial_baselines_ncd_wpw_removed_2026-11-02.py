import csv, collections
import numpy as np, pandas as pd
csv.field_size_limit(10**9)
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
S = {}
for r in csv.DictReader(open("broad_benchmark_setup/01_all_genotype_summary.csv", encoding="utf-8")):
    mps = set(x.strip() for x in r["mp_ids"].split("|") if x.strip()) if r["mp_ids"] else set()
    S[r["genotype_id"]] = (len(mps), len(mps & beh))
GOLD = {"ASD": ("A1prime", "run_2026-07-28_criterion_v1_asd_poloff_strict"), "SCZ": ("A2", "run_2026-07-28_criterion_v1_scz_poloff_strict"),
        "IDD": ("A2", "run_2026-09-10_topup_intellectualdisability_poloff_strict"), "NCD": ("A2", "run_2026-07-28_criterion_v1_neurocognitive_cf_poloff_strict")}
lab = pd.read_csv("audit/geneclust_2026-10-08/labels_corrected_2026-11-02.tsv", sep="\t", dtype=str)
def auc(y, s):
    r = pd.Series(s).rank().values; n1 = y.sum(); n0 = len(y) - n1
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)
print("| Disorder | support score | behavioral annotation count | any behavioral annotation | MP term count |")
print("|---|---|---|---|---|")
for D, (con, run) in [("NCD", GOLD["NCD"])]:
    g = pd.read_csv(f"benchmark/{run}/paired/08_score_pair_diffs.tsv", sep="\t", dtype={"n_mp_threshold": str})
    g = g[(g.contrast == con) & (g.n_mp_threshold == "4")]
    pos = set(lab[(lab.disorder == D) & (lab.label_corrected == "1") & (lab.in_k4_pool == "1")].genotype_id)
    y = g.genotype_id.isin(pos).astype(int).values
    nb = np.array([S.get(x, (0, 0))[1] for x in g.genotype_id]); nm = np.array([S.get(x, (0, 0))[0] for x in g.genotype_id])
    print(f"| {D} | {auc(y, g.score_a.values):.3f} | {auc(y, nb):.3f} | {auc(y, (nb > 0).astype(int)):.3f} | {auc(y, nm):.3f} |")

def binf(n): return 0 if n == 0 else 1 if n <= 2 else 2 if n <= 5 else 3 if n <= 10 else 4
def wauc(y, s, w):
    order = np.argsort(s, kind="mergesort"); s2 = s[order]; y2 = y[order]; w2 = w[order]
    ranks = pd.Series(s2).rank().values
    neg_w = w2 * (y2 == 0); tot_neg = neg_w.sum()
    cum = np.cumsum(neg_w) - neg_w
    df = pd.DataFrame({"s": s2, "y": y2, "w": w2})
    num = 0.0
    below = 0.0
    for sv, grp in df.groupby("s", sort=True):
        tie_neg = grp.w[grp.y == 0].sum()
        pos_w = grp.w[grp.y == 1].sum()
        num += pos_w * (below + 0.5 * tie_neg)
        below += tie_neg
    return num / (df.w[df.y == 1].sum() * tot_neg)
print()
print("| Disorder | support score, depth matched | behavioral count, depth matched |")
print("|---|---|---|")
for D, (con, run) in [("NCD", GOLD["NCD"])]:
    g = pd.read_csv(f"benchmark/{run}/paired/08_score_pair_diffs.tsv", sep="\t", dtype={"n_mp_threshold": str})
    g = g[(g.contrast == con) & (g.n_mp_threshold == "4")]
    pos = set(lab[(lab.disorder == D) & (lab.label_corrected == "1") & (lab.in_k4_pool == "1")].genotype_id)
    y = g.genotype_id.isin(pos).astype(int).values
    nb = np.array([S.get(x, (0, 0))[1] for x in g.genotype_id]); b = np.array([binf(n) for n in nb])
    w = np.ones(len(y))
    for k in range(5):
        pk = ((b == k) & (y == 1)).sum() / max(1, (y == 1).sum()); nk = ((b == k) & (y == 0)).sum()
        w[(b == k) & (y == 0)] = (pk * (y == 0).sum() / nk) if nk else 0
    print(f"| {D} | {wauc(y, g.score_a.values, w):.3f} | {wauc(y, nb.astype(float), w):.3f} |")
