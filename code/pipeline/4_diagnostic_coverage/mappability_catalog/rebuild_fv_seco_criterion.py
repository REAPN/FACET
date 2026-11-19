#!/usr/bin/env python3
import csv, collections, math, os
CAT=os.path.dirname(os.path.abspath(__file__)); BASE=os.path.dirname(CAT)
def P(*a): return os.path.join(*a)
SECO_T=0.85
SCORED={"symptom","impairment","specifier"}
FLOOR_CRITERIA={("SCZ","SCZ.A1"),
                ("SCZ","SCZ.A2"),
                ("SCZ","SCZ.A3")}
RERANK={"ASD":"asd_pair_rerank_v3_broad_v3","SCZ":"scz_pair_rerank_v1","ID":"intellectualdisability_pair_rerank_v1","NCD":"neurocognitive_pair_rerank_v1"}

parents=collections.defaultdict(set); child=collections.defaultdict(set); alt2canon={}; allt=set()
cur=None; cur_alt=[]; cur_par=[]; obs=False
def flush():
    global cur,cur_alt,cur_par,obs
    if cur and not obs:
        allt.add(cur)
        for p in cur_par: parents[cur].add(p); allt.add(p)
        for a in cur_alt: alt2canon[a]=cur
    cur=None; cur_alt=[]; cur_par=[]; obs=False
for line in open(P(BASE,"MPheno_OBO.ontology"),encoding="utf-8",errors="ignore"):
    line=line.rstrip("\n")
    if line=="[Term]": flush(); continue
    if line.startswith("id: MP:"): cur=line[4:].strip()
    elif line.startswith("alt_id: MP:"): cur_alt.append(line[8:].strip())
    elif line.startswith("is_obsolete: true"): obs=True
    elif line.startswith("is_a:") and cur:
        p=line.split("is_a:")[1].strip().split("!")[0].strip()
        if p.startswith("MP:"): cur_par.append(p)
flush()
for c,ps in parents.items():
    for p in ps: child[p].add(c)
def canon(mp): return alt2canon.get(mp,mp)
_dc={}
def desc(x):
    x=canon(x)
    if x in _dc: return _dc[x]
    seen=set(); st=[x]
    while st:
        n=st.pop()
        for c in child.get(n,()):
            if c not in seen: seen.add(c); st.append(c)
    _dc[x]=seen; return seen
N=len(allt)

_ac={}
def anc(x):
    x=canon(x)
    if x in _ac: return _ac[x]
    seen=set(); st=[x]
    while st:
        n=st.pop()
        for pp in parents.get(n,()):
            if pp not in seen: seen.add(pp); st.append(pp)
    _ac[x]=seen; return seen

_sc={}
def seco(mp):
    mp=canon(mp)
    if mp in _sc: return _sc[mp]
    v=1-math.log(len(desc(mp))+1)/math.log(N); _sc[mp]=v; return v
def hi(mp):
    if _A.depth_rule == "leaf":
        return len(desc(canon(mp))) == 0
    return seco(mp) >= _A.seco_t

import argparse, json
_ap = argparse.ArgumentParser()
_ap.add_argument("--include_provisional", action="store_true",
                 help="count provisional units, e.g. SCZ Criterion B, in breadth and depth")
_ap.add_argument("--depth_rule", choices=("leaf","seco"), default="leaf",
                 help="leaf (default): depth means the strict match landed on an MP term with NO "
                      "descendants, the most specific thing the ontology can say. seco: the legacy "
                      "rule, Seco intrinsic IC at or above --seco_t.")
_ap.add_argument("--seco_t", type=float, default=0.85,
                 help="only used when --depth_rule seco")
_ap.add_argument("--breadth_requires_strict", action="store_true",
                 help="admit a pair to BREADTH only if it carries strict_eligible. The inherited "
                      "behaviour admits broad_eligible too, and 74 to 87 percent of what breadth "
                      "currently rests on is broad-but-not-strict.")
_ap.add_argument("--require_mouse_agreement", choices=("none","any","same"), default="none",
                 help="none: human anchor only (historical). any: mouse term must be admitted "
                      "somewhere. same: mouse term must name the same unit.")
