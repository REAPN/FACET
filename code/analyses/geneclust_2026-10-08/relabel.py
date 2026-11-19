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
gdo = collections.defaultdict(set); gom = collections.defaultdict(set)
for l in open(U / "MGI_Geno_DiseaseDO.rpt", encoding="utf-8"):
    f = l.rstrip("\n").split("\t")
    if len(f) < 10: continue
    for d in f[7].split("|"):
        if d.startswith("DOID"): gdo[f[9]].add(d)
    for o in f[8].split("|"):
        if o.startswith("OMIM"): gom[f[9]].add(o)
FV = U / "mappability_catalog/genotype_face_validity_seco_criterion_strictonly_prev25_span1_k4_a2floor_ncdB_constructfiltered_idd20260910.tsv"
R = collections.defaultdict(dict)
for r in csv.DictReader(open(FV, encoding="utf-8"), delimiter="\t"): R[r["disorder"]][r["genotype_id"]] = r
pool = set(R["ASD"]); allg = set(S)
FVD = {"ASD": "ASD", "SCZ": "SCZ", "IDD": "ID", "NCD": "NCD", "MDD": "MDD"}
CN = {"ASD": "ASD", "SCZ": "SCZ", "IDD": "IntellectualDisability", "NCD": "Neurocognitive", "MDD": "MDD"}
T0 = {"SCZ": "SCZ_tier_0.csv", "IDD": "IntellectualDisability_tier_0.csv", "NCD": "Neurocognitive_tier_0.csv", "MDD": "MDD_tier_0.csv"}
grp = {D: ({g: s["benchmark_group"] for g, s in S.items()} if D == "ASD" else
           {r["genotype_id"]: r["benchmark_group"] for r in csv.DictReader(open(U / "benchmark_tables_per_tier" / T0[D], encoding="utf-8"))}) for D in CN}
MIX = {D: f"{'ASD' if D=='ASD' else CN[D]}_mixed" for D in CN}

new = {}; reasons = {}
for D in CN:
    old = {g for g in allg if grp[D].get(g) == f"{CN[D]}_primary"}
    mixed = {g for g in allg if grp[D].get(g) == MIX[D]}
    add = {g: "mixed: annotated to this disorder and another" for g in mixed - old}
    if D == "IDD":
        for g in allg - old:
            names = S[g]["disease_terms"].lower()
            if "intellectual developmental disorder" in names: add.setdefault(g, "name: intellectual developmental disorder")
            elif any(d == "DOID:1059" or "DOID:1059" in anc(d) for d in gdo.get(g, ())): add.setdefault(g, "DO closure under DOID:1059")
            elif "DOID:0060488" in gdo.get(g, ()): add.setdefault(g, "override: Pitt-Hopkins syndrome")
    new[D] = old | set(add); reasons[D] = add
    print(D, "old", len(old), "added", len(add), collections.Counter(add.values()))

IDHP = {"HP:0001249", "HP:0001256", "HP:0002342", "HP:0010864", "HP:0002187", "HP:0006889", "HP:0006887"}
strong = set()
for l in open(U / "phenotype.hpoa", encoding="utf-8"):
    if l.startswith("#") or l.startswith("database_id"): continue
    f = l.rstrip("\n").split("\t")
    if len(f) < 9 or not f[0].startswith("OMIM") or f[3] not in IDHP or f[2] == "NOT": continue
    fr = f[7]; ok = fr in ("HP:0040280", "HP:0040281")
    m = re.match(r"(\d+)/(\d+)$", fr)
    if m and int(m.group(2)) >= 3: ok = ok or int(m.group(1)) / int(m.group(2)) >= 0.8
    if ok: strong.add(f[0])
review = collections.Counter()
for g in pool - new["IDD"]:
    if gom.get(g, set()) & strong: review[S[g]["disease_terms"]] += 1

