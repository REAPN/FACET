import sys, os, json, collections
from pathlib import Path
import numpy as np, pandas as pd
import common
common.U = Path(os.path.expanduser(__import__("os").environ.get("FACET_ROOT", "."))); common.B = common.U / "benchmark"
from common import *
exec(open("run_geneclust.py").read().split("ARMDIR = ")[0].split("S = load_summary()")[1].replace("key, unm = cluster_keys(S)", "", 1)) if False else None
PART = sys.argv[1]
OUT = Path("ncd_wpw_removed_2026-11-02.json")
res = json.load(open(OUT)) if OUT.exists() else {}
D = "NCD"; con, h, f, pil, _ = GOLD[D]
lab = pd.read_csv("labels_corrected_2026-11-02.tsv", sep="\t", dtype=str)
POS = set(lab[(lab.disorder == D) & (lab.label_corrected == "1")].genotype_id)
S = load_summary(); key, unm = cluster_keys(S)
a3map = load_arm3(pil)
B_ = 2000; SEED = 20261008

def prep(run, thr="4"):
    g = pd.read_csv(common.B / run / "paired/08_score_pair_diffs.tsv", sep="\t", dtype={"n_mp_threshold": str})
    g = g[(g.contrast == con) & (g.n_mp_threshold == thr)].reset_index(drop=True)
    y = g.genotype_id.isin(POS).astype(int).to_numpy()
    cl = g.genotype_id.map(key).fillna("SINGLETON:x").to_numpy()
    sc = {"facet": g.score_a.to_numpy(), "arm3": g.genotype_id.map(a3map).fillna(0).to_numpy(), "published": g.score_b.to_numpy()}
    return g, y, cl, sc

def ap(y, s):
    o = np.argsort(-s, kind="stable"); yy = y[o]; prec = np.cumsum(yy) / np.arange(1, len(yy) + 1)
    return float((prec * yy).sum() / yy.sum())

if PART == "1":
    g, y, cl, sc = prep(h)
    cd, drop = cluster_boot(y, sc, cl, B_, SEED); sd = strat_boot(y, sc, B_, SEED)
    r = dict(n=len(y), n_pos=int(y.sum()), auroc=auc(y, sc["facet"]), ci_gene=pct(cd["facet"]).tolist(), ci_genotype=pct(sd["facet"]).tolist(),
             width_ratio=float(np.diff(pct(cd["facet"]))[0] / np.diff(pct(sd["facet"]))[0]), ap=ap(y, sc["facet"]), prevalence=float(y.mean()),
             pos_genes=len(set(cl[y == 1])), kish_pos=kish(collections.Counter(cl[y == 1]).values()), dropped=drop)
    for comp in ("arm3", "published"):
        d = cd["facet"] - cd[comp]
        r[f"auroc_{comp}"] = auc(y, sc[comp]); r[f"delta_{comp}"] = r["auroc"] - r[f"auroc_{comp}"]
        r[f"delta_{comp}_ci_gene"] = pct(d).tolist(); r[f"delta_{comp}_p_gene"] = float(min(1.0, 2 * min((d <= 0).mean(), (d >= 0).mean())))
    res["headline"] = r; print(json.dumps(r, indent=1))
elif PART == "2":
    g, y, cl, sc = prep(h)
    exec(open("run_geneclust.py").read().split("def one_allele")[1].split("which = sys.argv")[0].replace("(y, sc, cl, ndraw=1000, seed=SEED):", "def one_allele(y, sc, cl, ndraw=1000, seed=SEED):", 1)) if False else None
    rng = np.random.default_rng(SEED); cells = collections.defaultdict(list)
    for i, (c, l) in enumerate(zip(cl, y)): cells[(c, l)].append(i)
    cells = [np.array(v) for v in cells.values()]
    single = np.array([v[0] for v in cells if len(v) == 1]); multi = [v for v in cells if len(v) > 1]
    A = {k: [] for k in sc}
    for _ in range(1000):
        rows = np.concatenate([single, np.array([rng.choice(v) for v in multi])]); yy = y[rows]
        for k, s in sc.items(): A[k].append(auc(yy, s[rows]))
    r = {k: [float(np.median(v)), float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] for k, v in A.items()}
    r["n_pos"] = int(y[np.concatenate([single, np.array([v[0] for v in multi])])].sum())
    res["one_allele"] = r; print(json.dumps(r, indent=1))
    g, y, cl, sc = prep(f)
    cd, drop = cluster_boot(y, {"facet": sc["facet"]}, cl, B_, SEED)
    res["fullpool"] = dict(n=len(y), n_pos=int(y.sum()), auroc=auc(y, sc["facet"]), ci_gene=pct(cd["facet"]).tolist(), dropped=drop)
    print(json.dumps(res["fullpool"], indent=1))
elif PART == "3":
    g, y, cl, sc = prep(h, "1")
    res["threshold_k1"] = dict(n=len(y), n_pos=int(y.sum()), auroc=auc(y, sc["facet"]))
    par = collections.defaultdict(set); cur = None
    for l in open(common.U / "MPheno_OBO.ontology", encoding="utf-8"):
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
    def nbeh(x):
        return sum(1 for m in S[x]["mp_ids"].split("|") if m.strip() and (m.strip() == "MP:0004924" or "MP:0004924" in anc(m.strip())))
    BA = {x: nbeh(x) > 0 for x in S}
    g, y, cl, sc = prep(h)
    beh = np.array([BA.get(x, False) for x in g.genotype_id])
    yb, clb, sb = y[beh], cl[beh], sc["facet"][beh]
    cd, drop = cluster_boot(yb, {"facet": sb}, clb, B_, SEED)
    res["headline_both_behaviorally_annotated"] = dict(n=int(beh.sum()), n_pos=int(yb.sum()), auroc=auc(yb, sb), ci_gene=pct(cd["facet"]).tolist(), dropped=drop)
    FV = common.U / "mappability_catalog/genotype_face_validity_seco_criterion_strictonly_prev25_span1_k4_a2floor_ncdB_constructfiltered_idd20260910.tsv"
    R = {}
    for r in csv.DictReader(open(FV, encoding="utf-8"), delimiter="\t"):
        if r["disorder"] == "NCD": R[r["genotype_id"]] = int(r["breadth"] or 0)
    POOL = sorted(R); yall = np.array([1 if x in POS else 0 for x in POOL]); ball = np.array([R[x] for x in POOL], float)
    tb = np.array([BA.get(x, False) for x in POOL]); clp = np.array([key.get(x, "SINGLETON:" + x) for x in POOL])
    res["table2"] = dict(n_curated=int(yall.sum()), curated_behaviorally_annotated_pct=float(100 * tb[yall == 1].mean()), curated_credited=int((ball[yall == 1] > 0).sum()))
    cd, drop = cluster_boot(yall, {"f": ball}, clp, B_, SEED)
    res["convergent"] = dict(n=len(POOL), n_pos=int(yall.sum()), auroc=auc(yall, ball), ci_gene=pct(cd["f"]).tolist(),
                             both_behaviorally_annotated=auc(yall[tb], ball[tb]), n_pos_beh=int(yall[tb].sum()), dropped=drop)
    print(json.dumps({k: res[k] for k in ("threshold_k1", "headline_both_behaviorally_annotated", "table2", "convergent")}, indent=1))
json.dump(res, open(OUT, "w"), indent=1, default=float)
