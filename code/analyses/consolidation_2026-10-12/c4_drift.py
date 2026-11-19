import json, os
src = open(__import__("os").environ.get("FACET_ROOT", ".") + "/audit/vocab_removal_2026-10-08/vocab_common.py").read()
src = src.replace('ROOT = Path(os.environ.get("FACET_ROOT", "."))', 'ROOT = Path(__import__("os").environ.get("FACET_ROOT", "."))')
src = src.replace('LABELS = ROOT / "audit/geneclust_2026-10-08/labels_corrected_2026-10-08.tsv"', 'LABELS = Path(__import__("os").environ.get("FACET_ROOT", ".") + "/audit/geneclust_2026-10-08/labels_corrected_2026-10-08.tsv")')
exec(src)
from common import cluster_boot, cluster_keys, load_summary, pct, auc as auc2
g0 = gate(); print("gate (record annotations, record ontology):", g0, flush=True)
assert all(v == len(POOL) for v in g0.values()), "gate failed"
cpar = collections.defaultdict(set); cname = {}; _c = None
for _l in open(ROOT / "MGI additional/MPheno_OBO_2026-10-09.ontology", encoding="utf-8"):
    _l = _l.rstrip("\n")
    if _l == "[Term]": _c = None
    elif _l.startswith("id: MP:"): _c = _l[4:]
    elif _l.startswith("name: ") and _c: cname[_c] = _l[6:]
    elif _l.startswith("is_a: ") and _c: cpar[_c].add(_l[6:16])
_cm = {}
def canc(t):
    if t not in _cm:
        s = set()
        for p in cpar.get(t, ()): s |= {p} | canc(p)
        _cm[t] = s
    return _cm[t]
cur = collections.defaultdict(set)
for _l in open(ROOT / "MGI additional/MGI_PhenoGenoMP_2026-10-09.rpt", encoding="utf-8"):
    f = _l.rstrip("\n").split("\t")
    if len(f) >= 7: cur[f[6]].add(f[3])
CPOOL = sorted(g for g, s in cur.items() if len(s) >= 4)
def ccredits(d, g):
    res = set()
    for t in cur.get(g, ()):
        for a in canc(t) | {t}:
            for cid in IDX[d].get(a, ()): res.add(cid)
    return res
S = load_summary(); key, _ = cluster_keys(S)
out = {"gate": g0, "record_pool": len(POOL), "current_pool": len(CPOOL), "in_both": len(set(POOL) & set(CPOOL))}
old_ids = set(name); newterms = {t for t in cname if t not in old_ids}
bnew = collections.Counter()
for g in CPOOL:
    for t in cur[g]:
        if t in newterms and ("MP:0004924" in canc(t) or t == "MP:0004924"): bnew[t] += 1
out["new_terms_in_current_behavioral_annotations"] = len(bnew); out["uses"] = sum(bnew.values())
cred = {}
for d in DS:
    adm = set(IDX[d])
    under = [t for t in bnew if (canc(t) | {t}) & adm]
    cred[d] = dict(creditable_without_new_judgment=len(under), not_creditable=len(bnew) - len(under),
                   not_creditable_examples=[(t, cname.get(t)) for t in bnew if t not in under][:8])
out["new_terms_by_disorder"] = cred
res = {}
for d in DS:
    rec = {}
    old_b = {g: len([c for c in FVR[d][g]["breadth_crit"].split(";") if c]) for g in POOL}
    new_b = {g: len(ccredits(d, g)) for g in CPOOL}
    both = set(POOL) & set(CPOOL)
    rec["genotypes_in_both_with_changed_criterion_count"] = sum(1 for g in both if old_b[g] != new_b[g])
    rec["of_which_up"] = sum(1 for g in both if new_b[g] > old_b[g]); rec["of_which_down"] = sum(1 for g in both if new_b[g] < old_b[g])
    for tag, P, B in (("snapshot of record", POOL, old_b), ("current MGI", CPOOL, new_b)):
        y = np.array([int(curated(d, g)) for g in P]); s = np.array([B[g] for g in P], float); cl = np.array([key.get(g, g) for g in P])
        cd, _ = cluster_boot(y, {"f": s}, cl, 2000, 20261008)
        rec[tag] = dict(n=len(P), n_pos=int(y.sum()), convergent_auroc=round(auc2(y, s), 4), ci_gene=list(np.round(pct(cd["f"]), 4)))
    res[LABEL_NAME[d]] = rec; print(d, json.dumps(rec), flush=True)
out["convergent"] = res
json.dump(out, open(__import__("os").environ.get("FACET_ROOT", ".") + "/audit/geneclust_2026-10-08/c4_drift.json", "w"), indent=1, default=str); print(json.dumps({k: v for k, v in out.items() if k != "convergent"}, default=str)[:3000]); print("DONE")
