import csv, os, collections, math
from pathlib import Path
import numpy as np
csv.field_size_limit(10**9)
ROOT = Path(os.environ.get("FACET_ROOT", "."))
MC = ROOT / "mappability_catalog"
FV = MC / "genotype_face_validity_seco_criterion_strictonly_prev25_span1_k4_a2floor_ncdB_constructfiltered_idd20260910.tsv"
MX = MC / "match_export_criterion_strictonly_prev25_span1_k4_a2floor_ncdB_constructfiltered_idd20260910.tsv"
LABELS = ROOT / "audit/geneclust_2026-10-08/labels_corrected_2026-10-08.tsv"
DS = ["ASD", "SCZ", "ID", "NCD", "MDD"]
LABEL_NAME = {"ASD": "ASD", "SCZ": "SCZ", "ID": "IDD", "NCD": "NCD", "MDD": "MDD"}
TOPB = {"ASD": 4, "SCZ": 2, "ID": 2, "NCD": 2, "MDD": 3}

par = collections.defaultdict(set); kids = collections.defaultdict(set); name = {}; _cur = None
for _l in open(ROOT / "MPheno_OBO.ontology", encoding="utf-8"):
    _l = _l.rstrip("\n")
    if _l == "[Term]": _cur = None
    elif _l.startswith("id: MP:"): _cur = _l[4:]
    elif _l.startswith("name: ") and _cur: name[_cur] = _l[6:]
    elif _l.startswith("is_a: ") and _cur: _p = _l[6:16]; par[_cur].add(_p); kids[_p].add(_cur)
_am, _dm = {}, {}
def anc(t):
    if t not in _am:
        s = set()
        for p in par.get(t, ()): s |= {p} | anc(p)
        _am[t] = s
    return _am[t]
def desc(t):
    if t not in _dm:
        s = set()
        for k in kids.get(t, ()): s |= {k} | desc(k)
        _dm[t] = s
    return _dm[t]

ann = {}
for r in csv.DictReader(open(ROOT / "broad_benchmark_setup/01_all_genotype_summary.csv", encoding="utf-8")):
    ann[r["genotype_id"]] = [m.strip() for m in r["mp_ids"].split("|") if m.strip()]
FVR = collections.defaultdict(dict)
for r in csv.DictReader(open(FV, encoding="utf-8"), delimiter="\t"): FVR[r["disorder"]][r["genotype_id"]] = r
POOL = sorted(FVR["ASD"])
POS = collections.defaultdict(set)
for r in csv.DictReader(open(LABELS, encoding="utf-8"), delimiter="\t"):
    if r["label_corrected"] == "1": POS[r["disorder"]].add(r["genotype_id"])
def curated(d, g): return g in POS[LABEL_NAME[d]]

matches = collections.defaultdict(list)
for r in csv.DictReader(open(MX, encoding="utf-8"), delimiter="\t"): matches[r["disorder"]].append(r)
def _prev(t):
    sub = desc(t) | {t}
    return sum(1 for g in POOL if any(x in sub for x in ann.get(g, ()))) / len(POOL)
for _d, _ms in list(matches.items()):
    keep = []
    for m in _ms:
        span = len({mm["cid"] for mm in _ms if mm["mp"] in (desc(m["mp"]) | {m["mp"]})})
        if not (span > 1 and _prev(m["mp"]) > 0.25): keep.append(m)
    matches[_d] = keep
IDX = {d: collections.defaultdict(list) for d in matches}
for _d, _ms in matches.items():
    for m in _ms: IDX[_d][m["mp"]].append(m["cid"])
MATCHED = {d: {m["mp"] for m in matches[d]} for d in matches}

def credits(d, g, drop_ann=frozenset(), drop_match=frozenset()):
    res = collections.defaultdict(set)
    for t in ann.get(g, []):
        if t in drop_ann: continue
        for a in anc(t) | {t}:
            if a in drop_match: continue
            for cid in IDX[d].get(a, ()): res[cid].add(t)
    return res

def gate():
    return {d: sum(1 for g in POOL if set(credits(d, g)) == {c for c in FVR[d][g]["breadth_crit"].split(";") if c}) for d in DS}

def nbeh(g):
    return sum(1 for m in ann.get(g, ()) if m == "MP:0004924" or "MP:0004924" in anc(m))
def stratum(g):
    n = nbeh(g)
    return 0 if n == 0 else 1 if n <= 2 else 2 if n <= 5 else 3 if n <= 10 else 4
