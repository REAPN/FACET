import csv, json, collections, sys
csv.field_size_limit(10**9)
S = {r["genotype_id"]: r for r in csv.DictReader(open("broad_benchmark_setup/01_all_genotype_summary.csv", encoding="utf-8"))}
FV = "mappability_catalog/genotype_face_validity_seco_criterion_strictonly_prev25_span1_k4_a2floor_ncdB_constructfiltered_idd20260910.tsv"
POOL = sorted({r["genotype_id"] for r in csv.DictReader(open(FV, encoding="utf-8"), delimiter="\t") if r["disorder"] == "ASD"})
POS = collections.defaultdict(set)
for r in csv.DictReader(open("audit/geneclust_2026-10-08/labels_corrected_2026-11-02.tsv"), delimiter="\t"):
    if r["label_corrected"] == "1": POS[r["disorder"]].add(r["genotype_id"])
par = collections.defaultdict(set); cur = None
for l in open("MPheno_OBO.ontology", encoding="utf-8"):
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
CLASSES = [("social and vocal", ["MP:0002557", "MP:0001529"]), ("cognition", ["MP:0014114"]), ("emotion and affect", ["MP:0002572"]),
           ("motor behavior", ["MP:0002066"]), ("other behavior", ["MP:0004924", "MP:0002067", "MP:0002064"]),
           ("nervous system morphology", ["MP:0003632"]), ("nervous system physiology", ["MP:0003633"]),
           ("mortality and growth", ["MP:0010768", "MP:0005378"]), ("other physiology and morphology", [])]
def mpclass(t):
    a = anc(t) | {t}
    for cname, roots in CLASSES:
        if not roots or any(r in a for r in roots): return cname
mps = lambda g: [m.strip() for m in S[g]["mp_ids"].split("|") if m.strip()]
CL = {g: collections.Counter(mpclass(t) for t in mps(g)) for g in POOL}
def prof(G):
    G = list(G); tot = collections.Counter()
    for g in G: tot.update(CL[g])
    n = sum(tot.values()) or 1
    return dict(n=len(G), n_terms=sum(tot.values()), share={k: round(tot[k] / n, 4) for k, _ in CLASSES},
                carries={k: round(sum(CL[g][k] > 0 for g in G) / max(len(G), 1), 4) for k, _ in CLASSES})
out = {"classes": CLASSES, "curated": {D: prof(POS[D] & set(POOL)) for D in ["ASD", "SCZ", "IDD", "NCD", "MDD"]},
       "background": {D: prof(set(POOL) - POS[D]) for D in ["ASD", "SCZ", "IDD", "NCD", "MDD"]}, "pool": prof(POOL)}
json.dump(out, open("audit/composition_2026-11-06/composition.json", "w"), indent=1)
for D, v in out["curated"].items(): print(D, v["n"], v["n_terms"], {k: v["share"][k] for k in ["social and vocal", "cognition", "emotion and affect", "motor behavior", "nervous system morphology", "other physiology and morphology"]})
print("pool", out["pool"]["n"], out["pool"]["n_terms"])

ME = "mappability_catalog/match_export_criterion_strictonly_prev25_span1_k4_a2floor_ncdB_constructfiltered_idd20260910.tsv"
MAP = {"ASD": "ASD", "SCZ": "SCZ", "ID": "IDD", "NCD": "NCD", "MDD": "MDD"}
adm = {D: collections.Counter() for D in MAP.values()}; admterms = {D: set() for D in MAP.values()}
for r in csv.DictReader(open(ME, encoding="utf-8"), delimiter="\t"):
    if r["strict"] != "True": continue
    D = MAP[r["disorder"]]
    if r["mp"] in admterms[D]: continue
    admterms[D].add(r["mp"]); adm[D][mpclass(r["mp"])] += 1
out["admitted_terms_by_class"] = {D: {k: adm[D][k] for k, _ in CLASSES} for D in adm}
json.dump(out, open("audit/composition_2026-11-06/composition.json", "w"), indent=1)
for D in adm: print(D, dict(adm[D]))