_ap.add_argument("--max_hops", type=int, default=None,
                 help="DRIFT CAP from docket item D-F, adjudicated 2026-07-29. Drop an injected "
                      "match sitting more than N ontology hops below its nearest accepted base "
                      "anchor. The blind-with-criterion re-adjudication rejected injections OUTRIGHT "
                      "at 6.5, 0.0, 20.0 and 25.0 percent for 1, 2, 3 and 4 hops against a 5.0 "
                      "percent control floor, so 2 is the empirically supported cap. Rejection, not "
                      "demotion, is the metric to read: a narrowness objection produces a demotion "
                      "to broad, so the rejection rate is immune to the prompt artifact that voided "
                      "the first pilot.")
_ap.add_argument("--max_prevalence", type=float, default=None,
                 help="UMBRELLA RULE FOR THE FACE VALIDITY WING ONLY. Drop a matched term whose "
                      "subtree is annotated to more than this fraction of the disorder's genotype "
                      "pool. Rationale: gFV asserts that a genotype EVIDENCES a diagnostic "
                      "criterion, and an assertion satisfied by most of the population evidences "
                      "nothing. SCZ Criterion A4 rests on MP:0004924 'abnormal behavior', carried "
                      "by 68.4 percent of the SCZ pool; ASD B4 rests on MP:0002067 at 54.9 percent. "
                      "This is deliberately NOT applied to the discrimination wing, where a "
                      "ubiquitous term is self-neutralising: it raises positives and background "
                      "equally and the stage 4 null is already size matched, so excluding it would "
                      "discard real signal rather than remove a bias.")
_ap.add_argument("--pool", choices=("native","k4"), default="native",
                 help="GENOTYPE UNIVERSE. 'native' (legacy) takes each disorder's rows from "
                      "genotype_face_validity_v2.tsv, and those sets are NOT the same universe: "
                      "ASD 4,919 versus SCZ 18,930, ID 16,569, NCD 18,813, union 24,649, "
                      "intersection only 2,973. ASD's set is a survival from the original "
                      "autism-only generation and does not correspond to any current filter, so "
                      "cross-disorder denominators are not comparable. 'k4' scores every disorder "
                      "on ONE universe, every MGI genotype carrying at least 4 MP terms (32,535), "
                      "which is the universe the discrimination wing already uses. A genotype with "
                      "no matching annotation scores breadth 0, which is the correct answer rather "
                      "than an exclusion.")
_ap.add_argument("--umbrella_span", type=int, default=None,
                 help="CONJUNCTION RULE, 2026-07-29. Use WITH --max_prevalence. A term is an "
                      "umbrella only if it is BOTH prevalent AND non-specific, where non-specific "
                      "means its subtree serves more than N distinct criterion units of the same "
                      "disorder. Prevalence alone cannot separate the two cases that matter: "
                      "MP:0004924 'abnormal behavior' is 68 percent prevalent AND spans SCZ A4, A5 "
                      "and B, so it is generic; MP:0002067 'abnormal sensory capabilities/reflexes/"
                      "nociception' is 55 percent prevalent but spans ONE unit, ASD B4, which it "
                      "very nearly restates. The first is too permissive to evidence anything, the "
                      "second is the correct term for its criterion and happens to be common. The "
                      "structural test alone also fails, flagging specific low-prevalence terms "
                      "such as MP:0001360 'abnormal social investigation' at 6.5 percent. Only the "
                      "conjunction tracks the intended notion of an umbrella.")
_ap.add_argument("--max_anchor_desc", type=int, default=None,
                 help="UMBRELLA SENSITIVITY. Drop any matched MP term with more than N descendants. "
                      "Section 4.2 of the synthesis shows every top coverage driver is a high-level "
                      "umbrella term, and that SCZ Criterion A4 is carried by MP:0004924 'abnormal "
                      "behavior' (546 descendants) covering 12,953 genotypes, about 68 percent of "
                      "the SCZ pool. If SCZ breadth collapses when the umbrellas are removed, the A4 "
                      "result is an artifact of one term and must be reported as such.")
