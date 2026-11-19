import json
from common import *
from scipy.stats import wilcoxon
S = load_summary(); key, _ = cluster_keys(S)
FV = U / "mappability_catalog/genotype_face_validity_seco_criterion_strictonly_prev25_span1_k4_a2floor_ncdB_constructfiltered_idd20260910.tsv"
R = collections.defaultdict(dict)
for r in csv.DictReader(open(FV, encoding="utf-8"), delimiter="\t"): R[r["disorder"]][r["genotype_id"]] = r
POOL = sorted(R["ASD"])
FVD = {"ASD": "ASD", "SCZ": "SCZ", "IDD": "ID", "NCD": "NCD", "MDD": "MDD"}
POS = collections.defaultdict(set)
for r in csv.DictReader(open(__import__("os").environ.get("FACET_ROOT", ".") + "/audit/geneclust_2026-10-08/labels_corrected_2026-10-08.tsv"), delimiter="\t"):
    if r["label_corrected"] == "1": POS[r["disorder"]].add(r["genotype_id"])
br = lambda D, g: int(R[FVD[D]][g]["breadth"] or 0)
SUP = {}
for D, (con, h, f, pil, _) in GOLD.items():
    g = load_gold(f, con); SUP[D] = dict(zip(g.genotype_id, g.score_a))

par = collections.defaultdict(set); name = {}; cur = None
for l in open(U / "MPheno_OBO.ontology", encoding="utf-8"):
    l = l.rstrip("\n")
    if l == "[Term]": cur = None
    elif l.startswith("id: MP:"): cur = l[4:]
    elif l.startswith("name: ") and cur: name[cur] = l[6:]
    elif l.startswith("is_a: ") and cur: par[cur].add(l[6:16])
memo = {}
def anc(t):
    if t not in memo:
        s = set()
        for p in par.get(t, ()): s |= {p} | anc(p)
        memo[t] = s
    return memo[t]
CLASSES = [("motor behavior", ["MP:0002066"]), ("sensory behavior and reflexes", ["MP:0002067"]), ("seizures", ["MP:0002064"]),
           ("social and vocal", ["MP:0002557", "MP:0001529"]), ("cognition", ["MP:0014114"]), ("emotion and affect", ["MP:0002572"]),
           ("other behavior", ["MP:0004924"]), ("nervous system morphology", ["MP:0003632"]), ("nervous system physiology", ["MP:0003633"]),
           ("ear and eye", ["MP:0005377", "MP:0005391"]), ("mortality and growth", ["MP:0010768", "MP:0005378"]), ("other physiology and morphology", [])]
def mpclass(t):
    a = anc(t) | {t}
    for cname, roots in CLASSES:
        if not roots or any(r in a for r in roots): return cname
mps = lambda g: [m.strip() for m in S[g]["mp_ids"].split("|") if m.strip()]
CL = {g: collections.Counter(mpclass(t) for t in mps(g)) for g in POOL}
BEHAV = {"motor behavior", "sensory behavior and reflexes", "seizures", "social and vocal", "cognition", "emotion and affect", "other behavior"}
nbeh = lambda g: sum(v for k, v in CL[g].items() if k in BEHAV)

IMPC = re.compile(r"\((IMPC|KOMP|EUCOMM|NCOM)\)")
npm = lambda g: len([p for p in S[g]["pubmed_ids"].split("|") if p.strip()])
def source(g):
    if IMPC.search(S[g]["allele_symbols"]) and npm(g) == 0: return "IMPC, no literature row"
    if IMPC.search(S[g]["allele_symbols"]): return "IMPC allele with literature"
    return "literature" if npm(g) else "other, no PubMed row"
SRC = {g: source(g) for g in POOL}

AL = {}
for l in open(U / "MGI_PhenotypicAllele.rpt.txt", encoding="utf-8"):
    if l.startswith("#"): continue
    f = l.rstrip("\n").split("\t")
    if len(f) > 5: AL[f[1]] = (f[3], set(f[4].split("|")) - {""})
