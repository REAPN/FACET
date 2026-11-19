import csv, re, collections
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import rankdata
csv.field_size_limit(10**9)
U = Path(__import__("os").environ.get("FACET_ROOT", "."))
B = U / "benchmark"
GOLD = {
 "ASD": ("A1prime", "run_2026-07-28_criterion_v1_asd_poloff_strict", "run_2026-09-10_fullpool_asd_poloff_strict", "_pilot_asd_2026", "ASD"),
 "SCZ": ("A2", "run_2026-07-28_criterion_v1_scz_poloff_strict", "run_2026-09-10_fullpool_scz_poloff_strict", "_pilot_scz_2026", "SCZ"),
 "IDD": ("A2", "run_2026-09-10_topup_intellectualdisability_poloff_strict", "run_2026-09-10_fullpool_idd_poloff_strict_topup", "_pilot_id_2026", "ID"),
 "NCD": ("A2", "run_2026-07-28_criterion_v1_neurocognitive_cf_poloff_strict", "run_2026-09-10_fullpool_ncd_poloff_strict", "_pilot_ncd_2026", "NCD"),
}
CANON = {"ASD": (0.9552, 0.9667), "SCZ": (0.6995, 0.7267), "IDD": (0.7332, 0.7408), "NCD": (0.6607, 0.7205)}

def auc(y, s):
    r = rankdata(s); n1 = y.sum(); n0 = len(y) - n1
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)

def load_gold(run, contrast):
    g = pd.read_csv(B / run / "paired/08_score_pair_diffs.tsv", sep="\t", dtype={"n_mp_threshold": str})
    g = g[(g.contrast == contrast) & (g.n_mp_threshold == "4")].copy()
    g["label"] = g.label.astype(int)
    return g.reset_index(drop=True)

def load_arm3(pilot):
    p = pd.read_csv(U / pilot / "baseline_scores/01_baseline_genotype_scores__B1_phenodigm_arm3_2026.tsv", sep="\t")
    return p.set_index("genotype_id")["bma_score"]

DRIVER = re.compile(r"cre|rtTA|tTA|Flp|FLP|flp|EGFP|GFP|YFP|RFP|lacZ|LacZ|tdTomato|mCherry|Cas9|DTA|Dre|luc|Luc|tdT|GCaMP|Venus|EYFP|ERT", re.I)
MANUAL = {"Atp2b1<Tg(Thy1-CHMP2B*)1Rene>": "CHMP2B",
          "Zbtb20<Tg(PDGFB-APPSwInd)20Lms>": "APP",
          "Trib2<Tg(Thy1-Trh/APP*)2.1Ingm>": "APP",
          "2310039L15Rik<Tg(Prnp-SNCA*A53T)23Mkle>": "SNCA",
          "Khdrbs2<Tg(LRRK2*R1441G)135Cjli>": "LRRK2",
          "Nbea<Tg(GH1)240BNec>": "NBEA",
          "Maoa<Tg(H2-K1-Ifnb1)8Seif>": "MAOA"}

def _payload(construct):
    toks = [t for t in re.split(r"[-/,]", construct) if t]
    if not toks: return None
    t = re.sub(r"\*.*$", "", toks[-1])
    return t.upper() or None

def allele_gene(a):
    a = a.strip()
    if not a or a.endswith("<+>") or a in ("+", "?"): return None
    if a in MANUAL: return MANUAL[a]
    m = re.match(r"^([^<]+)<Tg\((.+)\)[^>]*>$", a)
    if m:
        return None if DRIVER.search(m.group(2)) else _payload(m.group(2))
    m = re.match(r"^Tg\((.+)\)\S*$", a)
    if m:
        return None if DRIVER.search(m.group(1)) else _payload(m.group(1))
    m = re.match(r"^Gt\(ROSA\)26Sor<(.+)>$", a)
    if m:
        if DRIVER.search(m.group(1)): return None
        inner = re.search(r"\((.+)\)", m.group(1))
        return _payload(inner.group(1)) if inner else "ROSA26:" + m.group(1)
    m = re.match(r"^([^<]+)<", a)
    if m: return m.group(1).upper()
    return a.upper()

def load_summary():
    S = {}
    for r in csv.DictReader(open(U / "broad_benchmark_setup/01_all_genotype_summary.csv", encoding="utf-8")):
        S[r["genotype_id"]] = r
    return S

def cluster_keys(S):
    key = {}; unm = 0
    for g, r in S.items():
        genes = sorted({x for x in (allele_gene(a) for a in r["allele_symbols"].split("|")) if x})
        if genes: key[g] = "+".join(genes)
        else: key[g] = "SINGLETON:" + g; unm += 1
    return key, unm

def kish(counts):
    c = np.array(list(counts)); return c.sum() ** 2 / (c ** 2).sum()

def cluster_index(clusters):
    codes, uniq = pd.factorize(pd.Series(clusters))
    order = np.argsort(codes, kind="stable"); bounds = np.searchsorted(codes[order], np.arange(len(uniq) + 1))
    members = [order[bounds[i]:bounds[i + 1]] for i in range(len(uniq))]
    return codes, members

def cluster_boot(y, scores, clusters, B=2000, seed=20261008):
    rng = np.random.default_rng(seed)
    codes, members = cluster_index(clusters)
    K = len(members); out = {k: [] for k in scores}; drop = 0
    for _ in range(B):
        pick = rng.integers(0, K, K)
        rows = np.concatenate([members[i] for i in pick])
        yy = y[rows]
        if yy.sum() < 2 or (len(yy) - yy.sum()) < 2: drop += 1; continue
        for k, s in scores.items(): out[k].append(auc(yy, s[rows]))
    return {k: np.array(v) for k, v in out.items()}, drop

def strat_boot(y, scores, B=2000, seed=20261008):
    rng = np.random.default_rng(seed); pos = np.where(y == 1)[0]; neg = np.where(y == 0)[0]
    out = {k: [] for k in scores}
    for _ in range(B):
        rows = np.concatenate([rng.choice(pos, len(pos)), rng.choice(neg, len(neg))]); yy = y[rows]
        for k, s in scores.items(): out[k].append(auc(yy, s[rows]))
    return {k: np.array(v) for k, v in out.items()}

def pct(v): return np.percentile(v, [2.5, 97.5])