_ap.add_argument("--floor_asd_a2", action="store_true",
                 help="CONSTRUCT FLOOR, ASD Criterion A2. Treat ASD.A2 exactly as the three SCZ "
                      "propositional criteria are treated: structurally unmodellable, scoring zero "
                      "on both breadth and depth. A2 is deficits in NONVERBAL communicative "
                      "behaviour, whose examples are eye contact, body language, gestures and facial "
                      "expression. MP contains no term for any of them, the mouse-side classifier "
                      "admits zero of 1,566 scoped terms to A2, and the vocalization terms that "
                      "carry its credits are admitted to A1, a different channel. Declared a "
                      "construct floor in criterion_specs/ASD.json items[1].floor_disclosure with "
                      "four-arm evidence; this flag makes the code honour that declaration. OFF by "
                      "default so every existing output reproduces byte for byte. Adds _a2floor to "
                      "the output suffix so the two families cannot merge. See "
                      "ASD_A2_CONSTRUCT_FLOOR_2026-07-29.md.")
_ap.add_argument("--out_suffix", default=None,
                 help="defaults to _criterion or _criterion_optin")
_A = _ap.parse_args()
if _A.floor_asd_a2:
    FLOOR_CRITERIA = FLOOR_CRITERIA | {("ASD","ASD.A2")}
SUFFIX = _A.out_suffix or ("_criterion" + ("_strictonly" if _A.breadth_requires_strict else "")
                           + ("" if _A.max_anchor_desc is None else f"_umb{_A.max_anchor_desc}")
                           + ("" if _A.max_hops is None else f"_hops{_A.max_hops}")
                           + ("" if _A.max_prevalence is None else f"_prev{int(_A.max_prevalence*100)}")
                           + ("" if _A.umbrella_span is None else f"_span{_A.umbrella_span}")
                           + ("" if _A.pool == "native" else f"_{_A.pool}")
                           + ("" if _A.depth_rule == "leaf" else f"_seco{_A.seco_t:g}")
                           + ("_optin" if _A.include_provisional else "")
                           + ("_a2floor" if _A.floor_asd_a2 else "")
                           + ("" if _A.require_mouse_agreement == "none"
                              else "_m" + _A.require_mouse_agreement))

_n_umb = 0; _umb_terms = {}; _n_hops_dropped = 0
def hops_to(mp, anchors):
    lvl={canon(mp)}; seen=set(lvl); d=0
    while lvl and d < 25:
        if lvl & anchors: return d
        nxt=set()
        for n in lvl:
            for p in parents.get(n,()):
                if p not in seen: seen.add(p); nxt.add(p)
        lvl=nxt; d+=1
    return 99
crit={}; _prov=set(); _missing=[]; _mouse={}
for _d in RERANK:
    _tu = P(BASE, f"target_units_{_d}", "03_target_criterion_units.tsv")
    if not os.path.exists(_tu):
        _missing.append(_d); continue
    _spec = P(BASE, "criterion_specs", f"{_d}.json")
    if os.path.exists(_spec):
        for _u in (json.load(open(_spec, encoding="utf-8")).get("provisional_units") or []):
            _prov.add((_d, f"{_d}.{_u}"))
    _tx = P(BASE, f"mp_term_taxonomy_criterion_v1_{_d}", "03_mp_term_taxonomy.tsv")
    if os.path.exists(_tx):
        for r in csv.DictReader(open(_tx, encoding="utf-8"), delimiter="\t"):
            _u2 = (r.get("criterion_unit") or "").strip()
            if _u2:
                _mouse[(_d, r["mp_id"])] = f"{_d}.{_u2}"
    for r in csv.DictReader(open(_tu, encoding="utf-8"), delimiter="\t"):
        _u = (r.get("item_id") or "none").strip()
        if _u == "none" or str(r.get("attributable","")).strip().lower() not in ("true","1"):
            continue
        crit[(_d, r["hpo_id"])] = (f"{_d}.{_u}", "symptom")
if _missing:
    print("WARN no target decomposition for:", ",".join(_missing),
          "-> those disorders contribute nothing. Run decompose_targets_to_criterion_units.py.")
if _prov:
    print(("counting" if _A.include_provisional else "EXCLUDING") + " provisional units:",
          ", ".join(sorted(c for _, c in _prov)))

