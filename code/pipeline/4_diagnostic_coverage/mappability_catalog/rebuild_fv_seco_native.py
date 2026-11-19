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
def hi(mp): return seco(mp)>=SECO_T

crit={}
for r in csv.DictReader(open(P(CAT,"catalog_by_phenotype.tsv")),delimiter="\t"):
    crit[(r["disorder"],r["hpo_id"])]=(r["criterion_id"],r["role"])

matches=[]
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
        if not (se or be): continue
        cr=crit.get((d,r.get("hpo_id","")))
        if not cr: continue
        cid,role=cr
        if role not in SCORED: continue
        if (d,cid) in FLOOR_CRITERIA: continue
        mp=canon(r["mp_id"])
        inj=("inject" in str(r.get("retrieval_channels",""))) or (r.get("matched_domain","")=="injected")
        if inj:
            if not (anc(mp) & base_acc.get(r.get("hpo_id",""), set())):
                n_inj_dropped+=1; continue
            n_inj+=1
        else:
            n_base+=1
        matches.append((d,cid,mp,se,"INJ" if inj else "BASE"))
print(f"accepted scored matches: base={n_base} injected(kept)={n_inj} injected(dropped by anchoring)={n_inj_dropped}  (ontology terms N={N})")

with open(P(CAT,"match_export_native.tsv"),"w") as o:
    o.write("disorder\tcid\tmp\tstrict\tseco\thi\tsource\n")
    for d,cid,mp,st,src in matches:
        o.write(f"{d}\t{cid}\t{mp}\t{st}\t{seco(mp):.3f}\t{hi(mp)}\t{src}\n")

fv={(r["disorder"],r["genotype_id"]):r for r in csv.DictReader(open(P(CAT,"genotype_face_validity_v2.tsv")),delimiter="\t") if r["disorder"] in RERANK}
powered=set(g for (d,g) in fv)
ann=collections.defaultdict(set); gene={}
for line in open(P(BASE,"MGI_PhenoGenoMP.rpt"),encoding="utf-8",errors="ignore"):
    f=line.rstrip("\n").split("\t")
    if len(f)>=7 and f[6] in powered:
        ann[f[6]].add(canon(f[3]))
        if f[6] not in gene: gene[f[6]]=f[0].split("<")[0].split("/")[0].strip()

sat=collections.defaultdict(lambda:[set(),set()])
for d,cid,mp,st,src in matches:
    A = st and hi(mp)
    for dmp in desc(mp)|{mp}:
        sat[(d,dmp)][0].add(cid)
        if A: sat[(d,dmp)][1].add(cid)

dist=collections.defaultdict(list)
with open(P(CAT,"genotype_face_validity_seco_v2.tsv"),"w") as o:
    o.write("disorder\tgenotype_id\tgene\tprimary\trank\tscore\tbreadth\tdepth\tbreadth_crit\tdepth_crit\n")
    for (d,g),r in fv.items():
        B=set(); D=set()
        for mp in ann.get(g,()):
            s=sat.get((d,mp))
            if s: B|=s[0]; D|=s[1]
        o.write("\t".join(str(x) for x in (d,g,gene.get(g,"?"),r.get("label",""),r.get("rank",""),
                r.get("score",""),len(B),len(D),";".join(sorted(B)),";".join(sorted(D))))+"\n")
        dist[d].append(len(D))
print("depth (Seco>=0.85):")
for d in ("ASD","SCZ","ID","NCD"):
    c=collections.Counter(dist[d]); print(f"  {d}: depth>=1 {sum(1 for x in dist[d] if x>=1)}  max {max(dist[d]) if dist[d] else 0}  dist {dict(sorted(c.items()))}")
