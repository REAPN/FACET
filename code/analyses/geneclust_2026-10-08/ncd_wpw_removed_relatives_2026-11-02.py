import os, sys, json, time, collections, csv, math
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path.cwd(); os.environ["FACET_ROOT"] = str(ROOT); SEED, B = 20261008, 2000
sys.path.insert(0, str(ROOT / "audit/geneclust_2026-10-08"))
import common; common.U = ROOT; common.B = ROOT / "benchmark"
from common import cluster_keys, load_summary, pct, load_gold, GOLD
S = load_summary(); key, _ = cluster_keys(S)
csv.field_size_limit(10**9)
par = collections.defaultdict(set); cur = None
for l in open(ROOT / "MPheno_OBO.ontology", encoding="utf-8"):
    l = l.strip()
    if l.startswith("id: MP:"): cur = l[4:]
    elif l.startswith("is_a: MP:") and cur: par[cur].add(l[6:16])
ch = collections.defaultdict(set)
for c, ps in par.items():
    for p in ps: ch[p].add(c)
beh = set(); st_ = ["MP:0004924"]
while st_:
    x = st_.pop()
    if x in beh: continue
    beh.add(x); st_.extend(ch[x])
mps = lambda g: {x.strip() for x in S[g]["mp_ids"].split("|") if x.strip()}
nbeh = {g: len(mps(g) & beh) for g in S}
BA = lambda g: nbeh[g] > 0
st = lambda g: (lambda n: 1 if n <= 2 else 2 if n <= 5 else 3 if n <= 10 else 4)(nbeh[g])
FV = ROOT / "mappability_catalog/genotype_face_validity_seco_criterion_strictonly_prev25_span1_k4_a2floor_ncdB_constructfiltered_idd20260910.tsv"
POOL = sorted({r["genotype_id"] for r in csv.DictReader(open(FV, encoding="utf-8"), delimiter="\t") if r["disorder"] == "ASD"})
cfg = {x["name"]: x for x in json.load(open(ROOT / "disorders_rescue_config.json"))["disorders"]}
dpar = collections.defaultdict(set); c_ = None
for l in open(ROOT / "audit/doid.obo", encoding="utf-8"):
    l = l.rstrip("\n")
    if l == "[Term]": c_ = None
    elif l.startswith("id: DOID:"): c_ = l[4:]
    elif l.startswith("is_a: DOID:") and c_: dpar[c_].add(l[6:].split(" ")[0])
dm = {}
def danc(t):
    if t not in dm:
        s = set()
        for p in dpar.get(t, ()): s |= {p} | danc(p)
        dm[t] = s
    return dm[t]
allt = set(dpar) | {p for v in dpar.values() for p in v}
DOIDS = set(cfg["Neurocognitive"]["doids"]) | {t for t in allt if t == "DOID:1307" or "DOID:1307" in danc(t)}
ncd_doids = DOIDS
j2p = {}
for l in open(ROOT / "MGI additional/BIB_PubMed_2026-10-13.rpt", encoding="utf-8"):
    f = l.rstrip("\n").split("\t")
    if len(f) >= 3 and f[1]: j2p[f[2]] = f[1]
claims = collections.defaultdict(lambda: collections.defaultdict(set))
for r in csv.DictReader(open(ROOT / "_overnight/parsed/disease_claims.tsv"), delimiter="\t"):
    if r["not_model"] == "1": continue
    for j in r["j_refs"].split("|"):
        if j and j in j2p: claims[r["genotype_id"]][r["doid"]].add(j2p[j])
POOLSET = set(POOL); allpm = collections.defaultdict(set)
for l in open(ROOT / "MGI_PhenoGenoMP.rpt", encoding="utf-8"):
    f = l.rstrip("\n").split("\t")
    if len(f) >= 7 and f[6] in POOLSET: allpm[f[6]] |= {p for p in f[4].split("|") if p.strip()}
def cref_of(p):
    cs = set().union(*[v for k, v in claims[p].items() if k in DOIDS]) if claims[p] else set()
    if not cs and claims[p]: cs = set().union(*claims[p].values())
    return cs
GH = {r["Symbol"].upper() for r in csv.DictReader(open(ROOT / "MGI_DO.rpt", encoding="utf-8"), delimiter="\t")
      if r["DO Disease ID"] in ncd_doids and r["Common Organism Name"].startswith("human")}
