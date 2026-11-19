import json
from common import *
S = load_summary(); key, _ = cluster_keys(S)
cfg = {d["name"]: d for d in json.load(open(U / "disorders_rescue_config.json"))["disorders"]}

par = collections.defaultdict(set); dname = {}; cur = None
for l in open(U / "audit/doid.obo", encoding="utf-8"):
    l = l.rstrip("\n")
    if l == "[Term]": cur = None
    elif l.startswith("id: DOID:"): cur = l[4:]
    elif l.startswith("name: ") and cur: dname[cur] = l[6:]
    elif l.startswith("is_a: DOID:") and cur: par[cur].add(l[6:].split(" ")[0])
memo = {}
def anc(t):
    if t not in memo:
        s = set()
        for p in par.get(t, ()): s |= {p} | anc(p)
        memo[t] = s
    return memo[t]
for r in csv.DictReader(open(U / "MGI_DO.rpt", encoding="utf-8"), delimiter="\t"): dname.setdefault(r["DO Disease ID"], r["DO Disease Name"])

gdo = collections.defaultdict(set); gom = collections.defaultdict(set)
for l in open(U / "MGI_Geno_DiseaseDO.rpt", encoding="utf-8"):
    f = l.rstrip("\n").split("\t")
    if len(f) < 10: continue
    for d in f[7].split("|"):
        if d.startswith("DOID"): gdo[f[9]].add(d)
    for o in f[8].split("|"):
        if o.startswith("OMIM"): gom[f[9]].add(o)

IDHP = {"HP:0001249", "HP:0001256", "HP:0002342", "HP:0010864", "HP:0002187", "HP:0006889", "HP:0006887"}
def freq_ok(fr):
    if fr in ("HP:0040280", "HP:0040281", "HP:0040282"): return True
    m = re.match(r"(\d+)/(\d+)$", fr)
    if m and int(m.group(2)) > 0: return int(m.group(1)) / int(m.group(2)) >= 0.3
    m = re.match(r"([\d.]+)%$", fr)
    if m: return float(m.group(1)) >= 30
    return False
omim_id_any, omim_id_freq = set(), set()
for l in open(U / "phenotype.hpoa", encoding="utf-8"):
    if l.startswith("#") or l.startswith("database_id"): continue
    f = l.rstrip("\n").split("\t")
    if len(f) < 9 or not f[0].startswith("OMIM") or f[3] not in IDHP or f[2] == "NOT": continue
    omim_id_any.add(f[0])
    if freq_ok(f[7]): omim_id_freq.add(f[0])

FV = U / "mappability_catalog/genotype_face_validity_seco_criterion_strictonly_prev25_span1_k4_a2floor_ncdB_constructfiltered_idd20260910.tsv"
R = collections.defaultdict(dict)
for r in csv.DictReader(open(FV, encoding="utf-8"), delimiter="\t"): R[r["disorder"]][r["genotype_id"]] = r
pool = set(R["ASD"])
names = lambda g: [dname.get(d, d) for d in sorted(gdo.get(g, ()))]

out = {}
rx = re.compile(cfg["IntellectualDisability"]["disease_terms_regex"], re.I)
idd_pos = {g for g, r in R["ID"].items() if r["primary"] == "1"}
under = lambda g, root: any(d == root or root in anc(d) for d in gdo.get(g, ()))
cands = {
  "name says intellectual developmental disorder": {g for g in pool if any("intellectual developmental disorder" in n.lower() for n in names(g))},
  "DO term under DOID:1059 intellectual disability": {g for g in pool if under(g, "DOID:1059")},
  "OMIM disease with HPO intellectual disability, any frequency": {g for g in pool if gom.get(g, set()) & omim_id_any},
  "OMIM disease with HPO intellectual disability, frequent or more": {g for g in pool if gom.get(g, set()) & omim_id_freq},
}
grp = {g: S[g]["benchmark_group"] for g in S}
tier0 = {r["genotype_id"]: r["benchmark_group"] for r in csv.DictReader(open(U / "benchmark_tables_per_tier/IntellectualDisability_tier_0.csv", encoding="utf-8"))}
out["idd_current"] = dict(positives_in_pool=len(idd_pos), regex=cfg["IntellectualDisability"]["disease_terms_regex"],
    mixed_in_pool=sorted((g, S[g]["disease_terms"][:70]) for g in pool if tier0.get(g) == "IntellectualDisability_mixed"))
