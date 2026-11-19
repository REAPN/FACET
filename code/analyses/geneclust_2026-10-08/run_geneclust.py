import sys, json
from common import *
B_ = 2000; SEED = 20261008
S = load_summary(); key, unm = cluster_keys(S)

par = collections.defaultdict(set); cur = None
for l in open(U / "MPheno_OBO.ontology", encoding="utf-8"):
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
    return sum(1 for m in S[g]["mp_ids"].split("|") if m.strip() and (m.strip() == "MP:0004924" or "MP:0004924" in anc(m.strip())))

ARMDIR = Path(__import__("os").environ.get("FACET_ROOT", ".") + "/audit/geneclust_2026-10-08/arms/_audit/runs")
ARMNAME = {"ASD": "ASD", "SCZ": "SCZ", "IDD": "ID", "NCD": "NCD"}
def arm_scores(D, arm, ids):
    p = pd.read_csv(ARMDIR / f"{ARMNAME[D]}_{arm}_s4_poloff/04_per_genotype_pvalue.tsv", sep="\t")
    p = p[p.analysis_mode == "strict"].set_index("genotype_id")["neg_log10_p"]
    return ids.map(p).fillna(0.0).to_numpy()

def summarize(tag, D, y, sc, cl, extra=None):
    cdraw, drop = cluster_boot(y, sc, cl, B_, SEED)
    sdraw = strat_boot(y, sc, B_, SEED)
    rec = dict(analysis=tag, disorder=D, n_pos=int(y.sum()), n_neg=int((y == 0).sum()),
               pos_genes=len(set(cl[y == 1])), kish_pos=round(kish(collections.Counter(cl[y == 1]).values()), 2),
               dropped_replicates=drop)
    a = auc(y, sc["facet"]); rec["auroc"] = a
    rec["ci_genotype"] = list(np.round(pct(sdraw["facet"]), 4)); rec["ci_gene"] = list(np.round(pct(cdraw["facet"]), 4))
    rec["width_ratio"] = round(float(np.diff(pct(cdraw["facet"]))[0] / np.diff(pct(sdraw["facet"]))[0]), 2)
    rec["gene_ci_clear_of_0.5"] = bool(pct(cdraw["facet"])[0] > 0.5)
    for comp in [k for k in sc if k != "facet"]:
        d = cdraw["facet"] - cdraw[comp]; ds = sdraw["facet"] - sdraw[comp]
        rec[f"auroc_{comp}"] = auc(y, sc[comp]); rec[f"delta_{comp}"] = a - rec[f"auroc_{comp}"]
        rec[f"delta_{comp}_ci_genotype"] = list(np.round(pct(ds), 4))
        rec[f"delta_{comp}_ci_gene"] = list(np.round(pct(d), 4))
        rec[f"delta_{comp}_p_gene"] = float(min(1.0, 2 * min((d <= 0).mean(), (d >= 0).mean())))
    if extra: rec.update(extra)
    print(json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in rec.items()}), flush=True)
    return rec

def one_allele(y, sc, cl, ndraw=1000, seed=SEED):
    rng = np.random.default_rng(seed)
    cells = collections.defaultdict(list)
    for i, (c, l) in enumerate(zip(cl, y)): cells[(c, l)].append(i)
    cells = [np.array(v) for v in cells.values()]
    single = np.array([v[0] for v in cells if len(v) == 1]); multi = [v for v in cells if len(v) > 1]
    A = {k: [] for k in sc}
    for _ in range(ndraw):
        rows = np.concatenate([single, np.array([rng.choice(v) for v in multi])]); yy = y[rows]
        for k, s in sc.items(): A[k].append(auc(yy, s[rows]))
    res = {"n_pos": int(y[np.concatenate([single, np.array([v[0] for v in multi])])].sum())}
    for k in A:
        v = np.array(A[k]); res[k] = [round(float(np.median(v)), 4), round(float(np.percentile(v, 2.5)), 4), round(float(np.percentile(v, 97.5)), 4)]
    res["delta_arm3"] = [round(float(np.median(np.array(A["facet"]) - np.array(A["arm3"]))), 4)]
    return res

which = sys.argv[1] if len(sys.argv) > 1 else "main"
out = []
for D, (con, h, f, pil, _) in GOLD.items():
    a3map = load_arm3(pil)
    for pool, run in (("headline", h), ("fullpool", f)):
        g = load_gold(run, con); y = g.label.to_numpy(); cl = g.genotype_id.map(key).fillna("SINGLETON:x").to_numpy()
        sc = {"facet": g.score_a.to_numpy(), "arm3": g.genotype_id.map(a3map).fillna(0).to_numpy(), "published": g.score_b.to_numpy()}
        if which == "main":
            out.append(summarize(pool, D, y, sc, cl))
            if pool == "headline":
                single = np.array([f"S{i}" for i in range(len(y))])
                cd, _ = cluster_boot(y, {"facet": sc["facet"]}, single, B_, SEED)
                print(json.dumps({"unit_test_singletons": D, "ci": list(np.round(pct(cd["facet"]), 4))}), flush=True)
                oa = one_allele(y, sc, cl); oa.update(analysis="one_allele_per_gene", disorder=D); out.append(oa)
                print(json.dumps(oa), flush=True)
        elif which == "supp" and pool == "headline":
            nb = np.array([nbeh(x) for x in g.genotype_id])
            cut = np.percentile(nb[y == 1], 10)
            for tag, m in (("bg_any_behavior", (y == 1) | (nb >= 1)), ("bg_behavior_ge_curated_p10", (y == 1) | (nb >= cut))):
                out.append(summarize(tag, D, y[m], {k: v[m] for k, v in sc.items() if k != "arm3"} , cl[m]))
            for arm in ("R1R2",):
                s2 = dict(sc); s2["facet"] = arm_scores(D, arm, g.genotype_id)
                out.append(summarize("audit_" + arm, D, y, {k: v for k, v in s2.items() if k != "arm3"}, cl))
json.dump(out, open(f__import__("os").environ.get("FACET_ROOT", ".") + "/audit/geneclust_2026-10-08/geneclust_{which}.json", "w"), indent=1, default=float)
print("DONE", which)
