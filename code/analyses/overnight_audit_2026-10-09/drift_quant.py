import json, collections
from common import *
exec(open(__import__("os").environ.get("FACET_ROOT", ".") + "/audit/geneclust_2026-10-08/landscape.py").read().split("out = {\"mp_class_definition\"")[0])
REP = U / "MGI additional/MGI_PhenoGenoMP_2026-10-09.rpt"
cur = collections.defaultdict(set)
for l in open(REP, encoding="utf-8"):
    f = l.rstrip("\n").split("\t")
    if len(f) >= 7: cur[f[6]].add(f[3])
old = collections.defaultdict(set)
for l in open(U / "MGI_PhenoGenoMP.rpt", encoding="utf-8") if (U / "MGI_PhenoGenoMP.rpt").exists() else []:
    f = l.rstrip("\n").split("\t")
    if len(f) >= 7: old[f[6]].add(f[3])
oldont = set(name)
newont = set()
for l in open(U / "MGI additional/MPheno_OBO_2026-10-09.ontology", encoding="utf-8"):
    if l.startswith("id: MP:"): newont.add(l[4:14])
B = lambda t: t == "MP:0004924" or "MP:0004924" in anc(t)
rec = {g: {m.strip() for m in S[g]["mp_ids"].split("|") if m.strip()} for g in POOL}
same = sum(1 for g in POOL if cur.get(g, set()) == rec[g]); gone = sum(1 for g in POOL if g not in cur)
added = sum(len(cur.get(g, set()) - rec[g]) for g in POOL); removed = sum(len(rec[g] - cur.get(g, set())) for g in POOL)
newterm_uses = sum(1 for g in POOL for t in cur.get(g, set()) if t not in oldont)
behchg = sum(1 for g in POOL if {t for t in rec[g] if B(t)} != {t for t in cur.get(g, set()) if t in oldont and B(t)} or any(t not in oldont for t in cur.get(g, set()) - rec[g]))
k4_now = sum(1 for g, s in cur.items() if len(s) >= 4); k4_new = sum(1 for g, s in cur.items() if len(s) >= 4 and g not in rec)
res = dict(record_report="2026-03-23", current_report="2026-10-05 (server date)", record_ontology="2026-05-19", current_ontology="2026-09-23",
           mp_terms_record_ontology=len(oldont), mp_terms_current_ontology=len(newont), new_terms=len(newont - oldont), terms_dropped=len(oldont - newont),
           genotypes_record_report=len(old) or None, genotypes_current_report=len(cur),
           k4_pool=len(POOL), k4_unchanged=same, k4_share_unchanged=round(same / len(POOL), 4), k4_withdrawn=gone,
           k4_term_annotations_added=added, k4_term_annotations_removed=removed, k4_uses_of_terms_newer_than_record_ontology=newterm_uses,
           k4_genotypes_with_behavioral_change_or_new_term=behchg,
           genotypes_with_4_or_more_terms_now=k4_now, of_which_not_in_record_pool=k4_new)
print(json.dumps(res, indent=1)); json.dump(res, open("drift_quant.json", "w"), indent=1)