for k, s in cands.items():
    miss = s - idd_pos
    out[f"idd_cand::{k}"] = dict(n_in_pool=len(s), already_positive=len(s & idd_pos), missed=len(miss),
        missed_regex_hit=sum(1 for g in miss if rx.search(S[g]["disease_terms"] or "")),
        missed_by_tier0_group=collections.Counter(tier0.get(g, "?") for g in miss).most_common(),
        examples=sorted({S[g]["disease_terms"][:60] for g in miss})[:40])

ROOTS = {"ASD": ("ASD", ["DOID:0060041"]), "SCZ": ("SCZ", ["DOID:5419"]), "NCD": ("Neurocognitive", ["DOID:1307"]),
         "MDD": ("MDD", ["DOID:1596"]), "ID": ("IntellectualDisability", ["DOID:1059"])}
for d, (cname, roots) in ROOTS.items():
    pos = {g for g, r in R[d].items() if r["primary"] == "1"}
    rxd = re.compile(cfg[cname]["disease_terms_regex"], re.I)
    clos = {g for g in pool if any(under(g, rt) for rt in roots)}
    regex_hit = {g for g in pool if rxd.search(S[g]["disease_terms"] or "")}
    out[f"other::{d}"] = dict(positives=len(pos), regex_hits_in_pool=len(regex_hit), regex_hits_not_positive=len(regex_hit - pos),
        regex_not_positive_groups=collections.Counter(grp.get(g) for g in regex_hit - pos).most_common(),
        DO_closure_in_pool=len(clos), DO_closure_not_positive=len(clos - pos),
        DO_not_positive_examples=sorted({S[g]["disease_terms"][:60] for g in clos - pos})[:15])

crit = lambda x: [c for c in x.split(";") if c] if x else []
def conv_auc(pos):
    y = np.array([1 if g in pos else 0 for g in R["ID"]]); s = np.array([int(R["ID"][g]["breadth"] or 0) for g in R["ID"]])
    return auc(y, s)
mixed = {g for g in pool if tier0.get(g) == "IntellectualDisability_mixed"}
fix1 = idd_pos | cands["name says intellectual developmental disorder"]
fix2 = fix1 | cands["DO term under DOID:1059 intellectual disability"] | mixed
fix3 = fix2 | cands["OMIM disease with HPO intellectual disability, frequent or more"]
RULES = {"as run": idd_pos, "F1 regex adds 'intellectual developmental disorder'": fix1,
         "F2 F1 plus DO closure under DOID:1059 plus mixed": fix2, "F3 F2 plus OMIM-HPO intellectual disability (frequent or more)": fix3}
con, h, f, pil, _ = GOLD["IDD"]
gh = load_gold(h, con); gf = load_gold(f, con); a3 = load_arm3(pil)
res = []
for name, pos in RULES.items():
    row = dict(rule=name, positives_in_pool=len(pos), genes=len({key[g] for g in pos}))
    row["any_evidence"] = sum(1 for g in pos if int(R["ID"][g]["breadth"] or 0) > 0)
    row["rule_meeting_curated"] = sum(1 for g in pos if set(crit(R["ID"][g]["breadth_crit"])) >= {"ID.A", "ID.B"})
    row["rule_meeting_curated_leaf"] = sum(1 for g in pos if set(crit(R["ID"][g]["depth_crit"])) >= {"ID.A", "ID.B"})
    row["convergent_auroc"] = round(conv_auc(pos), 4)
    for pname, g in (("headline", gh), ("fullpool", gf)):
        y = g.genotype_id.isin(pos).astype(int).to_numpy(); s = g.score_a.to_numpy()
        b3 = g.genotype_id.map(a3).fillna(0).to_numpy(); cl = g.genotype_id.map(key).fillna("SINGLETON:x").to_numpy()
        cd, _ = cluster_boot(y, {"f": s, "a3": b3}, cl, 2000, 20261008)
        row[f"{pname}_n_pos"] = int(y.sum()); row[f"{pname}_auroc"] = round(auc(y, s), 4)
        row[f"{pname}_ci_gene"] = list(np.round(pct(cd["f"]), 4))
        row[f"{pname}_delta_arm3"] = round(auc(y, s) - auc(y, b3), 4)
        row[f"{pname}_delta_arm3_ci_gene"] = list(np.round(pct(cd["f"] - cd["a3"]), 4))
    res.append(row); print(json.dumps(row), flush=True)
out["idd_recomputed"] = res
out["idd_added_F2"] = sorted((g, S[g]["allelic_composition"][:45], S[g]["disease_terms"][:60], R["ID"][g]["breadth_crit"]) for g in fix2 - idd_pos)
json.dump(out, open(__import__("os").environ.get("FACET_ROOT", ".") + "/audit/geneclust_2026-10-08/label_audit.json", "w"), indent=1, default=str)
print("DONE")
