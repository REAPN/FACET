import json, collections, re
from common import *
import statsmodels.api as sm
from scipy.stats import wilcoxon
exec(open(__import__("os").environ.get("FACET_ROOT", ".") + "/audit/geneclust_2026-10-08/bias.py").read().split("TOPB = ")[0])
gsrc = open(__import__("os").environ.get("FACET_ROOT", ".") + "/audit/geneclust_2026-10-08/gene_vs_curated.py").read()
exec(gsrc.split("out = {\"gene_set_sizes\"")[0].split("exec(open(\"audit/geneclust_2026-10-08/bias.py\").read().split(\"TOPB = \")[0])")[1])
A = U / "MGI additional"
POOLS = set(POOL)
BA = lambda g: nbeh(g) > 0
out = {"population": "K4 pool (32,535), corrected labels 2026-10-08, behaviorally annotated = at least one MP:0004924 descendant"}
DOIDS = {}
for D in FVD:
    ids = set(cfg[CN[D]]["doids"])
    allt = set(dpar) | {p for v in dpar.values() for p in v}
    ids |= {t for t in allt if any(rt == t or rt in danc(t) for rt in ROOTS[D])}
    DOIDS[D] = ids

neg = collections.defaultdict(set); neg_src = collections.Counter()
for l in open(A / "MGI_Geno_NotDiseaseDO.rpt", encoding="utf-8"):
    f = l.rstrip("\n").split("\t")
    if len(f) < 10: continue
    for d in f[7].split("|"):
        for D in FVD:
            if d in DOIDS[D]: neg[D].add(f[9]); neg_src[("NotDiseaseDO", D)] += 0
comp = collections.defaultdict(set)
for g in POOL: comp[(S[g]["allelic_composition"].strip(), S[g]["genetic_background"].strip())].add(g)
compA = collections.defaultdict(set)
for g in POOL: compA[S[g]["allelic_composition"].strip()].add(g)
dmm_unmatched = collections.Counter()
for l in open(A / "MGI_DiseaseMouseModel.rpt", encoding="utf-8"):
    if l.startswith("#"): continue
    f = l.rstrip("\n").split("\t")
    if len(f) < 5 or f[2] != "NOT": continue
    for D in FVD:
        if f[1] in DOIDS[D]:
            hit = comp.get((f[3].strip(), f[4].strip())) or compA.get(f[3].strip())
            if hit: neg[D] |= hit
            else: dmm_unmatched[D] += 1
P1 = {}
for D in FVD:
    N = neg[D] & POOLS; P = POS[D] & POOLS
    rec = dict(explicit_negatives_in_pool=len(N), explicit_negatives_any=len(neg[D]), unmatched_NOT_rows=dmm_unmatched[D],
               conflicts_positive_and_negative=sorted(N & P), negatives=sorted((g, S[g]["allelic_composition"][:50]) for g in N))
    Nn = sorted(N - P)
    if len(Nn) >= 10:
        for sname, fn in (("support, discrimination AUROC", lambda g: SUP[D].get(g, 0) if D in SUP else None), ("coverage, convergent AUROC", lambda g: br(D, g))):
            if "support" in sname and D not in SUP: continue
            ids = sorted(P) + Nn; y = np.array([1] * len(P) + [0] * len(Nn)); s = np.array([fn(g) for g in ids], float)
            cd, _ = cluster_boot(y, {"f": s}, np.array([key[g] for g in ids]), 1000, 20261008)
            rec[sname] = dict(n_pos=len(P), n_neg=len(Nn), auroc=round(auc(y, s), 4), ci_gene=list(np.round(pct(cd["f"]), 3)))
    P1[D] = rec; print("P1", D, {k: v for k, v in rec.items() if k != "negatives"}, flush=True)
out["P1_explicit_negatives"] = P1

BEHN = {"MP:0005386", "MP:0004924"}
normal = collections.defaultdict(set)
for r in csv.DictReader(open(A / "MGI_Pheno_Sex.rpt", encoding="utf-8"), delimiter="\t"):
    t = r["MP ID"]
    if r["Sex-specific Normal Y/N"] == "Y" and (t in BEHN or "MP:0004924" in anc(t)): normal[r["Genotype ID"]].add(t)
