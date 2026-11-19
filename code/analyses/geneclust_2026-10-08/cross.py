import json
from common import *
exec(open("landscape.py").read().split("out = {\"mp_class_definition\"")[0])
crit=lambda x:[c for c in x.split(";") if c] if x else []
res={}
g="MGI:5638914"
res["Efna2"]={D:dict(breadth=R[FVD[D]][g]["breadth"],crit=R[FVD[D]][g]["breadth_crit"],leaf=R[FVD[D]][g]["depth_crit"],
   support=round(float(SUP[D].get(g,0)),3) if D in SUP else None,
   support_pct=round(float(100*np.mean([v<=SUP[D].get(g,0) for v in SUP[D].values()])),1) if D in SUP else None,
   breadth_pct=round(float(100*np.mean([br(D,x)<=br(D,g) for x in POOL])),2)) for D in FVD}
print(res["Efna2"])
TOPB={"ASD":4,"SCZ":2,"IDD":2,"NCD":2,"MDD":3}
topF={D:{x for x in POOL if br(D,x)>=TOPB[D]} for D in FVD}
def topS(D,q=0.98):
    v=np.array([SUP[D].get(x,0) for x in POOL]); cut=np.quantile(v,q); cut=max(cut,1e-9)
    return {x for x,s in zip(POOL,v) if s>=cut}
topD={D:topS(D) for D in SUP}
bins=lambda x: 0 if nbeh(x)==0 else 1 if nbeh(x)<=2 else 2 if nbeh(x)<=5 else 3 if nbeh(x)<=10 else 4
B={x:bins(x) for x in POOL}; nb=collections.Counter(B.values())
def pairstats(T,curated_excluded=True):
    out={}
    Ds=list(T)
    for i,a in enumerate(Ds):
        for b in Ds[i+1:]:
            U=[x for x in POOL if not (curated_excluded and (x in POS[a] or x in POS[b]))]
            A={x for x in T[a] if x in set(U)}; Bb={x for x in T[b] if x in set(U)}
            obs=len(A&Bb); n=len(U)
            exp_ind=len(A)*len(Bb)/n
            e=0
            for k in range(5):
                Uk=[x for x in U if B[x]==k]
                if not Uk: continue
                pa=sum(1 for x in Uk if x in A)/len(Uk); pb=sum(1 for x in Uk if x in Bb)/len(Uk); e+=len(Uk)*pa*pb
            Ut=[x for x in U if B[x]>0]
            At={x for x in A if B[x]>0}; Bt={x for x in Bb if B[x]>0}
            out[f"{a}-{b}"]=dict(top_a=len(A),top_b=len(Bb),overlap=obs,expected_independent=round(exp_ind,1),
                ratio_independent=round(obs/exp_ind,2) if exp_ind else None,expected_behavior_stratified=round(e,1),
                ratio_stratified=round(obs/e,2) if e else None)
    return out
res["coverage_top_tier_uncurated"]=pairstats(topF)
res["support_top2pct_uncurated"]=pairstats(topD)
for k,v in res["coverage_top_tier_uncurated"].items(): print("COV",k,v)
for k,v in res["support_top2pct_uncurated"].items(): print("SUP",k,v)
cur={}
for a in FVD:
    for b in FVD:
        if a==b: continue
        P=[x for x in POOL if x in POS[a] and x not in POS[b]]
        obs=sum(1 for x in P if x in topF[b])
        bg=[x for x in POOL if x not in POS[a] and x not in POS[b]]
        rate={k:np.mean([x in topF[b] for x in bg if B[x]==k]) for k in range(5)}
        exp=sum(rate[B[x]] for x in P)
        cur[f"curated {a} in top tier of {b}"]=dict(n=len(P),observed=obs,expected_stratified=round(float(exp),1),ratio=round(obs/exp,2) if exp else None)
res["curated_cross"]=cur
for k,v in cur.items(): print(k,v)
json.dump(res,open("cross.json","w"),indent=1,default=str)