matches=[]
_n_drop_norule=0; _n_drop_other=0
n_inj=0; n_base=0; n_inj_dropped=0
for d,rr in RERANK.items():
    fp=P(BASE,rr,"03_reranked_pairs_filled.tsv")
    if not os.path.exists(fp): print("WARN missing",fp); continue
    recs=list(csv.DictReader(open(fp),delimiter="\t"))
    base_acc=collections.defaultdict(set)
    for r in recs:
        if not (r.get("strict_eligible","")=="True" or r.get("broad_eligible","")=="True"): continue
        isinj=("inject" in str(r.get("retrieval_channels",""))) or (r.get("matched_domain","")=="injected")
        if not isinj: base_acc[r.get("hpo_id","")].add(canon(r.get("mp_id","")))
    for r in recs:
        se=r.get("strict_eligible","")=="True"; be=r.get("broad_eligible","")=="True"
        if _A.breadth_requires_strict:
            if not se: continue
        elif not (se or be): continue
        cr=crit.get((d,r.get("hpo_id","")))
        if not cr: continue
        cid,role=cr
        if role not in SCORED: continue
        if (d,cid) in FLOOR_CRITERIA: continue
        if (not _A.include_provisional) and (d,cid) in _prov: continue
        if _A.require_mouse_agreement != "none":
            _mu = _mouse.get((d, canon(r["mp_id"])))
            if _mu is None:
                _n_drop_norule += 1; continue
            if _A.require_mouse_agreement == "same" and _mu != cid:
                _n_drop_other += 1; continue
        mp=canon(r["mp_id"])
        inj=("inject" in str(r.get("retrieval_channels",""))) or (r.get("matched_domain","")=="injected")
        if inj:
            _anchors = base_acc.get(r.get("hpo_id",""), set())
            if not (anc(mp) & _anchors):
                n_inj_dropped+=1; continue
            if _A.max_hops is not None and hops_to(mp, _anchors) > _A.max_hops:
                _n_hops_dropped += 1; continue
            n_inj+=1
        else:
            n_base+=1
        if _A.max_anchor_desc is not None and len(desc(mp)) > _A.max_anchor_desc:
            _n_umb += 1; _umb_terms[(d, mp)] = len(desc(mp)); continue
        matches.append((d,cid,mp,se,"INJ" if inj else "BASE"))
print(f"mouse-agreement gate = {_A.require_mouse_agreement}: dropped {_n_drop_norule} "
      f"(mouse term admitted to no unit), {_n_drop_other} (mouse term names a different unit)")
if _A.max_hops is not None:
    print(f"drift cap at {_A.max_hops} hops: dropped {_n_hops_dropped} injected matches")
if _A.max_anchor_desc is not None:
    print(f"umbrella filter at >{_A.max_anchor_desc} descendants: dropped {_n_umb} matches "
          f"over {len(_umb_terms)} distinct (disorder, term) pairs")
    for (d_, mp_), nd_ in sorted(_umb_terms.items(), key=lambda kv: -kv[1])[:8]:
        print(f"    {d_:4s} {mp_} desc={nd_}")
print(f"accepted scored matches: base={n_base} injected(kept)={n_inj} injected(dropped by anchoring)={n_inj_dropped}  (ontology terms N={N})")

with open(P(CAT,f"match_export{SUFFIX}.tsv"),"w") as o:
    o.write("disorder\tcid\tmp\tstrict\tseco\thi\tsource\n")
    for d,cid,mp,st,src in matches:
        o.write(f"{d}\t{cid}\t{mp}\t{st}\t{seco(mp):.3f}\t{hi(mp)}\t{src}\n")

if _A.pool == "native":
    fv={(r["disorder"],r["genotype_id"]):r for r in csv.DictReader(open(P(CAT,"genotype_face_validity_v2.tsv")),delimiter="\t") if r["disorder"] in RERANK}
else:
    _K4=set(); 
    for _r in csv.DictReader(open(P(BASE,"broad_benchmark_setup","01_all_genotype_summary.csv"))):
        try:
            if int(_r["n_mp_terms"])>=4: _K4.add(_r["genotype_id"])
        except (TypeError,ValueError): pass
    _LBL={"ASD":("broad_benchmark_setup/01_all_genotype_summary.csv","ASD_primary"),
          "SCZ":("benchmark_tables_per_tier/SCZ_tier_0.csv","SCZ_primary"),
          "ID":("benchmark_tables_per_tier/IntellectualDisability_tier_0.csv","IntellectualDisability_primary"),
          "NCD":("benchmark_tables_per_tier/SCZ_tier_0.csv","Neurocognitive_primary")}
    fv={}
    for _d in RERANK:
        _f,_grp=_LBL[_d]
        _pos={_r["genotype_id"] for _r in csv.DictReader(open(P(BASE,_f))) if _r.get("benchmark_group")==_grp}
        for _g in _K4:
            fv[(_d,_g)]={"disorder":_d,"genotype_id":_g,"label":"1" if _g in _pos else "0",
                         "rank":"","score":""}
    print(f"pool=k4: one universe of {len(_K4)} genotypes scored for each of {len(RERANK)} disorders; "
          f"positives " + ", ".join(f"{_d} {sum(1 for (dd,gg),v in fv.items() if dd==_d and v['label']=='1')}" for _d in RERANK))