NB = {g for g in normal if g in POOLS}
P2 = dict(genotypes_with_normal_behavior_any=len(normal), in_pool=len(NB),
          in_pool_behaviorally_annotated=sum(1 for g in NB if BA(g)), in_pool_not_behaviorally_annotated=sum(1 for g in NB if not BA(g)),
          pool_not_behaviorally_annotated=sum(1 for g in POOL if not BA(g)), terms=collections.Counter(t for g in NB for t in normal[g]).most_common(8))
P2["share_of_not_behaviorally_annotated_with_recorded_normal"] = round(P2["in_pool_not_behaviorally_annotated"] / P2["pool_not_behaviorally_annotated"], 5)
P2["by_curated"] = {D: dict(curated=sum(1 for g in NB if g in POS[D]), curated_n=len(POS[D] & POOLS)) for D in FVD}
out["P2_recorded_normal_behavior"] = P2; print("P2", P2, flush=True)

pubs = collections.Counter(); imsr = {}
for l in open(A / "MRK_Reference.rpt", encoding="utf-8"):
    f = l.rstrip("\n").split("\t")
    if len(f) >= 5: pubs[f[1].upper()] = len({p for p in f[4].split("|") if p.strip()})
for r in csv.DictReader(open(A / "MGI_IMSRKomp.rpt", encoding="utf-8"), delimiter="\t"):
    try: imsr[r["Marker Symbol"].upper()] = int(r["Total number of IMSR Strains"])
    except Exception: pass
def att(g, table):
    ks = [x.upper() for x in key.get(g, "").split("+") if x and x.upper() in table]
    return np.log1p(max(table[x] for x in ks)) if ks else None
ATT = {g: att(g, pubs) for g in POOL}; IMS = {g: att(g, imsr) for g in POOL}
MAP = [g for g in POOL if ATT[g] is not None]
P3 = {"genotypes_with_attention": len(MAP), "genotypes_without": len(POOL) - len(MAP)}
sf = lambda x: S[x]["contains_sfari_gene"] == "True"
def logit(y, X, var):
    fit = sm.Logit(y, sm.add_constant(X)).fit(disp=0); ci = np.exp(fit.conf_int().loc[var]).tolist()
    return [round(float(np.exp(fit.params[var])), 2), round(ci[0], 2), round(ci[1], 2)]
for D in FVD:
    rec = {}
    unc = [g for g in MAP if g not in POS[D]]
    X = pd.DataFrame({"prior": [int(gp(g, D)) for g in unc], "log_att": [ATT[g] for g in unc], "log_imsr": [IMS[g] if IMS[g] is not None else 0 for g in unc],
                      "log_mp": [np.log1p(len(mps(g))) for g in unc], "log_beh": [np.log1p(nbeh(g)) for g in unc], "sfari": [int(sf(g)) for g in unc]})
    yb = np.array([int(BA(g)) for g in unc])
    rec["P3a_behaviorally_annotated_on_prior"] = dict(unadjusted=logit(yb, X[["prior"]], "prior"), adj_attention=logit(yb, X[["prior", "log_att"]], "prior"),
                                                      adj_attention_and_imsr=logit(yb, X[["prior", "log_att", "log_imsr"]], "prior"))
    ks = (3, 4, 5) if D == "ASD" else (2, 3) if D == "MDD" else (2,)
    for k in ks:
        yt = np.array([int(br(D, g) >= k) for g in unc])
        if yt.sum() < 5: rec[f"P3b_tier_{k}"] = "under 5 in tier"; continue
        r = {"n_tier": int(yt.sum())}
        for nm, pv in (("gene prior H", "prior"), ("SFARI", "sfari")):
            if nm == "SFARI" and D != "ASD": continue
            try:
                r[nm] = dict(as_reported=logit(yt, X[[pv, "log_mp", "log_beh"]], pv), adj_attention=logit(yt, X[[pv, "log_mp", "log_beh", "log_att"]], pv),
                             adj_attention_and_imsr=logit(yt, X[[pv, "log_mp", "log_beh", "log_att", "log_imsr"]], pv))
            except Exception as e: r[nm] = str(e)[:80]
        rec[f"P3b_tier_{k}"] = r
    bb = [g for g in MAP if BA(g)]
    Xc = pd.DataFrame({"log_beh": [np.log1p(nbeh(g)) for g in bb], "log_att_z": [ATT[g] for g in bb]})
    Xc["log_att_z"] = (Xc.log_att_z - Xc.log_att_z.mean()) / Xc.log_att_z.std()
    yc = np.array([int(g in POS[D]) for g in bb])
    rec["P3c_curated_OR_per_SD_log_attention_adj_log_beh"] = logit(yc, Xc, "log_att_z")
    rec["P3c_mean_log_attention"] = dict(curated=round(float(np.mean([ATT[g] for g in bb if g in POS[D]])), 3),
                                        H_lines=round(float(np.mean([ATT[g] for g in bb if g not in POS[D] and carries(g, G[D])])), 3),
                                        other=round(float(np.mean([ATT[g] for g in bb if g not in POS[D] and not carries(g, G[D]) and not carries(g, M[D])])), 3))
    P3[D] = rec; print("P3", D, json.dumps(rec), flush=True)
