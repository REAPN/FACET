#!/usr/bin/env python3
import sys, json, re, csv, collections
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / "audit/geneclust_2026-10-08"))
import common
common.U = ROOT; common.B = ROOT / "benchmark"
from common import GOLD, auc, load_gold, load_arm3, load_summary, cluster_keys, cluster_boot, pct, kish
OUT = ROOT / "audit/impc_test_2026-11-07"; OUT.mkdir(exist_ok=True)
U = ROOT

S = load_summary(); key, _ = cluster_keys(S)
IMPC = re.compile(r"\((IMPC|KOMP|EUCOMM|NCOM)\)")
impc = lambda g: bool(IMPC.search(S[g]["allele_symbols"])) if g in S else False

par = collections.defaultdict(set); cur = None
for l in open(U / "MPheno_OBO.ontology", encoding="utf-8"):
    l = l.rstrip("\n")
    if l == "[Term]": cur = None
    elif l.startswith("id: MP:"): cur = l[4:]
    elif l.startswith("is_a: ") and cur: par[cur].add(l[6:16])
memo = {}
def anc(t):
    if t not in memo:
        s = set()
        for p in par.get(t, ()): s |= {p} | anc(p)
        memo[t] = s
    return memo[t]
def nbeh(g):
    return sum(1 for m in S[g]["mp_ids"].split("|") if m.strip() and (m.strip() == "MP:0004924" or "MP:0004924" in anc(m.strip())))
def stratum(g):
    n = nbeh(g); return 0 if n == 0 else 1 if n <= 2 else 2 if n <= 5 else 3 if n <= 10 else 4

V = U / "dnv_catalogs"
def col(path, c="gene_symbol"): return {r[c].upper() for r in csv.DictReader(open(path, encoding="utf-8"), delimiter="\t") if r.get(c)}
G = {"ASD": col(V / "asc_satterstrom2020_asd_genes.tsv") | col(V / "fu2022_asd_genes.tsv"),
     "SCZ": col(V / "schema_scz_gene_list.tsv") | col(V / "denovo_db_scz_genes.tsv"),
     "IDD": col(V / "ddg2p_id_confirmed_dominant.tsv")}
cfg = {d["name"]: d for d in json.load(open(U / "disorders_rescue_config.json"))["disorders"]}
ncd_doids = set(cfg["Neurocognitive"]["doids"])
G["NCD"] = {r["Symbol"].upper() for r in csv.DictReader(open(U / "MGI_DO.rpt", encoding="utf-8"), delimiter="\t")
            if r["DO Disease ID"] in ncd_doids and r["Common Organism Name"].startswith("human")}
hgene = lambda g, D: any(x in G[D] for x in key[g].split("+"))

POS = collections.defaultdict(set)
for r in csv.DictReader(open(U / "audit/geneclust_2026-10-08/labels_corrected_2026-11-02.tsv"), delimiter="\t"):
    if r["label_corrected"] == "1": POS[r["disorder"]].add(r["genotype_id"])

FV = U / "mappability_catalog/genotype_face_validity_seco_criterion_strictonly_prev25_span1_k4_a2floor_ncdB_constructfiltered_idd20260910.tsv"
COV = collections.defaultdict(dict); FVN = {"ASD": "ASD", "SCZ": "SCZ", "IDD": "ID", "NCD": "NCD"}
for r in csv.DictReader(open(FV, encoding="utf-8"), delimiter="\t"):
    COV[r["disorder"]][r["genotype_id"]] = float(r["breadth"] or 0)

def wauc(sp, kp, sn, kn):
    pc = np.bincount(kp, minlength=5) / len(kp); nc = np.bincount(kn, minlength=5)
    w = np.where(nc[kn] > 0, pc[kn] / np.maximum(nc[kn], 1), 0.0)
    if w.sum() == 0: return np.nan
    o = np.argsort(sn); sn, w = sn[o], w[o]; cw = np.concatenate([[0], np.cumsum(w)])
    lo = np.searchsorted(sn, sp, "left"); hi = np.searchsorted(sn, sp, "right")
    return float(np.mean((cw[lo] + 0.5 * (cw[hi] - cw[lo])) / cw[-1]))

