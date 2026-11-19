import json, collections
from common import *
import statsmodels.api as sm
exec(open(__import__("os").environ.get("FACET_ROOT", ".") + "/audit/geneclust_2026-10-08/bias.py").read().split("TOPB = ")[0])
gsrc = open(__import__("os").environ.get("FACET_ROOT", ".") + "/audit/geneclust_2026-10-08/gene_vs_curated.py").read()
exec(gsrc.split("out = {\"gene_set_sizes\"")[0].split("exec(open(\"audit/geneclust_2026-10-08/bias.py\").read().split(\"TOPB = \")[0])")[1])
IC = {r["mp_id"]: float(r["ic_prop"]) for r in csv.DictReader(open(U / "mappability_catalog/mp_term_specificity.tsv", encoding="utf-8"), delimiter="\t")}
ROOT = "MP:0004924"
dmemo = {ROOT: 0}
def depth(t):
    if t not in dmemo:
        ds = [depth(p) for p in par.get(t, ()) if p == ROOT or ROOT in anc(p)]
        dmemo[t] = 1 + min(ds)
    return dmemo[t]
def bterms(g): return sorted({t for t in mps(g) if t == ROOT or ROOT in anc(t)})
missing_ic = collections.Counter()
DET = {}
for g in POOL:
    T = bterms(g)
    if not T: continue
    ics = []
    for t in T:
        if t in IC: ics.append(IC[t])
        else: missing_ic[t] += 1
    DET[g] = dict(D1=float(np.mean(ics)) if ics else np.nan, D2=sum(1 for x in ics if x >= 11.0), D3=max(ics) if ics else np.nan,
                  D4=float(np.mean([depth(t) for t in T])), n=len(T))
BA = sorted(DET)
d1 = np.array([DET[g]["D1"] for g in BA]); T1, T2 = np.nanpercentile(d1, [100 / 3, 200 / 3])
def tert(g): x = DET[g]["D1"]; return 0 if x < T1 else 1 if x < T2 else 2
def cstr(g): n = DET[g]["n"]; return 0 if n <= 2 else 1 if n <= 5 else 2 if n <= 10 else 3
out = {"population": "K4 pool, corrected labels 2026-10-08, behaviorally annotated = at least one MP:0004924 descendant",
       "n_behaviorally_annotated": len(BA), "terms_without_ic": dict(missing_ic), "D1_tertile_cuts": [round(T1, 3), round(T2, 3)]}

def wauc(sp, wp, sn, wn):
    o = np.argsort(sn); sn, wn = sn[o], wn[o]; cw = np.concatenate([[0], np.cumsum(wn)])
    lo = np.searchsorted(sn, sp, "left"); hi = np.searchsorted(sn, sp, "right")
    return float(np.sum(wp * (cw[lo] + 0.5 * (cw[hi] - cw[lo]))) / (wp.sum() * cw[-1]))
def boot(ids, y, fn_list, B=1000):
    cl = np.array([key.get(g, g) for g in ids]); codes, members = cluster_index(cl); rng = np.random.default_rng(20261008)
    est = [f(np.arange(len(ids))) for f in fn_list]; draws = []
    for _ in range(B):
        r = np.concatenate([members[i] for i in rng.integers(0, len(members), len(members))])
        if y[r].sum() < 2 or (y[r] == 0).sum() < 2: continue
        draws.append([f(r) for f in fn_list])
    return est, np.array(draws)