DRV = re.compile(r"cre|Cre|rtTA|tTA|Flp|FLP|Dre", re.I)
def design(g):
    alle = [a for a in S[g]["allele_symbols"].split("|") if a and not a.endswith("<+>")]
    info = [(a, *AL.get(a, ("?", set()))) for a in alle]
    drivers = [a for a, t, at in info if "Recombinase" in at or (t == "Transgenic" and DRV.search(a) and "Inserted expressed sequence" not in at and False)]
    drivers += [a for a, t, at in info if re.search(r"\(cre|-cre|cre\)|cre/Esr|\(Cre", a) and a not in drivers]
    core = [(a, t, at) for a, t, at in info if a not in drivers]
    if drivers and any("Conditional ready" in at for a, t, at in core): return "conditional (Cre plus floxed allele)"
    if drivers and not core: return "driver or reporter only"
    ats = set().union(*[at for a, t, at in core]) if core else set()
    tys = {t for a, t, at in core}
    if "Humanized sequence" in ats: return "humanized sequence"
    if "Transgenic" in tys and not ({"Targeted", "Endonuclease-mediated"} & tys): return "transgene (random insertion)"
    if "Hypomorph" in ats: return "hypomorph"
    if "Null/knockout" in ats: return "null or knockout"
    if "Chemically induced (ENU)" in tys or any(t.startswith("Chemically") for t in tys): return "chemically induced (ENU)"
    if "Spontaneous" in tys: return "spontaneous"
    if "Gene trapped" in tys: return "gene trap"
    if {"Targeted", "Endonuclease-mediated"} & tys: return "targeted, not null (knock-in, point, other)"
    return "other or unresolved"
DES = {g: design(g) for g in POOL}
def zyg(g):
    comp = [c for c in S[g]["allelic_composition"].split(",") if not DRV.search(c)]
    if not comp: return "unresolved"
    c = comp[0]
    if "/Y" in c or "/0" in c: return "hemizygous"
    if "<+>" in c: return "heterozygous"
    a = c.split("/")
    return "homozygous" if len(a) == 2 and a[0] == a[1] else "compound or other"
ZYG = {g: zyg(g) for g in POOL}

out = {"mp_class_definition": CLASSES}
def prof(G):
    G = list(G); tot = collections.Counter()
    for g in G: tot.update(CL[g])
    n = sum(tot.values()) or 1
    return dict(n=len(G), median_terms=float(np.median([len(mps(g)) for g in G])) if G else None,
                median_behavior_terms=float(np.median([nbeh(g) for g in G])) if G else None,
                any_behavior=round(float(np.mean([nbeh(g) > 0 for g in G])), 3) if G else None,
                social_tested=round(float(np.mean([CL[g]["social and vocal"] > 0 for g in G])), 3) if G else None,
                cognition_tested=round(float(np.mean([CL[g]["cognition"] > 0 for g in G])), 3) if G else None,
                single_pmid=round(float(np.mean([npm(g) == 1 for g in G])), 3) if G else None,
                term_share={k: round(tot[k] / n, 3) for k, _ in CLASSES})
out["annotation_by_curated_set"] = {D: prof(POS[D] & set(POOL)) for D in FVD}
out["annotation_pool"] = prof(POOL)
out["annotation_by_source"] = {s: prof([g for g in POOL if SRC[g] == s]) for s in sorted(set(SRC.values()))}
out["curated_by_source"] = {D: collections.Counter(SRC[g] for g in POS[D] & set(POOL)) for D in FVD}

def perf(D, G):
    G = [g for g in G]
    if not G: return None
    return dict(n=len(G), any_evidence=round(float(np.mean([br(D, g) > 0 for g in G])), 3),
                mean_criteria=round(float(np.mean([br(D, g) for g in G])), 3),
                support_nonzero=round(float(np.mean([SUP[D].get(g, 0) > 0 for g in G])), 3) if D in SUP else None)
out["performance_by_source"] = {D: {s: dict(curated=perf(D, [g for g in POS[D] if g in R[FVD[D]] and SRC[g] == s]),
                                          background=perf(D, [g for g in POOL if g not in POS[D] and SRC[g] == s]))
                                    for s in sorted(set(SRC.values()))} for D in FVD}

bins = lambda g: 0 if nbeh(g) == 0 else 1 if nbeh(g) <= 2 else 2 if nbeh(g) <= 5 else 3
poolbins = collections.Counter(bins(g) for g in POOL); W = {b: poolbins[b] / len(POOL) for b in poolbins}
def std_rate(D, G, fn):
    cell = collections.defaultdict(list)
    for g in G: cell[bins(g)].append(fn(g))
    num = sum(W[b] * np.mean(v) for b, v in cell.items() if b in W); den = sum(W[b] for b in cell if b in W)
    return round(float(num / den), 3) if den else None