con, h, f, pil, _ = GOLD["NCD"]; g = load_gold(h, con); HU = set(g.genotype_id); sc = dict(zip(g.genotype_id, g.score_a.astype(float)))
def strat_auc_boot(pos, neg, score):
    items = list(pos) + list(neg); n = len(items)
    y = np.array([1] * len(pos) + [0] * len(neg)); s = np.array([score[x] for x in items], float)
    sta = np.array([st(x) for x in items]); cl = pd.factorize(pd.Series([key.get(x, x) for x in items]))[0]; K = cl.max() + 1
    rng = np.random.default_rng(SEED)
    W = np.vstack([np.ones(n)] + [np.bincount(rng.integers(0, K, K), minlength=K)[cl] for _ in range(B)]).astype(float)
    num = np.zeros(W.shape[0]); den = np.zeros(W.shape[0])
    for k in (1, 2, 3, 4):
        idx = np.where(sta == k)[0]
        if not ((y[idx] == 1).any() and (y[idx] == 0).any()): continue
        o = idx[np.argsort(s[idx], kind="stable")]; starts = np.r_[0, np.nonzero(np.diff(s[o]))[0] + 1]
        Wp = W[:, o] * (y[o] == 1); Wn = W[:, o] * (y[o] == 0)
        Gp = np.add.reduceat(Wp, starts, axis=1); Gn = np.add.reduceat(Wn, starts, axis=1)
        below = np.cumsum(Gn, axis=1) - Gn + 0.5 * Gn; sp, sn = Gp.sum(1), Gn.sum(1); ok = (sp > 0) & (sn > 0)
        a = np.where(ok, (Gp * below).sum(1) / np.where(ok, sp * sn, 1), 0.0)
        num += np.where(ok, sp * a, 0.0); den += np.where(ok, sp, 0.0)
    v = np.where(den > 0, num / np.where(den > 0, den, 1), np.nan)
    return v[0], v[1:]
def compare(pos, neg):
    pos, neg = sorted(pos), sorted(neg); a, dr = strat_auc_boot(pos, neg, sc); dr = dr[~np.isnan(dr)]
    se = float(np.std(dr, ddof=1)); z = (a - 0.5) / se; p = float(math.erfc(abs(z) / math.sqrt(2)))
    return dict(n=len(pos), n_background=len(neg), auroc=round(float(a), 4), ci_gene=list(np.round(pct(dr), 4)), p_approx=round(p, 4))
def run(labels):
    POS = {r["genotype_id"] for r in csv.DictReader(open(ROOT / "audit/geneclust_2026-10-08" / labels), delimiter="\t") if r["disorder"] == "NCD" and r["label_corrected"] == "1"}
    P = [x for x in POOL if x in POS]; Pset = set(P)
    posbygene = collections.defaultdict(list)
    for p in P: posbygene[key[p]].append(p)
    cur = {k for k in posbygene if not k.startswith("SINGLETON:")}
    gref = {k: set().union(*[cref_of(p) for p in v]) for k, v in posbygene.items()}
    cand = [x for x in POOL if x not in Pset and key[x] in cur and BA(x)]
    rel = [x for x in cand if not (allpm[x] & gref[key[x]])]
    bg = [x for x in POOL if BA(x) and x not in Pset and key[x] not in cur]
    hctl = [x for x in bg if any(z in GH for z in key[x].split("+"))]
    r = dict(labels=labels, positives=len(P), curated_genes=len(cur), relatives_independent=len(rel), background=len(bg), attention_control=len(hctl))
    r["relatives_vs_background"] = compare([x for x in rel if x in HU], [x for x in bg if x in HU])
    r["relatives_vs_attention_control"] = compare([x for x in rel if x in HU], [x for x in hctl if x in HU])
    print(json.dumps(r), flush=True); return r
out = {"gate_old_labels": run("labels_corrected_2026-10-08.tsv"), "new": run("labels_corrected_2026-11-02.tsv")}
assert abs(out["gate_old_labels"]["relatives_vs_background"]["auroc"] - 0.5807) < 0.0006 and abs(out["gate_old_labels"]["relatives_vs_attention_control"]["auroc"] - 0.5551) < 0.0006, "gate failed"
json.dump(out, open(ROOT / "audit/geneclust_2026-10-08/ncd_wpw_removed_relatives_2026-11-02.json", "w"), indent=1); print("gate passed")
