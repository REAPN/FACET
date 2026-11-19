#!/usr/bin/env python3
"""compare_methods_paired.py
=========================

Usage example
-------------
    python compare_methods_paired.py         --metrics_file benchmark/metrics/03_metrics_per_contrast.tsv         --ranks_file   benchmark/metrics/06_per_genotype_ranks.tsv         --score_file new_pipeline::asd_batch4_ranked_broad/07_recommended_ranking.tsv::recommended_score         --score_file B1_phenodigm_plain::benchmark/baseline_scores/01_baseline_genotype_scores__B1_phenodigm_plain.tsv::bma_score         --score_file B2_phenodigm_ic::benchmark/baseline_scores/01_baseline_genotype_scores__B2_phenodigm_ic.tsv::bma_score         --labels_file broad_benchmark_setup/06_benchmark_group_table.csv         --outdir benchmark/paired         --pair new_pipeline:B1_phenodigm_plain         --pair new_pipeline:B2_phenodigm_ic         --pair B1_phenodigm_plain:B2_phenodigm_ic         --n_bootstrap 1000         --n_permutations 10000         --seed 1
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from safe_write_util import safe_write_csv
from scipy.stats import wilcoxon
from sklearn.metrics import average_precision_score, roc_auc_score

DEFAULT_SCORE_COLS = (
    "recommended_score",
    "rank_score",
    "overall_support_score_mean",
    "bma_score",
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("paired_compare")


def parse_score_spec(s: str) -> tuple[str, Path, Optional[str]]:
    parts = s.split("::")
    if len(parts) == 2:
        return parts[0], Path(parts[1]), None
    if len(parts) == 3:
        return parts[0], Path(parts[1]), parts[2]
    raise ValueError(f"--score_file must be 'label::path[::col]', got: {s}")


def load_score_file(label: str, path: Path, score_col: Optional[str]) -> pd.DataFrame:
    sep = "," if path.suffix.lower() == ".csv" else "\t"
    df = pd.read_csv(path, sep=sep, low_memory=False)
    if "genotype_id" not in df.columns:
        raise ValueError(f"{path} missing 'genotype_id'")
    col = score_col or next((c for c in DEFAULT_SCORE_COLS if c in df.columns), None)
    if col is None:
        raise ValueError(f"Could not detect score column in {path}")
    out = df[["genotype_id", col]].rename(columns={col: "score"}).copy()
    out["genotype_id"] = out["genotype_id"].astype(str).str.strip()
    out["method"] = label
    out = out.dropna(subset=["score"]).drop_duplicates(subset=["genotype_id"])
    return out


def load_labels(path: Path) -> pd.DataFrame:
    sep = "," if path.suffix.lower() == ".csv" else "\t"
    df = pd.read_csv(path, sep=sep, low_memory=False)
    df = df[["genotype_id", "benchmark_group"]].copy()
    df["genotype_id"] = df["genotype_id"].astype(str).str.strip()
    df["benchmark_group"] = df["benchmark_group"].astype(str).str.strip()
    return df.drop_duplicates(subset=["genotype_id"])

def load_n_mp_per_genotype(path: Path) -> dict[str, int]:
    sep = "," if path.suffix.lower() == ".csv" else "\t"
    df = pd.read_csv(path, sep=sep, low_memory=False)
    if "n_mp_terms" in df.columns and "genotype_id" in df.columns:
        if "analysis_mode" in df.columns:
            df = df[df["analysis_mode"] == "strict"].copy()
        df = df.dropna(subset=["genotype_id", "n_mp_terms"])
        df["genotype_id"] = df["genotype_id"].astype(str).str.strip()
        df = df.drop_duplicates(subset=["genotype_id"])
        out = dict(zip(df["genotype_id"], df["n_mp_terms"].astype(int)))
    elif "genotype_id" in df.columns:
        s = df["genotype_id"].astype(str).str.strip().value_counts()
        out = s.astype(int).to_dict()
    else:
        raise ValueError(
            f"n_mp_terms file {path} has neither 'genotype_id'+'n_mp_terms' "
            f"columns nor a 'genotype_id' column. Found: {list(df.columns)[:20]}"
        )
    log.info("Loaded n_mp_terms for %d genotypes from %s", len(out), path.name)
    return out


def parse_n_mp_thresholds(arg: str) -> list[int]:
    if not arg:
        return [1]
    parts = [p.strip() for p in str(arg).split(",") if p.strip()]
    return sorted({int(p) for p in parts} | {1})


DEFAULT_ASD_CONTRASTS: dict[str, dict] = {
    "A1_headline_psychiatric_non_ASD": dict(
        positive=["ASD_primary"],
        negative=["NDD_non_ASD", "psychiatric_non_NDD_non_ASD",
                  "language_social_confound_non_ASD"]),
    "A1prime_all_non_ASD": dict(
        positive=["ASD_primary"],
        negative=["NDD_non_ASD", "psychiatric_non_NDD_non_ASD",
                  "language_social_confound_non_ASD", "broad_other"]),
    "A3_NDD_only": dict(positive=["ASD_primary"], negative=["NDD_non_ASD"]),
    "A4_psychiatric_only": dict(positive=["ASD_primary"],
                                 negative=["psychiatric_non_NDD_non_ASD"]),
    "A5_language_confound": dict(positive=["ASD_primary"],
                                  negative=["language_social_confound_non_ASD"]),
    "S1_mixed_vs_primary": dict(positive=["ASD_mixed"], negative=["ASD_primary"]),
    "S2_pooled_ASD_vs_psych": dict(
        positive=["ASD_primary", "ASD_mixed"],
        negative=["NDD_non_ASD", "psychiatric_non_NDD_non_ASD",
                  "language_social_confound_non_ASD"]),
}


def _expand_token(negs, labels_df):
    out = []
    bg_universe = set(labels_df["benchmark_group"].dropna().astype(str).unique())
    for n in negs:
        m = re.fullmatch(r"__all_non_([A-Za-z0-9_]+)__", n)
        if m:
            target_bg = m.group(1)
            expanded = sorted(bg_universe - {target_bg})
            out.extend(expanded)
        else:
            out.append(n)
    seen = set(); uniq = []
    for x in out:
        if x not in seen:
            seen.add(x); uniq.append(x)
    return uniq


def load_contrasts_from_config(contrasts_json_arg, labels_df):
    import json as _json
    text = None
    p = Path(contrasts_json_arg) if contrasts_json_arg else None
    if p is not None and p.exists():
        text = p.read_text(encoding="utf-8")
    elif contrasts_json_arg and contrasts_json_arg.strip().startswith("["):
        text = contrasts_json_arg
    elif contrasts_json_arg and contrasts_json_arg.strip().startswith("{"):
        text = contrasts_json_arg
    else:
        raise ValueError(
            f"--contrasts_json: not a file path and not a JSON string: "
            f"{contrasts_json_arg!r}"
        )
    raw = _json.loads(text)
    if isinstance(raw, dict) and "contrasts" in raw:
        raw = raw["contrasts"]
    if not isinstance(raw, list):
        raise ValueError("contrasts must be a list (or a dict with 'contrasts' list)")
    out = {}
    for c in raw:
        cid = c.get("name") or c.get("id")
        if not cid:
            continue
        pos = c.get("positive") or c.get("positive_group")
        if isinstance(pos, str):
            pos = [pos]
        negs = c.get("negative") or c.get("negative_groups") or []
        if isinstance(negs, str):
            negs = [negs]
        negs_expanded = _expand_token(negs, labels_df)
        out[cid] = {
            "description":  c.get("description", ""),
            "positive":     pos,
            "negative":     negs_expanded,
            "expected_direction": c.get("expected_direction", ">0.5"),
            "is_specificity_sanity_check":
                c.get("is_specificity_sanity_check", False),
        }
    return out


def _ranks_higher_is_better(scores: np.ndarray) -> np.ndarray:
    return pd.Series(scores).rank(method="average", ascending=False).to_numpy()


def metric_value(name: str, scores: np.ndarray, labels: np.ndarray) -> float:
    if labels.sum() == 0 or labels.sum() == len(labels):
        return float("nan")
    if name == "auroc":
        return float(roc_auc_score(labels, scores))
    if name == "auprc":
        return float(average_precision_score(labels, scores))
    if name == "mrr":
        ranks = _ranks_higher_is_better(scores)
        return float(np.mean(1.0 / ranks[labels == 1]))
    if name.startswith("hit@"):
        k = int(name.split("@")[1])
        ranks = _ranks_higher_is_better(scores)
        return float(np.mean(ranks[labels == 1] <= k))
    raise ValueError(f"Unknown metric: {name}")


METRICS_FOR_PAIRED = ("auroc", "auprc", "mrr", "hit@10", "hit@50", "hit@100")


def _compute_midrank(x: np.ndarray) -> np.ndarray:
    J = np.argsort(x)
    Z = x[J]
    N = len(x)
    T = np.zeros(N, dtype=float)
    i = 0
    while i < N:
        j = i
        while j < N and Z[j] == Z[i]:
            j += 1
        T[i:j] = 0.5 * (i + j - 1) + 1
        i = j
    T2 = np.empty(N, dtype=float)
    T2[J] = T
    return T2


def delong_paired_auc_test(
    labels: np.ndarray, scores_a: np.ndarray, scores_b: np.ndarray
) -> tuple[float, float, float]:
    labels = np.asarray(labels, dtype=int)
    pos = labels == 1
    neg = ~pos
    m, n = pos.sum(), neg.sum()
    if m == 0 or n == 0:
        return float("nan"), float("nan"), float("nan")

    aucs = []
    v01 = []
    v10 = []
    for s in (scores_a, scores_b):
        s = np.asarray(s, dtype=float)
        tx = _compute_midrank(s[pos])
        ty = _compute_midrank(s[neg])
        tz = _compute_midrank(s)
        auc = (tz[pos].sum() / (m * n)) - (m + 1) / (2 * n)
        aucs.append(auc)
        v01.append((tz[pos] - tx) / n)
        v10.append(1.0 - (tz[neg] - ty) / m)

    aucs = np.array(aucs)
    v01 = np.vstack(v01)
    v10 = np.vstack(v10)
    sx = np.cov(v01, ddof=1)
    sy = np.cov(v10, ddof=1)
    s = sx / m + sy / n
    diff = aucs[0] - aucs[1]
    var_diff = s[0, 0] + s[1, 1] - 2 * s[0, 1]
    if var_diff <= 0:
        return float(aucs[0]), float(aucs[1]), float("nan")
    z = diff / np.sqrt(var_diff)
    from math import erf, sqrt
    p = 2.0 * (1.0 - 0.5 * (1 + erf(abs(z) / sqrt(2))))
    return float(aucs[0]), float(aucs[1]), float(p)


def paired_bootstrap_delta(
    labels: np.ndarray,
    scores_a: np.ndarray,
    scores_b: np.ndarray,
    metric: str,
    n_bootstrap: int,
    rng: np.random.Generator,
) -> tuple[float, float, float, float]:
    pos_idx = np.where(labels == 1)[0]
    neg_idx = np.where(labels == 0)[0]
    if len(pos_idx) == 0 or len(neg_idx) == 0:
        return float("nan"), float("nan"), float("nan"), float("nan")

    obs_a = metric_value(metric, scores_a, labels)
    obs_b = metric_value(metric, scores_b, labels)
    delta_obs = obs_a - obs_b

    deltas = []
    for _ in range(n_bootstrap):
        bp = rng.choice(pos_idx, size=len(pos_idx), replace=True)
        bn = rng.choice(neg_idx, size=len(neg_idx), replace=True)
        idx = np.concatenate([bp, bn])
        sa = scores_a[idx]
        sb = scores_b[idx]
        lb = labels[idx]
        d = metric_value(metric, sa, lb) - metric_value(metric, sb, lb)
        if not np.isnan(d):
            deltas.append(d)
    if not deltas:
        return delta_obs, float("nan"), float("nan"), float("nan")
    deltas = np.array(deltas)
    lo = float(np.percentile(deltas, 2.5))
    hi = float(np.percentile(deltas, 97.5))
    p = 2.0 * min(np.mean(deltas <= 0), np.mean(deltas >= 0))
    return delta_obs, lo, hi, float(p)


def paired_permutation_rrank_diff(
    labels: np.ndarray,
    scores_a: np.ndarray,
    scores_b: np.ndarray,
    n_permutations: int,
    rng: np.random.Generator,
) -> tuple[float, float]:
    if labels.sum() == 0:
        return float("nan"), float("nan")
    rA = _ranks_higher_is_better(scores_a)
    rB = _ranks_higher_is_better(scores_b)
    rrA = 1.0 / rA[labels == 1]
    rrB = 1.0 / rB[labels == 1]
    diff = rrA - rrB
    obs = float(np.mean(diff))
    n = len(diff)
    null = np.empty(n_permutations)
    for i in range(n_permutations):
        signs = rng.integers(0, 2, size=n) * 2 - 1
        null[i] = float(np.mean(signs * diff))
    p = float(np.mean(np.abs(null) >= abs(obs)))
    return obs, p


def evaluate_pair(
    contrast_id: str,
    contrast_def: dict,
    method_a: str,
    method_b: str,
    scores_by_method: dict,
    labels: pd.DataFrame,
    n_bootstrap: int,
    n_permutations: int,
    rng: np.random.Generator,
    n_mp_threshold: int = 1,
    n_mp_by_geno: Optional[dict] = None,
):
    pos_groups = set(contrast_def["positive"])
    neg_groups = set(contrast_def["negative"])
    pos_genos = set(labels[labels["benchmark_group"].isin(pos_groups)]["genotype_id"])
    neg_genos = set(labels[labels["benchmark_group"].isin(neg_groups)]["genotype_id"])
    keep = pos_genos | neg_genos

    a = scores_by_method[method_a]
    b = scores_by_method[method_b]
    paired = (
        a[a["genotype_id"].isin(keep)][["genotype_id", "score"]]
        .merge(
            b[b["genotype_id"].isin(keep)][["genotype_id", "score"]],
            on="genotype_id",
            suffixes=(f"_{method_a}", f"_{method_b}"),
        )
    )
    if (n_mp_threshold is not None and n_mp_threshold > 1
            and n_mp_by_geno is not None):
        eligible = {g for g, k in n_mp_by_geno.items() if k >= n_mp_threshold}
        paired = paired[paired["genotype_id"].isin(eligible)].copy()

    if paired.empty:
        log.warning(
            "No paired genotypes for %s vs %s on %s (n_mp>=%d)",
            method_a, method_b, contrast_id, n_mp_threshold,
        )
        return None, None

    paired["label"] = paired["genotype_id"].isin(pos_genos).astype(int)
    paired = paired.dropna(subset=[f"score_{method_a}", f"score_{method_b}"])

    sa = paired[f"score_{method_a}"].to_numpy()
    sb = paired[f"score_{method_b}"].to_numpy()
    lb = paired["label"].to_numpy()

    n_pos = int(lb.sum())
    n_neg = int(len(lb) - n_pos)

    rows = []
    if n_pos < 2 or n_neg < 2:
        log.warning(
            "Pair %s vs %s on %s (n_mp>=%d): n_pos=%d n_neg=%d — skipping.",
            method_a, method_b, contrast_id, n_mp_threshold, n_pos, n_neg,
        )
        return None, None
    auc_a, auc_b, p_delong = delong_paired_auc_test(lb, sa, sb)
    delta_auc, lo_auc, hi_auc, p_boot_auc = paired_bootstrap_delta(
        lb, sa, sb, "auroc", n_bootstrap, rng,
    )
    perm_obs, perm_p = paired_permutation_rrank_diff(
        lb, sa, sb, n_permutations, rng,
    )
    try:
        w_stat, p_wilcox = wilcoxon(sa, sb, zero_method="zsplit",
                                     alternative="two-sided")
        p_wilcox = float(p_wilcox)
    except Exception:
        p_wilcox = float("nan")

    rows.append(dict(
        contrast=contrast_id, n_mp_threshold=n_mp_threshold,
        method_a=method_a, method_b=method_b,
        metric="auroc", value_a=auc_a, value_b=auc_b,
        delta=delta_auc, ci_low=lo_auc, ci_high=hi_auc,
        p_paired_bootstrap=p_boot_auc, p_delong=p_delong,
        p_paired_permutation=float("nan"),
        p_paired_wilcoxon=p_wilcox,
        n_pos=n_pos, n_neg=n_neg, n_resamples=n_bootstrap,
    ))

    for metric in ("auprc", "mrr", "hit@10", "hit@50", "hit@100"):
        v_a = metric_value(metric, sa, lb)
        v_b = metric_value(metric, sb, lb)
        delta, lo, hi, p_boot = paired_bootstrap_delta(
            lb, sa, sb, metric, n_bootstrap, rng,
        )
        p_perm = perm_p if metric == "mrr" else float("nan")
        rows.append(dict(
            contrast=contrast_id, n_mp_threshold=n_mp_threshold,
            method_a=method_a, method_b=method_b,
            metric=metric, value_a=v_a, value_b=v_b,
            delta=delta, ci_low=lo, ci_high=hi,
            p_paired_bootstrap=p_boot, p_delong=float("nan"),
            p_paired_permutation=p_perm,
            p_paired_wilcoxon=float("nan"),
            n_pos=n_pos, n_neg=n_neg, n_resamples=n_bootstrap,
        ))

    metrics_df = pd.DataFrame(rows)

    diffs = paired.copy()
    diffs[f"score_{method_a}_minus_{method_b}"] = sa - sb
    diffs["rank_a"] = _ranks_higher_is_better(sa)
    diffs["rank_b"] = _ranks_higher_is_better(sb)
    diffs.insert(0, "contrast", contrast_id)
    diffs.insert(1, "n_mp_threshold", n_mp_threshold)
    diffs.insert(2, "method_a", method_a)
    diffs.insert(3, "method_b", method_b)
    diffs = diffs.rename(columns={
        f"score_{method_a}": "score_a",
        f"score_{method_b}": "score_b",
        f"score_{method_a}_minus_{method_b}": "score_a_minus_b",
    })
    return metrics_df, diffs[["contrast", "n_mp_threshold",
                                "method_a", "method_b",
                                "genotype_id", "label",
                                "score_a", "score_b", "score_a_minus_b",
                                "rank_a", "rank_b"]]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metrics_file", type=Path, required=False,
                    help="Output of compute_benchmark_metrics.py "
                         "(03_metrics_per_contrast.tsv). Optional.")
    ap.add_argument("--ranks_file", type=Path, required=False,
                    help="Output of compute_benchmark_metrics.py "
                         "(06_per_genotype_ranks.tsv). Reserved for future use.")
    ap.add_argument("--score_file", action="append", required=True,
                    help="Format: label::path[::col]. Pass once per method.")
    ap.add_argument("--labels_file", type=Path, required=True)
    ap.add_argument(
        "--contrasts_json", type=str, default=None,
        help="Path to JSON file (or inline JSON) with disorder-config "
             "contrast list. Supports __all_non_<X>_primary__ token expansion.",
    )
    ap.add_argument("--outdir", type=Path, required=True)
    ap.add_argument("--pair", action="append",
                    help="Method pair as 'A:B'. Defaults to standard set.")
    ap.add_argument("--n_bootstrap", type=int, default=1000)
    ap.add_argument("--n_permutations", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument(
        "--n_mp_thresholds", type=str, default="1,3,4,5,7,10",
        help="Comma-separated list of n_mp_terms thresholds (>=K filter). "
             "K=1 always included. Default '1,3,4,5,7,10'.",
    )
    ap.add_argument(
        "--n_mp_terms_file", type=Path, default=None,
        help="File providing n_mp_terms per genotype. Required when any "
             "threshold > 1.",
    )
    args = ap.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)

    specs = [parse_score_spec(s) for s in args.score_file]
    scores_by_method = {label: load_score_file(label, path, col)
                        for (label, path, col) in specs}
    method_labels = list(scores_by_method.keys())
    log.info("Methods: %s", method_labels)

    if args.pair:
        pair_list = []
        for p in args.pair:
            a, b = p.split(":")
            pair_list.append((a.strip(), b.strip()))
    else:
        pair_list = []
        if ("new_pipeline" in scores_by_method
                and "B1_phenodigm_plain" in scores_by_method):
            pair_list.append(("new_pipeline", "B1_phenodigm_plain"))
        if ("new_pipeline" in scores_by_method
                and "B2_phenodigm_ic" in scores_by_method):
            pair_list.append(("new_pipeline", "B2_phenodigm_ic"))
        if ("B1_phenodigm_plain" in scores_by_method
                and "B2_phenodigm_ic" in scores_by_method):
            pair_list.append(("B1_phenodigm_plain", "B2_phenodigm_ic"))
    if not pair_list:
        log.error("No valid method pairs to compare.")
        return 2

    labels = load_labels(args.labels_file)
    active_contrasts = (
        load_contrasts_from_config(args.contrasts_json, labels)
        if args.contrasts_json
        else DEFAULT_ASD_CONTRASTS
    )
    log.info('Using %d contrasts: %s', len(active_contrasts),
             list(active_contrasts.keys()))

    n_mp_thresholds = parse_n_mp_thresholds(args.n_mp_thresholds)
    log.info("n_mp depth-filter thresholds: %s", n_mp_thresholds)
    n_mp_by_geno = None
    if any(k > 1 for k in n_mp_thresholds):
        if args.n_mp_terms_file is None:
            raise SystemExit(
                "--n_mp_thresholds includes K > 1 but --n_mp_terms_file is "
                "not set."
            )
        n_mp_by_geno = load_n_mp_per_genotype(args.n_mp_terms_file)

    all_metrics, all_diffs = [], []
    t0 = time.time()
    for K in n_mp_thresholds:
        log.info("--- n_mp_threshold = %d ---", K)
        for method_a, method_b in pair_list:
            log.info("=== Pair: %s vs %s (K=%d) ===", method_a, method_b, K)
            for cid, cdef in active_contrasts.items():
                mdf, ddf = evaluate_pair(
                    cid, cdef, method_a, method_b,
                    scores_by_method, labels,
                    args.n_bootstrap, args.n_permutations, rng,
                    n_mp_threshold=K,
                    n_mp_by_geno=n_mp_by_geno,
                )
                if mdf is None:
                    continue
                all_metrics.append(mdf)
                all_diffs.append(ddf)

    metrics_out = args.outdir / "07_paired_method_comparison.tsv"
    safe_write_csv(pd.concat(all_metrics, ignore_index=True), metrics_out,
                   sep="\t", index=False)
    log.info("Wrote %s", metrics_out)

    diffs_out = args.outdir / "08_score_pair_diffs.tsv"
    safe_write_csv(pd.concat(all_diffs, ignore_index=True), diffs_out,
                   sep="\t", index=False)
    log.info("Wrote %s", diffs_out)

    cfg = dict(
        methods=method_labels,
        pairs=[f"{a}:{b}" for (a, b) in pair_list],
        contrasts=list(active_contrasts.keys()),
        n_bootstrap=args.n_bootstrap,
        n_permutations=args.n_permutations,
        seed=args.seed,
        n_mp_thresholds=n_mp_thresholds,
        n_mp_terms_file=(str(args.n_mp_terms_file)
                         if args.n_mp_terms_file is not None else None),
        n_mp_universe_size=(len(n_mp_by_geno)
                            if n_mp_by_geno is not None else 0),
        elapsed_seconds=round(time.time() - t0, 1),
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
    )
    (args.outdir / "99_paired_run_config.json").write_text(
        json.dumps(cfg, indent=2)
    )
    log.info("Done in %.1fs", time.time() - t0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
