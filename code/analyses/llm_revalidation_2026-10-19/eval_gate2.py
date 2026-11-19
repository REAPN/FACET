import sys; sys.path.insert(0, __import__("os").environ.get("FACET_ROOT", ".") + "/audit/geneclust_2026-10-08")
from common import *
POSC = collections.defaultdict(set)
for r in csv.DictReader(open(__import__("os").environ.get("FACET_ROOT", ".") + "/audit/geneclust_2026-10-08/labels_corrected_2026-10-08.tsv"), delimiter="\t"):
    if r["label_corrected"] == "1": POSC[r["disorder"]].add(r["genotype_id"])
N = {"ASD": "ASD", "SCZ": "SCZ", "IDD": "ID", "NCD": "NCD"}; EXP = {"ASD": 0.9557, "SCZ": 0.6823, "IDD": 0.7511, "NCD": 0.6638}
for D in GOLD:
    con, h, f, pil, _ = GOLD[D]; g = load_gold(h, con)
    p = pd.read_csv(U / f"_judgeswap/runs/{N[D]}_cached_s4_poloff/04_per_genotype_pvalue.tsv", sep="\t")
    p = p[p.analysis_mode == "strict"].set_index("genotype_id")["neg_log10_p"]
    s = g.genotype_id.map(p).fillna(0).to_numpy(); y = g.genotype_id.isin(POSC[D]).astype(int).to_numpy()
    a = auc(y, s); maxdiff = float(np.abs(s - g.score_a.to_numpy()).max())
    print(D, round(a, 4), "expected", EXP[D], "pass" if abs(round(a, 4) - EXP[D]) < 5e-5 else "FAIL", "max |score - record|", maxdiff)
