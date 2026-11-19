import json
from common import *
import statsmodels.api as sm
exec(open(__import__("os").environ.get("FACET_ROOT", ".") + "/audit/geneclust_2026-10-08/bias.py").read().split("TOPB = ")[0])
exec(open("cross.py").read().split("res={}")[0])
src = open("cross.py").read(); exec(src[src.index("bins=lambda"):src.index("res[\"coverage_top_tier_uncurated\"]")])
sf = lambda x: S[x]["contains_sfari_gene"] == "True" if x in S else False
def OR(D, k, prior):
    P = POS[D] & set(POOL); bg = [g for g in POOL if g not in P]
    X = pd.DataFrame({"prior": [int(prior(g)) for g in bg], "log_mp": [np.log1p(len(mps(g))) for g in bg], "log_beh": [np.log1p(nbeh(g)) for g in bg]})
    y = np.array([int(br(D, g) >= k) for g in bg])
    fit = sm.Logit(y, sm.add_constant(X)).fit(disp=0); ci = np.exp(fit.conf_int().loc["prior"]).tolist()
    return dict(n_tier_uncurated=int(y.sum()), OR=[round(float(np.exp(fit.params["prior"])), 2), round(ci[0], 2), round(ci[1], 2)])
res = {}
for k in (3, 4, 5):
    res[f"ASD at {k}"] = dict(gene_prior_H=OR("ASD", k, lambda g: gp(g, "ASD")), SFARI=OR("ASD", k, sf),
        curated_in_tier=len([g for g in POS["ASD"] & set(POOL) if br("ASD", g) >= k]))
    T = {D: {x for x in POOL if br(D, x) >= (k if D == "ASD" else 3 if D == "MDD" else 2)} for D in FVD}
    ps = pairstats(T); res[f"ASD at {k}"]["overlap_ratio_stratified"] = {p: v["ratio_stratified"] for p, v in ps.items() if p.startswith("ASD")}
    print(k, json.dumps(res[f"ASD at {k}"]), flush=True)
for k in (2, 3):
    res[f"MDD at {k}"] = dict(gene_prior_H=OR("MDD", k, lambda g: gp(g, "MDD")), curated_in_tier=len([g for g in POS["MDD"] & set(POOL) if br("MDD", g) >= k]))
    print("MDD", k, json.dumps(res[f"MDD at {k}"]), flush=True)
json.dump(res, open("tier_sweep.json", "w"), indent=1)