def main():
    out = {}; L = ["# IMPC-only test of the support score (corrected labels, headline universe, K4)", "",
                   "Universe: IMPC-tagged genotypes of the headline universe with curated models removed. Positives: genotypes whose gene is an H gene (S5 Table). Intervals: 95% gene-clustered bootstrap, 2,000 replicates. Depth matched: background reweighted to the positives' behavioral-depth bins (0, 1 to 2, 3 to 5, 6 to 10, 11 or more), gene-clustered, 500 replicates.", "",
                   "| Disorder | IMPC genotypes | H-gene positives (genes) | Background | Support AUROC (95%) | Coverage AUROC (95%) | Behavioral count AUROC (95%) | PhenoDigm recomputed AUROC (95%) | Support minus PhenoDigm (95%, p) | Support AUROC depth matched (95%) | Behavioral count depth matched |",
                   "|---|---|---|---|---|---|---|---|---|---|---|"]
    for D, (con, h, f, pil, fvd) in GOLD.items():
        g = load_gold(h, con)
        ids = g.genotype_id.to_numpy(); sup = g.score_a.to_numpy()
        keep = np.array([impc(x) and x not in POS[D] for x in ids])
        ids, sup = ids[keep], sup[keep]
        y = np.array([int(hgene(x, D)) for x in ids]); cl = np.array([key[x] for x in ids])
        cov = np.array([COV[fvd].get(x, 0.0) for x in ids]); beh = np.array([nbeh(x) for x in ids], float)
        pdg = load_arm3(pil); phen = np.array([pdg.get(x, 0.0) for x in ids], float)
        sc = {"facet": sup, "coverage": cov, "beh": beh, "phenodigm": phen}
        r = dict(n_impc=int(len(ids)), n_pos=int(y.sum()), pos_genes=len(set(cl[y == 1])), n_bg=int((y == 0).sum()))
        if y.sum() < 5 or (y == 0).sum() < 10:
            r["note"] = "too few positives"; out[D] = r; continue
        cd, drop = cluster_boot(y, sc, cl, 2000, 20261008)
        for k in sc:
            r[f"auroc_{k}"] = round(float(auc(y, sc[k])), 4); r[f"ci_{k}"] = [round(float(v), 4) for v in pct(cd[k])]
        d = cd["facet"] - cd["phenodigm"]
        r["delta_phenodigm"] = round(r["auroc_facet"] - r["auroc_phenodigm"], 4); r["delta_phenodigm_ci"] = [round(float(v), 4) for v in pct(d)]
        r["delta_phenodigm_p"] = float(min(1.0, 2 * min((d <= 0).mean(), (d >= 0).mean())))
        kk = np.array([stratum(x) for x in ids])
        r["auroc_facet_depth_matched"] = round(wauc(sup[y == 1], kk[y == 1], sup[y == 0], kk[y == 0]), 4)
        r["auroc_beh_depth_matched"] = round(wauc(beh[y == 1], kk[y == 1], beh[y == 0], kk[y == 0]), 4)
        codes = {c: i for i, c in enumerate(sorted(set(cl)))}; members = collections.defaultdict(list)
        for i, c in enumerate(cl): members[codes[c]].append(i)
        members = [np.array(v) for v in members.values()]; rng = np.random.default_rng(20261008); dm = []
        for _ in range(500):
            rr = np.concatenate([members[i] for i in rng.integers(0, len(members), len(members))]); yy = y[rr]
            if yy.sum() < 2 or (yy == 0).sum() < 2: continue
            v = wauc(sup[rr][yy == 1], kk[rr][yy == 1], sup[rr][yy == 0], kk[rr][yy == 0])
            if np.isfinite(v): dm.append(v)
        r["ci_facet_depth_matched"] = [round(float(v), 4) for v in pct(np.array(dm))] if dm else None
        r["pos_depth_bins"] = np.bincount(kk[y == 1], minlength=5).tolist(); r["bg_depth_bins"] = np.bincount(kk[y == 0], minlength=5).tolist()
        r["share_pos_behaviorally_annotated"] = round(float((beh[y == 1] > 0).mean()), 3); r["share_bg_behaviorally_annotated"] = round(float((beh[y == 0] > 0).mean()), 3)
        out[D] = r
        f3 = lambda a, b: f"{a:.3f} ({b[0]:.3f} to {b[1]:.3f})"
        L.append(f"| {D} | {r['n_impc']} | {r['n_pos']} ({r['pos_genes']}) | {r['n_bg']} | {f3(r['auroc_facet'], r['ci_facet'])} | {f3(r['auroc_coverage'], r['ci_coverage'])} | {f3(r['auroc_beh'], r['ci_beh'])} | {f3(r['auroc_phenodigm'], r['ci_phenodigm'])} | {r['delta_phenodigm']:+.3f} ({r['delta_phenodigm_ci'][0]:+.3f} to {r['delta_phenodigm_ci'][1]:+.3f}, p {r['delta_phenodigm_p']:.3f}) | {f3(r['auroc_facet_depth_matched'], r['ci_facet_depth_matched']) if r['ci_facet_depth_matched'] else r['auroc_facet_depth_matched']} | {r['auroc_beh_depth_matched']:.3f} |")
        print(D, json.dumps(r), flush=True)
    L += ["", "Behaviorally annotated share, positives against background: " + ", ".join(f"{D} {out[D].get('share_pos_behaviorally_annotated')} against {out[D].get('share_bg_behaviorally_annotated')}" for D in out), "",
          "Positive depth bins (0, 1 to 2, 3 to 5, 6 to 10, 11 or more): " + ", ".join(f"{D} {out[D].get('pos_depth_bins')}" for D in out)]
    json.dump(out, open(OUT / "RESULT_impc.json", "w"), indent=1); (OUT / "RESULT_impc.md").write_text("\n".join(L))
    print("DONE", OUT)

if __name__ == "__main__":
    main()
