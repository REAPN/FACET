#!/usr/bin/env python3
import sys, json, collections, csv
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / "audit/geneclust_2026-10-08"))
import common
common.U = ROOT; common.B = ROOT / "benchmark"
from common import GOLD, auc, load_gold, load_summary, cluster_keys, cluster_boot

N = {"ASD": "ASD", "SCZ": "SCZ", "IDD": "ID", "NCD": "NCD"}
RECORD_S4 = {"ASD": "asd_pvalue_broad_v3_poloff", "SCZ": "scz_pvalue_v1_poloff",
             "IDD": "intellectualdisability_pvalue_v1_topup20260910_poloff", "NCD": "neurocognitive_pvalue_v1_cf_poloff"}
OUT = ROOT / "audit/nullmirror_2026-10-27"

POSC = collections.defaultdict(set)
for r in csv.DictReader(open(ROOT / "audit/geneclust_2026-10-08/labels_corrected_2026-10-08.tsv"), delimiter="\t"):
    if r["label_corrected"] == "1":
        POSC[r["disorder"]].add(r["genotype_id"])
key, _ = cluster_keys(load_summary())


def strict_p(path):
    p = pd.read_csv(path, sep="\t")
    return p[p.analysis_mode == "strict"].set_index("genotype_id")


def main():
    out = {}; lines = ["# Mirrored permutation null: consolidated result (corrected labels, strict, K4)", "",
                       "Observed support scores are the record's in both columns. The null of record combines every candidate-passing pair per anchor by noisy-OR. The mirrored null first clusters near-duplicate pairs exactly as the Stage 3 aggregator does (same mp_id, same ancestor, token Jaccard of term text at or above 0.65), keeps the top pair per cluster and then combines. The random term sets are identical, so every difference below comes from the score function alone.", ""]
    for D, (con, h, f, _, _) in GOLD.items():
        rec = strict_p(ROOT / RECORD_S4[D] / "04_per_genotype_pvalue.tsv")
        mir_path = ROOT / f"_nullmirror/{N[D]}_s4_poloff/04_per_genotype_pvalue.tsv"
        if not mir_path.exists():
            print(f"{D}: mirrored run missing ({mir_path})"); continue
        mir = strict_p(mir_path)
        both = rec.index.intersection(mir.index)
        r = {"n_scored_record": int(len(rec)), "n_scored_mirrored": int(len(mir)), "n_common": int(len(both))}
        dp = (mir.loc[both, "neg_log10_p"] - rec.loc[both, "neg_log10_p"])
        r["genotypes_changed"] = int((dp.abs() > 1e-12).sum())
        r["changed_up"] = int((dp > 1e-12).sum()); r["changed_down"] = int((dp < -1e-12).sum())
        r["max_abs_change_neg_log10_p"] = round(float(dp.abs().max()), 4)
        r["ceiling_ties_record"] = int((rec.loc[both, "neg_log10_p"] >= 3.9999).sum())
        r["ceiling_ties_mirrored"] = int((mir.loc[both, "neg_log10_p"] >= 3.9999).sum())
        obs_same = np.allclose(rec.loc[both, "observed_score"].to_numpy(), mir.loc[both, "observed_score"].to_numpy(), atol=1e-12)
        r["observed_scores_identical"] = bool(obs_same)
        for pool, run in (("headline", h), ("full_pool", f)):
            g = load_gold(run, con); y = g.genotype_id.isin(POSC[D]).astype(int).to_numpy()
            cl = g.genotype_id.map(key).fillna("SINGLETON:x").to_numpy()
            S = {"record": g.score_a.to_numpy(), "mirrored": g.genotype_id.map(mir["neg_log10_p"]).fillna(0).to_numpy()}
            draws, drop = cluster_boot(y, S, cl, 2000, 20261008)
            d = draws["mirrored"] - draws["record"]
            r[pool] = {"n": int(len(y)), "n_pos": int(y.sum()), "dropped": drop,
                       "auroc_record": round(auc(y, S["record"]), 4), "auroc_mirrored": round(auc(y, S["mirrored"]), 4),
                       "diff": round(auc(y, S["mirrored"]) - auc(y, S["record"]), 4),
                       "ci90": [round(v, 4) for v in np.percentile(d, [5, 95])],
                       "ci95": [round(v, 4) for v in np.percentile(d, [2.5, 97.5])]}
        nr = pd.read_csv(ROOT / RECORD_S4[D] / "03_null_distribution_per_depth.tsv", sep="\t")
        nm = pd.read_csv(ROOT / f"_nullmirror/{N[D]}_s4_poloff/03_null_distribution_per_depth.tsv", sep="\t")
        nr = nr[nr.analysis_mode == "strict"].set_index("depth_k"); nm = nm[nm.analysis_mode == "strict"].set_index("depth_k")
        dd = (nm["null_mean"] - nr["null_mean"]).dropna()
        r["null_mean_shift"] = {"mean": round(float(dd.mean()), 6), "min": round(float(dd.min()), 6), "max": round(float(dd.max()), 6),
                                "depths_with_any_shift": int((dd.abs() > 1e-12).sum()), "depths": int(len(dd))}
        out[D] = r
        hd, fp = r["headline"], r["full_pool"]
        lines += [f"## {D}",
                  f"| universe | n (positives) | discrimination AUROC, null of record | discrimination AUROC, mirrored null | difference (90 percent interval) |",
                  "|---|---|---|---|---|",
                  f"| headline | {hd['n']} ({hd['n_pos']}) | {hd['auroc_record']:.4f} | {hd['auroc_mirrored']:.4f} | {hd['diff']:+.4f} ({hd['ci90'][0]:+.4f} to {hd['ci90'][1]:+.4f}) |",
                  f"| full pool | {fp['n']} ({fp['n_pos']}) | {fp['auroc_record']:.4f} | {fp['auroc_mirrored']:.4f} | {fp['diff']:+.4f} ({fp['ci90'][0]:+.4f} to {fp['ci90'][1]:+.4f}) |",
                  f"Genotypes whose p value changed: {r['genotypes_changed']} of {r['n_common']} (up {r['changed_up']}, down {r['changed_down']}, largest change in neg log10 p {r['max_abs_change_neg_log10_p']}). "
                  f"Ceiling ties: {r['ceiling_ties_record']} under the null of record, {r['ceiling_ties_mirrored']} under the mirrored null. "
                  f"Null mean shift over depths: mean {r['null_mean_shift']['mean']}, range {r['null_mean_shift']['min']} to {r['null_mean_shift']['max']}, "
                  f"{r['null_mean_shift']['depths_with_any_shift']} of {r['null_mean_shift']['depths']} depths differ. Observed scores identical: {r['observed_scores_identical']}.", ""]
        print(D, json.dumps(r), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "RESULT_nullmirror.json").write_text(json.dumps(out, indent=1))
    (OUT / "RESULT_nullmirror.md").write_text("\n".join(lines))
    print("wrote", OUT / "RESULT_nullmirror.md")


if __name__ == "__main__":
    main()