des_out = {}
for d in sorted(set(DES.values())):
    G = [g for g in POOL if DES[g] == d]
    row = dict(pool_n=len(G), annotation=prof(G))
    for D in FVD:
        cur = [g for g in G if g in POS[D]]
        row[D] = dict(curated=len(cur), curated_any=round(float(np.mean([br(D, g) > 0 for g in cur])), 3) if cur else None,
                      curated_mean_criteria=round(float(np.mean([br(D, g) for g in cur])), 3) if cur else None,
                      pool_any=round(float(np.mean([br(D, g) > 0 for g in G])), 3),
                      pool_any_behavior_standardized=std_rate(D, G, lambda g: br(D, g) > 0),
                      pool_support_nonzero=round(float(np.mean([SUP[D].get(g, 0) > 0 for g in G])), 3) if D in SUP else None)
    des_out[d] = row
out["design"] = des_out
out["zygosity"] = {z: {D: dict(curated=len([g for g in POOL if ZYG[g] == z and g in POS[D]]),
                              curated_any=round(float(np.mean([br(D, g) > 0 for g in POOL if ZYG[g] == z and g in POS[D]])), 3) if any(ZYG[g] == z and g in POS[D] for g in POOL) else None,
                              curated_mean_criteria=round(float(np.mean([br(D, g) for g in POOL if ZYG[g] == z and g in POS[D]])), 3) if any(ZYG[g] == z and g in POS[D] for g in POOL) else None)
                       for D in FVD} | {"pool_n": sum(1 for g in POOL if ZYG[g] == z)} for z in sorted(set(ZYG.values()))}

cmp = {}
for D in FVD:
    byg = collections.defaultdict(lambda: {"c": [], "n": []})
    for g in POOL:
        gene = key[g].split("+")[0]
        if DES[g] == "conditional (Cre plus floxed allele)": byg[gene]["c"].append(br(D, g))
        elif DES[g] == "null or knockout": byg[gene]["n"].append(br(D, g))
    pairs = [(np.mean(v["c"]), np.mean(v["n"])) for v in byg.values() if v["c"] and v["n"]]
    c = np.array([p[0] for p in pairs]); n = np.array([p[1] for p in pairs])
    try: p = float(wilcoxon(c, n).pvalue) if (c != n).any() else 1.0
    except Exception: p = None
    cmp[D] = dict(genes=len(pairs), conditional_mean=round(float(c.mean()), 3), null_mean=round(float(n.mean()), 3),
                  genes_conditional_higher=int((c > n).sum()), genes_null_higher=int((n > c).sum()), wilcoxon_p=p)
cmpb = {}
for D in FVD:
    byg = collections.defaultdict(lambda: {"c": [], "n": []})
    for g in POOL:
        if nbeh(g) == 0: continue
        gene = key[g].split("+")[0]
        if DES[g] == "conditional (Cre plus floxed allele)": byg[gene]["c"].append(br(D, g))
        elif DES[g] == "null or knockout": byg[gene]["n"].append(br(D, g))
    pairs = [(np.mean(v["c"]), np.mean(v["n"])) for v in byg.values() if v["c"] and v["n"]]
    c = np.array([p[0] for p in pairs]); n = np.array([p[1] for p in pairs])
    try: p = float(wilcoxon(c, n).pvalue) if (c != n).any() else 1.0
    except Exception: p = None
    cmpb[D] = dict(genes=len(pairs), conditional_mean=round(float(c.mean()), 3), null_mean=round(float(n.mean()), 3),
                   genes_conditional_higher=int((c > n).sum()), genes_null_higher=int((n > c).sum()), wilcoxon_p=p)
out["conditional_vs_null_within_gene"] = cmp; out["conditional_vs_null_within_gene_behavior_tested"] = cmpb

def credited_classes(D):
    res = {}
    for tag, G in (("curated", [g for g in POOL if g in POS[D]]), ("background", [g for g in POOL if g not in POS[D]])):
        E = [g for g in G if br(D, g) > 0]
        res[tag] = dict(n_with_evidence=len(E), carries={k: round(float(np.mean([CL[g][k] > 0 for g in E])), 3) for k, _ in CLASSES} if E else None)
    return res
out["classes_among_evidenced"] = {D: credited_classes(D) for D in FVD}
json.dump(out, open(__import__("os").environ.get("FACET_ROOT", ".") + "/audit/geneclust_2026-10-08/landscape.json", "w"), indent=1, default=str)
print("DONE")