powered=set(g for (d,g) in fv)
ann=collections.defaultdict(set); gene={}
for line in open(P(BASE,"MGI_PhenoGenoMP.rpt"),encoding="utf-8",errors="ignore"):
    f=line.rstrip("\n").split("\t")
    if len(f)>=7 and f[6] in powered:
        ann[f[6]].add(canon(f[3]))
        if f[6] not in gene: gene[f[6]]=f[0].split("<")[0].split("/")[0].strip()

if _A.max_prevalence is not None:
    _mp2g=collections.defaultdict(set)
    for _g,_ms in ann.items():
        for _m in _ms: _mp2g[_m].add(_g)
    _poolsz=collections.Counter(d_ for (d_,g_) in fv)
    _keep=[]; _dropped={}
    for _t in matches:
        d_,cid_,mp_,st_,src_=_t
        _cov=set()
        for _x in desc(mp_)|{mp_}: _cov |= _mp2g.get(_x,set())
        _pv=len(_cov)/max(1,_poolsz.get(d_,1))
        _span = len({_mouse[(d_,_x)] for _x in desc(mp_)|{mp_} if (d_,_x) in _mouse})
        _generic = (_A.umbrella_span is None) or (_span > _A.umbrella_span)
        if _pv > _A.max_prevalence and _generic:
            _dropped[(d_,cid_,mp_)]=(_pv,_span)
        else:
            _keep.append(_t)
    _rule = (f"prevalence >{_A.max_prevalence:.0%} of the pool"
             + (f" AND subtree spanning >{_A.umbrella_span} criterion units"
                if _A.umbrella_span is not None else ""))
    print(f"umbrella filter [{_rule}]: dropped {len(matches)-len(_keep)} of {len(matches)} "
          f"matches over {len(_dropped)} distinct (disorder, criterion, term) triples")
    for (d_,cid_,mp_),(_pv,_sp) in sorted(_dropped.items(), key=lambda kv:-kv[1][0])[:10]:
        print(f"    {d_:4s} {cid_:8s} {mp_} prevalence {_pv:5.1%}  spans {_sp} criterion units")
    matches=_keep

sat=collections.defaultdict(lambda:[set(),set()])
for d,cid,mp,st,src in matches:
    A = st and hi(mp)
    for dmp in desc(mp)|{mp}:
        sat[(d,dmp)][0].add(cid)
        if A: sat[(d,dmp)][1].add(cid)

dist=collections.defaultdict(list)
with open(P(CAT,f"genotype_face_validity_seco{SUFFIX}.tsv"),"w") as o:
    o.write("disorder\tgenotype_id\tgene\tprimary\trank\tscore\tbreadth\tdepth\tbreadth_crit\tdepth_crit\n")
    for (d,g),r in fv.items():
        B=set(); D=set()
        for mp in ann.get(g,()):
            s=sat.get((d,mp))
            if s: B|=s[0]; D|=s[1]
        o.write("\t".join(str(x) for x in (d,g,gene.get(g,"?"),r.get("label",""),r.get("rank",""),
                r.get("score",""),len(B),len(D),";".join(sorted(B)),";".join(sorted(D))))+"\n")
        dist[d].append(len(D))
print(f"depth rule = {_A.depth_rule}" + ("" if _A.depth_rule=="leaf" else f" (Seco >= {_A.seco_t:g})") + f", breadth_requires_strict={_A.breadth_requires_strict}, out suffix {SUFFIX}:")
for d in ("ASD","SCZ","ID","NCD"):
    c=collections.Counter(dist[d]); print(f"  {d}: depth>=1 {sum(1 for x in dist[d] if x>=1)}  max {max(dist[d]) if dist[d] else 0}  dist {dict(sorted(c.items()))}")
