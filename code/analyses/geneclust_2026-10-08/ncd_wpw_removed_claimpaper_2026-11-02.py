import os, sys, json, time, collections, csv
from pathlib import Path
import numpy as np, pandas as pd
t0 = time.time()
ROOT = Path.cwd(); os.environ["FACET_ROOT"] = str(ROOT)
src = open(ROOT / "audit/vocab_removal_2026-10-08/vocab_common.py").read().replace("labels_corrected_2026-10-08.tsv", "labels_corrected_2026-11-02.tsv")
exec(src)
sys.path.insert(0, str(ROOT / "audit/geneclust_2026-10-08"))
import common; common.U = ROOT; common.B = ROOT / "benchmark"
from common import cluster_boot, cluster_keys, load_summary, pct, auc as auc2, load_gold, GOLD
d = "NCD"; print("loaded", round(time.time() - t0, 1), flush=True)
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
j2p = {}
for l in open(ROOT / "MGI additional/BIB_PubMed_2026-10-13.rpt", encoding="utf-8"):
    f = l.rstrip("\n").split("\t")
    if len(f) >= 3 and f[1]: j2p[f[2]] = f[1]
claims = collections.defaultdict(lambda: collections.defaultdict(set))
for r in csv.DictReader(open(ROOT / "_overnight/parsed/disease_claims.tsv"), delimiter="\t"):
    if r["not_model"] == "1": continue
    for j in r["j_refs"].split("|"):
        if j and j in j2p: claims[r["genotype_id"]][r["doid"]].add(j2p[j])
annref = collections.defaultdict(lambda: collections.defaultdict(set))
for l in open(ROOT / "MGI_PhenoGenoMP.rpt", encoding="utf-8"):
    f = l.rstrip("\n").split("\t")
    if len(f) >= 7 and f[6] in FVR["ASD"]:
        annref[f[6]][f[3]] |= {p for p in f[4].split("|") if p.strip()}
print("refs", round(time.time() - t0, 1), flush=True)
S = load_summary(); key, _ = cluster_keys(S)
P = [g for g in POOL if curated(d, g)]
claim_of = {}
for g in P:
    cs = set().union(*[v for k, v in claims[g].items() if k in DOIDS]) if claims[g] else set()
    if not cs and claims[g]: cs = set().union(*claims[g].values())
    claim_of[g] = cs
allref = {g: set().union(*annref[g].values()) if annref[g] else set() for g in POOL}
out = dict(positives=len(P), claim_refs_equal_all_refs=sum(allref[g] <= claim_of[g] for g in P),
           wpw_in_prior_count=[g for g in ("MGI:8187632", "MGI:8187633") if allref[g] <= (set().union(*claims[g].values()) if claims[g] else set())])
print(json.dumps(out), flush=True)
def drop_for(g):
    cs = claim_of.get(g, set()); o = set()
    for t, refs in annref[g].items():
        if refs and refs <= cs: o.add(t)
    return frozenset(o)
def bg_drop(g):
    cnt = collections.Counter(p for refs in annref[g].values() for p in refs)
    if not cnt: return frozenset()
    top = sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return frozenset(t for t, refs in annref[g].items() if refs and refs <= {top})
vB = {g: len(credits(d, g, drop_ann=drop_for(g))) for g in P}
Pset = set(P); bgs = {g: len(credits(d, g, drop_ann=bg_drop(g))) for g in POOL if g not in Pset}
print("credits", round(time.time() - t0, 1), flush=True)
y = np.array([int(g in Pset) for g in POOL]); s = np.array([vB[g] if g in Pset else bgs[g] for g in POOL], float)
cl = np.array([key.get(g, g) for g in POOL]); cd, _ = cluster_boot(y, {"f": s}, cl, 2000, 20261008)
out["convergent_after_claim_paper_removal_symmetric"] = dict(auroc=round(auc2(y, s), 4), ci_gene=list(np.round(pct(cd["f"]), 4)), positives_with_any_criterion=int(sum(vB[g] > 0 for g in P)))
t = pd.read_csv(ROOT / "_openitems/runs/NCD_item2_s4_poloff/04_per_genotype_pvalue.tsv", sep="\t"); t = t[t.analysis_mode == "strict"].drop_duplicates("genotype_id").set_index("genotype_id")["neg_log10_p"]
con, h, f, pil, _ = GOLD["NCD"]; g = load_gold(h, con); yy = g.genotype_id.isin(Pset).astype(int).to_numpy(); clh = g.genotype_id.map(key).fillna("S").to_numpy()
b = g.genotype_id.map(t).fillna(0).to_numpy(); cd2, _ = cluster_boot(yy, {"b": b}, clh, 2000, 20261008)
out["discrimination_after_claim_paper_removal"] = dict(n_pos=int(yy.sum()), auroc=round(auc2(yy, b), 4), ci_gene=list(np.round(pct(cd2["b"]), 3)))
print(json.dumps(out, indent=1)); json.dump(out, open(ROOT / "audit/geneclust_2026-10-08/ncd_wpw_removed_claimpaper_2026-11-02.json", "w"), indent=1)
print("done", round(time.time() - t0, 1))