A = {}
src_rows = collections.defaultdict(list)
for g in BA: src_rows[SRC[g]].append(DET[g]["D1"])
A["D1_by_source"] = {s: dict(n=len(v), mean=round(float(np.nanmean(v)), 3), median=round(float(np.nanmedian(v)), 3)) for s, v in src_rows.items()}
for D in FVD:
    P = [g for g in BA if g in POS[D]]; unc = [g for g in BA if g not in POS[D]]
    H = [g for g in unc if carries(g, G[D])]; O = [g for g in unc if not carries(g, G[D]) and not carries(g, M[D])]
    summ = lambda X: {k: round(float(np.nanmean([DET[g][k] for g in X])), 3) for k in ("D1", "D2", "D3", "D4", "n")} | {"N": len(X)}
    rec = dict(curated=summ(P), H_lines=summ(H), other_uncurated=summ(O))
    rec["curated_by_source"] = dict(collections.Counter(SRC[g] for g in P))
    ids = P + O; y = np.array([1] * len(P) + [0] * len(O)); s = np.array([DET[g]["D1"] for g in ids])
    est, dr = boot(ids, y, [lambda r: auc(y[r], s[r])])
    rec["AUROC_D1_curated_vs_other"] = dict(auroc=round(est[0], 4), ci_gene=list(np.round(pct(dr[:, 0]), 3)))
    yy = np.array([int(g in POS[D]) for g in BA])
    X = pd.DataFrame({"log_n": [np.log1p(DET[g]["n"]) for g in BA], "D1_z": (d1 - np.nanmean(d1)) / np.nanstd(d1)})
    try:
        fit = sm.Logit(yy, sm.add_constant(X)).fit(disp=0); ci = np.exp(fit.conf_int()).loc["D1_z"].tolist()
        rec["OR_curated_per_SD_D1_adj_log_count"] = [round(float(np.exp(fit.params["D1_z"])), 2), round(ci[0], 2), round(ci[1], 2)]
        ci2 = np.exp(fit.conf_int()).loc["log_n"].tolist()
        rec["OR_curated_log_count_adj_D1"] = [round(float(np.exp(fit.params["log_n"])), 2), round(ci2[0], 2), round(ci2[1], 2)]
    except Exception as e: rec["OR_curated_per_SD_D1_adj_log_count"] = str(e)[:80]
    A[D] = rec; print("A", D, json.dumps(rec), flush=True)
out["A_who_gets_detail"] = A

BC = {}
for D in FVD:
    rec = {}
    fams = [("coverage, convergent AUROC", BA, lambda g: br(D, g))]
    if D in SUP: fams.insert(0, ("support, discrimination AUROC, full pool", BA, lambda g: SUP[D].get(g, 0)))
    for fam, ids0, fn in fams:
        for tag, ids in (("both classes behaviorally annotated, D1-weighted", ids0), ("both classes with D2 at least 1", [g for g in ids0 if DET[g]["D2"] >= 1])):
            ids = list(ids); y = np.array([int(g in POS[D]) for g in ids]); s = np.array([fn(g) for g in ids], float)
            if y.sum() < 5: rec[f"{fam} :: {tag}"] = "positives under 5"; continue
            w = np.array([DET[g]["D1"] for g in ids]); w = w / np.nanmean(w)
            if "weighted" in tag:
                f_u = lambda r: auc(y[r], s[r])
                f_w = lambda r: wauc(s[r][y[r] == 1], w[r][y[r] == 1], s[r][y[r] == 0], w[r][y[r] == 0])
                est, dr = boot(ids, y, [f_u, f_w, lambda r: f_w(r) - f_u(r)])
                rec[f"{fam} :: {tag}"] = dict(n_pos=int(y.sum()), n_neg=int((y == 0).sum()), unweighted=round(est[0], 4), weighted=round(est[1], 4),
                                              weighted_ci_gene=list(np.round(pct(dr[:, 1]), 3)), difference=round(est[2], 4), difference_ci_gene=list(np.round(pct(dr[:, 2]), 4)))
            else:
                full = list(ids0); yf = np.array([int(g in POS[D]) for g in full]); sf_ = np.array([fn(g) for g in full], float)
                keep = np.array([DET[g]["D2"] >= 1 for g in full])
                f_all = lambda r: auc(yf[r], sf_[r])
                def f_sub(r):
                    rr = r[keep[r]]; return auc(yf[rr], sf_[rr]) if yf[rr].sum() > 1 and (yf[rr] == 0).sum() > 1 else np.nan
                est, dr = boot(full, yf, [f_all, f_sub, lambda r: f_sub(r) - f_all(r)])
                rec[f"{fam} :: {tag}"] = dict(n_pos=int(y.sum()), n_neg=int((y == 0).sum()), restricted=round(est[1], 4),
                                              restricted_ci_gene=list(np.round(np.nanpercentile(dr[:, 1], [2.5, 97.5]), 3)),
                                              difference_vs_all_behaviorally_annotated=round(est[2], 4),
                                              difference_ci_gene=list(np.round(np.nanpercentile(dr[:, 2], [2.5, 97.5]), 4)))
    BC[D] = rec; print("BC", D, json.dumps(rec), flush=True)