bbm = [g for g in MAP if BA(g)]
T1, T2 = np.percentile([ATT[g] for g in bbm], [100 / 3, 200 / 3]); P3["attention_tertile_cuts_log1p"] = [round(T1, 3), round(T2, 3)]
cstr = lambda g: (lambda n: 0 if n <= 2 else 1 if n <= 5 else 2 if n <= 10 else 3)(nbeh(g))
att3 = lambda g: 0 if ATT[g] < T1 else 1 if ATT[g] < T2 else 2
def wauc(sp, sn, wn):
    o = np.argsort(sn); sn, wn = sn[o], wn[o]; cw = np.concatenate([[0], np.cumsum(wn)])
    lo = np.searchsorted(sn, sp, "left"); hi = np.searchsorted(sn, sp, "right")
    return float(np.mean((cw[lo] + 0.5 * (cw[hi] - cw[lo])) / cw[-1]))
def mauc(sp, cp, sn, cn, nc):
    pc = np.bincount(cp, minlength=nc) / len(cp); ncnt = np.bincount(cn, minlength=nc)
    w = np.where(ncnt[cn] > 0, pc[cn] / np.maximum(ncnt[cn], 1), 0.0)
    return wauc(sp, sn, w) if w.sum() > 0 else np.nan
def contrast(Pp, Nn, fn):
    if len(Pp) < 5 or len(Nn) < 10: return None
    ids = Pp + Nn; y = np.array([1] * len(Pp) + [0] * len(Nn)); s = np.array([fn(g) for g in ids], float)
    c1 = np.array([cstr(g) for g in ids]); c12 = np.array([cstr(g) * 3 + att3(g) for g in ids])
    f1 = lambda r: mauc(s[r][y[r] == 1], c1[r][y[r] == 1], s[r][y[r] == 0], c1[r][y[r] == 0], 4)
    f12 = lambda r: mauc(s[r][y[r] == 1], c12[r][y[r] == 1], s[r][y[r] == 0], c12[r][y[r] == 0], 12)
    codes, members = cluster_index(np.array([key[g] for g in ids])); rng = np.random.default_rng(20261008); dr = []
    for _ in range(500):
        r = np.concatenate([members[i] for i in rng.integers(0, len(members), len(members))])
        if y[r].sum() < 2 or (y[r] == 0).sum() < 2: continue
        a, b = f1(r), f12(r); dr.append((b, b - a))
    dr = np.array(dr); a0 = f1(np.arange(len(ids))); b0 = f12(np.arange(len(ids)))
    empty = sorted(set(int(x) for x in c12[y == 1]) - set(int(x) for x in c12[y == 0]))
    return dict(n_pos=len(Pp), n_neg=len(Nn), count_matched=round(a0, 4), count_and_attention_matched=round(b0, 4),
                ci_gene=list(np.round(np.nanpercentile(dr[:, 0], [2.5, 97.5]), 3)), difference=round(b0 - a0, 4),
                difference_ci_gene=list(np.round(np.nanpercentile(dr[:, 1], [2.5, 97.5]), 4)), positive_cells_without_negatives=empty)
