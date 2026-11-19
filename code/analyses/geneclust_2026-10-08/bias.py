import json, sys
from common import *
import statsmodels.api as sm
exec(open(__import__("os").environ.get("FACET_ROOT", ".") + "/audit/geneclust_2026-10-08/landscape.py").read().split("out = {\"mp_class_definition\"")[0])
V = U / "dnv_catalogs"
def col(path, c="gene_symbol"): return {r[c].upper() for r in csv.DictReader(open(path, encoding="utf-8"), delimiter="\t") if r.get(c)}
G = {"ASD": col(V / "asc_satterstrom2020_asd_genes.tsv") | col(V / "fu2022_asd_genes.tsv"),
     "SCZ": col(V / "schema_scz_gene_list.tsv") | col(V / "denovo_db_scz_genes.tsv"),
     "IDD": col(V / "ddg2p_id_confirmed_dominant.tsv"),
     "MDD": col(U / "rescue_line_output/mdd_t1g_REAL_human_genes.tsv")}
cfg = {d["name"]: d for d in json.load(open(U / "disorders_rescue_config.json"))["disorders"]}
ncd_doids = set(cfg["Neurocognitive"]["doids"])
G["NCD"] = {r["Symbol"].upper() for r in csv.DictReader(open(U / "MGI_DO.rpt", encoding="utf-8"), delimiter="\t")
            if r["DO Disease ID"] in ncd_doids and r["Common Organism Name"].startswith("human")}
ASSAY = {"ASD": ["MP:0002557"], "SCZ": ["MP:0014114", "MP:0002634"], "IDD": ["MP:0014114"], "NCD": ["MP:0014114"], "MDD": ["MP:0002572"]}
ASSAY_NAME = {"ASD": "social", "SCZ": "cognition or sensorimotor gating", "IDD": "cognition", "NCD": "cognition", "MDD": "emotion and affect"}
amemo2 = {}
def tested(g, D):
    k = (g, D)
    if k not in amemo2:
        amemo2[k] = any(m == r or r in anc(m) for m in mps(g) for r in ASSAY[D])
    return amemo2[k]
gp = lambda g, D: any(x in G[D] for x in key[g].split("+"))
TOPB = {"ASD": 3, "SCZ": 2, "IDD": 2, "NCD": 2, "MDD": 3}
out = {"gene_prior_sizes": {D: len(v) for D, v in G.items()}, "assay_family": ASSAY_NAME}
for D in FVD:
    P = POS[D] & set(POOL); bg = [g for g in POOL if g not in P]
    rec = dict(curated_tested=round(float(np.mean([tested(g, D) for g in P])), 3),
               bg_prior_tested=round(float(np.mean([tested(g, D) for g in bg if gp(g, D)])), 3) if any(gp(g, D) for g in bg) else None,
               bg_nonprior_tested=round(float(np.mean([tested(g, D) for g in bg if not gp(g, D)])), 3),
               bg_prior_n=sum(gp(g, D) for g in bg), curated_carrying_prior_gene=round(float(np.mean([gp(g, D) for g in P])), 3))
    X = pd.DataFrame({"prior": [int(gp(g, D)) for g in bg], "log_mp": [np.log1p(len(mps(g))) for g in bg],
                      "log_beh": [np.log1p(nbeh(g)) for g in bg], "tested": [int(tested(g, D)) for g in bg]})
    yy = np.array([int(br(D, g) >= TOPB[D]) for g in bg])
    for cols in (["prior"], ["prior", "log_mp", "log_beh"], ["prior", "log_mp", "log_beh", "tested"]):
        try:
            fit = sm.Logit(yy, sm.add_constant(X[cols])).fit(disp=0)
            ci = np.exp(fit.conf_int().loc["prior"]).tolist()
            rec[f"OR_prior::{'+'.join(cols)}"] = [round(float(np.exp(fit.params["prior"])), 2), round(ci[0], 2), round(ci[1], 2)]
        except Exception as e:
            rec[f"OR_prior::{'+'.join(cols)}"] = str(e)[:80]
    yall = np.array([1 if g in P else 0 for g in POOL]); ball = np.array([br(D, g) for g in POOL])
    tb = np.array([nbeh(g) > 0 for g in POOL]); ta = np.array([tested(g, D) for g in POOL])
    rec["convergent_full"] = round(auc(yall, ball), 4)
    rec["convergent_behavior_tested"] = round(auc(yall[tb], ball[tb]), 4)
    rec["convergent_assay_tested"] = round(auc(yall[ta], ball[ta]), 4) if yall[ta].sum() > 1 else None
    rec["curated_in_assay_tested"] = int(yall[ta].sum())
    if D in GOLD:
        con, h, f, pil, _ = GOLD[D]
        for pname, run in (("headline", h), ("fullpool", f)):
            g = load_gold(run, con); ids = g.genotype_id.to_numpy(); s = g.score_a.to_numpy()
            y = g.genotype_id.isin(POS[D]).astype(int).to_numpy(); cl = g.genotype_id.map(key).fillna("S").to_numpy()
            inpool = np.array([x in R["ASD"] for x in ids])
            beh = np.array([inpool_ and nbeh(x) > 0 for x, inpool_ in zip(ids, inpool)])
            ast = np.array([inpool_ and tested(x, D) for x, inpool_ in zip(ids, inpool)])
            pri = np.array([gp(x, D) if x in key else False for x in ids])
            for tag, m in (("all", np.ones(len(y), bool)), ("bg behaviorally tested", beh), (f"bg {ASSAY_NAME[D]} tested", ast),
                           ("bg carries gene-prior gene", pri), ("bg gene-prior and assay tested", pri & ast)):
                mm = (y == 1) | m
                if (y[mm] == 0).sum() < 10: rec[f"disc::{pname}::{tag}"] = "background under 10"; continue
                cd, _ = cluster_boot(y[mm], {"f": s[mm]}, cl[mm], 1000, 20261008)
                rec[f"disc::{pname}::{tag}"] = dict(n_pos=int(y[mm].sum()), n_bg=int((y[mm] == 0).sum()), auroc=round(auc(y[mm], s[mm]), 4),
                                                     ci_gene=list(np.round(pct(cd["f"]), 3)))
    out[D] = rec; print(D, json.dumps(rec), flush=True)
json.dump(out, open(__import__("os").environ.get("FACET_ROOT", ".") + "/audit/geneclust_2026-10-08/bias.json", "w"), indent=1, default=str)
print("DONE")