out["B_C_reward_and_restriction"] = BC

def mauc(sp, cp, sn, cn, ncell):
    pc = np.bincount(cp, minlength=ncell) / len(cp); nc = np.bincount(cn, minlength=ncell)
    w = np.where(nc[cn] > 0, pc[cn] / np.maximum(nc[cn], 1), 0.0)
    return wauc(sp, np.ones(len(sp)), sn, w) if w.sum() > 0 else np.nan
def contrast(Pp, Nn, fn):
    if len(Pp) < 5 or len(Nn) < 10: return None
    ids = Pp + Nn; y = np.array([1] * len(Pp) + [0] * len(Nn)); s = np.array([fn(g) for g in ids], float)
    c1 = np.array([cstr(g) for g in ids]); c12 = np.array([cstr(g) * 3 + tert(g) for g in ids])
    f1 = lambda r: mauc(s[r][y[r] == 1], c1[r][y[r] == 1], s[r][y[r] == 0], c1[r][y[r] == 0], 4)
    f12 = lambda r: mauc(s[r][y[r] == 1], c12[r][y[r] == 1], s[r][y[r] == 0], c12[r][y[r] == 0], 12)
    est, dr = boot(ids, y, [f1, f12, lambda r: f12(r) - f1(r)], B=500)
    empty = sorted(set(int(x) for x in c12[y == 1]) - set(int(x) for x in c12[y == 0]))
    return dict(n_pos=len(Pp), n_neg=len(Nn), count_matched=round(est[0], 4), count_and_detail_matched=round(est[1], 4),
                ci_gene=list(np.round(np.nanpercentile(dr[:, 1], [2.5, 97.5]), 3)), difference=round(est[2], 4),
                difference_ci_gene=list(np.round(np.nanpercentile(dr[:, 2], [2.5, 97.5]), 4)), positive_cells_without_negatives=empty)
DD = {}
for D in FVD:
    P = [g for g in BA if g in POS[D]]; curgenes = {key[g] for g in POS[D] & set(POOL)}
    unc = [g for g in BA if g not in POS[D]]
    H = [g for g in unc if carries(g, G[D])]; Hn = [g for g in H if key[g] not in curgenes]
    O = [g for g in unc if not carries(g, G[D]) and not carries(g, M[D])]
    rec = {}
    for sname, fn in (("coverage", lambda g: br(D, g)), ("support", lambda g: SUP[D].get(g, 0))):
        if sname == "support" and D not in SUP: continue
        rec[f"{sname}: curated vs H lines"] = contrast(P, H, fn)
        rec[f"{sname}: curated vs other uncurated"] = contrast(P, O, fn)
        rec[f"{sname}: H lines without curated gene vs other uncurated"] = contrast(Hn, O, fn)
    DD[D] = rec; print("D", D, json.dumps(rec), flush=True)
out["D_count_and_detail_matched"] = DD
json.dump(out, open(__import__("os").environ.get("FACET_ROOT", ".") + "/audit/geneclust_2026-10-08/detail.json", "w"), indent=1, default=str)
print("DONE")