for D in FVD:
    P = [g for g in bbm if g in POS[D]]; curgenes = {key[g] for g in POS[D] & POOLS}
    unc = [g for g in bbm if g not in POS[D]]; H = [g for g in unc if carries(g, G[D])]; Hn = [g for g in H if key[g] not in curgenes]
    O = [g for g in unc if not carries(g, G[D]) and not carries(g, M[D])]
    rec = {}
    for sname, fn in (("coverage", lambda g: br(D, g)), ("support", lambda g: SUP[D].get(g, 0))):
        if sname == "support" and D not in SUP: continue
        rec[f"{sname}: curated vs H lines"] = contrast(P, H, fn)
        rec[f"{sname}: curated vs other uncurated"] = contrast(P, O, fn)
        rec[f"{sname}: H lines without curated gene vs other uncurated"] = contrast(Hn, O, fn)
    P3[D]["P3d"] = rec; print("P3d", D, json.dumps(rec), flush=True)
out["P3_attention"] = P3

REC = {}
for l in open(A / "MGI_Recombinase_Full.rpt", encoding="utf-8"):
    if l.startswith("#") or not l.strip(): continue
    f = l.rstrip("\n").split("\t")
    if len(f) < 7: continue
    det = {x for x in f[3].split("|") if x}
    if not det: cls = "no assay data" if not f[4] else "assayed, nervous system not detected"
    elif "nervous system" not in det: cls = "assayed, nervous system not detected"
    elif det <= {"nervous system", "head", "sensory organs"}: cls = "nervous-system restricted"
    else: cls = "nervous system plus other systems"
    REC[f[1]] = cls
RANK = {"nervous system plus other systems": 3, "nervous-system restricted": 2, "assayed, nervous system not detected": 1, "no assay data": 0}
def drivers(g):
    alle = [a for a in S[g]["allele_symbols"].split("|") if a and not a.endswith("<+>")]
    info = [(a, *AL.get(a, ("?", set()))) for a in alle]
    dr = [a for a, t, at in info if "Recombinase" in at]
    dr += [a for a, t, at in info if re.search(r"\(cre|-cre|cre\)|cre/Esr|\(Cre", a) and a not in dr]
    return dr
def dclass(g):
    cs = [REC.get(a, "no assay data") for a in drivers(g)]
    return max(cs, key=lambda c: RANK[c]) if cs else None
COND = [g for g in POOL if DES[g] == "conditional (Cre plus floxed allele)"]
DC = {g: dclass(g) for g in COND}
P4 = {"conditional_lines_in_pool": len(COND), "class_mix_pool": dict(collections.Counter(DC.values())),
      "class_mix_behaviorally_annotated": dict(collections.Counter(DC[g] for g in COND if BA(g))),
      "class_mix_uncurated_ASD_ceiling_5_or_6": dict(collections.Counter(DC[g] for g in COND if br("ASD", g) >= 5 and g not in POS["ASD"])),
      "driver_alleles_in_report": len(REC), "driver_alleles_in_pool_conditionals_matched": sum(1 for g in COND for a in drivers(g) if a in REC),
      "driver_alleles_in_pool_conditionals": sum(len(drivers(g)) for g in COND)}
for D in FVD:
    rec = {}
    for cls in RANK:
        byg = collections.defaultdict(lambda: {"c": [], "n": []})
        for g in POOL:
            if not BA(g): continue
            gene = key[g].split("+")[0]
            if DES[g] == "conditional (Cre plus floxed allele)" and DC[g] == cls: byg[gene]["c"].append(br(D, g))
            elif DES[g] == "null or knockout": byg[gene]["n"].append(br(D, g))
        pairs = [(np.mean(v["c"]), np.mean(v["n"])) for v in byg.values() if v["c"] and v["n"]]
        if len(pairs) < 20: rec[cls] = dict(genes=len(pairs), note="under 20 genes"); continue
        c = np.array([p[0] for p in pairs]); n = np.array([p[1] for p in pairs])
        p = float(wilcoxon(c, n).pvalue) if (c != n).any() else 1.0
        rec[cls] = dict(genes=len(pairs), conditional_mean=round(float(c.mean()), 3), null_mean=round(float(n.mean()), 3),
                        genes_conditional_higher=int((c > n).sum()), genes_null_higher=int((n > c).sum()), wilcoxon_p=round(p, 5))
    P4[D] = rec; print("P4", D, json.dumps(rec), flush=True)
print("P4 mix", {k: v for k, v in P4.items() if k not in FVD}, flush=True)
out["P4_recombinase"] = P4
json.dump(out, open(__import__("os").environ.get("FACET_ROOT", ".") + "/audit/geneclust_2026-10-08/mgi_add.json", "w"), indent=1, default=str)
print("DONE")