crit = lambda x: [c for c in x.split(";") if c] if x else []
RULE = {"ASD": None, "SCZ": None, "IDD": {"ID.A", "ID.B"}, "NCD": {"NCD.A", "NCD.B"}, "MDD": None}
out = {"added": {D: sorted((g, S[g]["allelic_composition"][:45], S[g]["disease_terms"][:70], why, g in pool) for g, why in reasons[D].items()) for D in CN},
       "override_review_candidates": review.most_common(60)}
rows = []
for D in CN:
    F = R[FVD[D]]
    for tag, P in (("as run", {g for g, r in F.items() if r["primary"] == "1"}), ("corrected", new[D] & pool)):
        y = np.array([1 if g in P else 0 for g in F]); b = np.array([int(F[g]["breadth"] or 0) for g in F])
        row = dict(disorder=D, labels=tag, positives_in_pool=int(y.sum()), genes=len({key[g] for g in P}),
                   any_evidence=int(sum(1 for g in P if int(F[g]["breadth"] or 0) > 0)), convergent_auroc=round(auc(y, b), 4))
        if RULE[D]:
            row["curated_meeting_rule"] = sum(1 for g in P if set(crit(F[g]["breadth_crit"])) >= RULE[D])
            row["curated_meeting_rule_leaf"] = sum(1 for g in P if set(crit(F[g]["depth_crit"])) >= RULE[D])
            row["uncurated_meeting_rule"] = sum(1 for g in F if g not in P and set(crit(F[g]["breadth_crit"])) >= RULE[D])
        if D in GOLD:
            con, h, f, pil, _ = GOLD[D]; a3 = load_arm3(pil)
            for pname, run in (("headline", h), ("fullpool", f)):
                g = load_gold(run, con)
                y2 = g.label.to_numpy() if tag == "as run" else g.genotype_id.isin(new[D]).astype(int).to_numpy()
                s = g.score_a.to_numpy(); b3 = g.genotype_id.map(a3).fillna(0).to_numpy(); bp = g.score_b.to_numpy()
                cl = g.genotype_id.map(key).fillna("SINGLETON:x").to_numpy()
                cd, _ = cluster_boot(y2, {"f": s, "a3": b3, "p": bp}, cl, 2000, 20261008)
                row[f"{pname}_n_pos"] = int(y2.sum()); row[f"{pname}_auroc"] = round(auc(y2, s), 4)
                row[f"{pname}_ci_gene"] = list(np.round(pct(cd["f"]), 3))
                d3 = cd["f"] - cd["a3"]; dp = cd["f"] - cd["p"]
                row[f"{pname}_delta_arm3"] = round(auc(y2, s) - auc(y2, b3), 4); row[f"{pname}_delta_arm3_ci"] = list(np.round(pct(d3), 3))
                row[f"{pname}_delta_arm3_p"] = round(float(min(1, 2 * min((d3 <= 0).mean(), (d3 >= 0).mean()))), 3)
                row[f"{pname}_delta_pub"] = round(auc(y2, s) - auc(y2, bp), 4); row[f"{pname}_delta_pub_ci"] = list(np.round(pct(dp), 3))
        rows.append(row); print(json.dumps(row), flush=True)
out["recomputed"] = rows
with open(__import__("os").environ.get("FACET_ROOT", ".") + "/audit/geneclust_2026-10-08/labels_corrected_2026-10-08.tsv", "w") as fh:
    fh.write("disorder\tgenotype_id\tlabel_as_run\tlabel_corrected\treason\tin_k4_pool\n")
    for D in CN:
        old = {g for g in allg if grp[D].get(g) == f"{CN[D]}_primary"}
        for g in sorted(old | new[D]):
            fh.write(f"{D}\t{g}\t{int(g in old)}\t{int(g in new[D])}\t{reasons[D].get(g, 'as run')}\t{int(g in pool)}\n")
json.dump(out, open(__import__("os").environ.get("FACET_ROOT", ".") + "/audit/geneclust_2026-10-08/relabel.json", "w"), indent=1, default=str)
print("DONE")
