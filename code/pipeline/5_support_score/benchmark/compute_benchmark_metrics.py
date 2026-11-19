#!/usr/bin/env python3
"""compute_benchmark_metrics.py
============================

Usage example
-------------
    python compute_benchmark_metrics.py         --score_file new_pipeline::asd_batch4_ranked_broad/07_recommended_ranking.tsv::recommended_score         --score_file B1_phenodigm_plain::benchmark/baseline_scores/01_baseline_genotype_scores__B1_phenodigm_plain.tsv::bma_score         --score_file B2_phenodigm_ic::benchmark/baseline_scores/01_baseline_genotype_scores__B2_phenodigm_ic.tsv::bma_score         --labels_file broad_benchmark_setup/06_benchmark_group_table.csv         --outdir benchmark/metrics         --n_bootstrap 1000         --seed 1
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from safe_write_util import safe_write_csv
from sklearn.metrics import (
    average_precision_score,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("benchmark_metrics")


DEFAULT_ASD_CONTRASTS: dict[str, dict] = {
    "A1_headline_psychiatric_non_ASD": dict(
        description="ASD_primary vs psychiatric_non_ASD pool",
        positive=["ASD_primary"],
        negative=[
            "NDD_non_ASD",
            "psychiatric_non_NDD_non_ASD",
            "language_social_confound_non_ASD",
        ],
    ),
    "A1prime_all_non_ASD": dict(
        description="ASD_primary vs all non-ASD (excludes ASD_mixed)",
        positive=["ASD_primary"],
        negative=[
            "NDD_non_ASD",
            "psychiatric_non_NDD_non_ASD",
            "language_social_confound_non_ASD",
            "broad_other",
        ],
    ),
    "A3_NDD_only": dict(
        description="ASD_primary vs NDD_non_ASD",
        positive=["ASD_primary"],
        negative=["NDD_non_ASD"],
    ),
    "A4_psychiatric_only": dict(
        description="ASD_primary vs psychiatric_non_NDD_non_ASD",
        positive=["ASD_primary"],
        negative=["psychiatric_non_NDD_non_ASD"],
    ),
    "A5_language_confound": dict(
        description="ASD_primary vs language_social_confound_non_ASD (descriptive, small n)",
        positive=["ASD_primary"],
        negative=["language_social_confound_non_ASD"],
    ),
    "S1_mixed_vs_primary": dict(
        description="ASD_mixed vs ASD_primary (sensitivity: pure vs comorbid ASD)",
        positive=["ASD_mixed"],
        negative=["ASD_primary"],
    ),
    "S2_pooled_ASD_vs_psych": dict(
        description="{ASD_primary, ASD_mixed} pooled vs psychiatric_non_ASD",
        positive=["ASD_primary", "ASD_mixed"],
        negative=[
            "NDD_non_ASD",
            "psychiatric_non_NDD_non_ASD",
            "language_social_confound_non_ASD",
        ],
    ),
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
    from pathlib import Path as _Path
    text = None
    pp = _Path(contrasts_json_arg) if contrasts_json_arg else None
    if pp is not None and pp.exists():
        text = pp.read_text(encoding="utf-8")
    elif contrasts_json_arg and contrasts_json_arg.strip().startswith(("[", "{")):
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
        raise ValueError("contrasts must be a list (or a dict with key 'contrasts')")
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
            "description":          c.get("description", ""),
            "positive":             pos,
            "negative":             negs_expanded,
            "expected_direction":   c.get("expected_direction", ">0.5"),
            "is_specificity_sanity_check":
                c.get("is_specificity_sanity_check", False),
        }
    return out


DEFAULT_SCORE_COLS = (
    "recommended_score",
    "rank_score",
    "overall_support_score_mean",
    "bma_score",
)


@dataclass
class ScoreFileSpec:
    label: str
    path: Path
    score_col: Optional[str]


def parse_score_spec(s: str) -> ScoreFileSpec:
    parts = s.split("::")
    if len(parts) == 2:
        label, path = parts
        return ScoreFileSpec(label=label, path=Path(path), score_col=None)
    if len(parts) == 3:
        label, path, col = parts
        return ScoreFileSpec(label=label, path=Path(path), score_col=col)
    raise ValueError(
        f"--score_file must be 'label::path' or 'label::path::col', got: {s}"
    )


def load_score_file(spec: ScoreFileSpec) -> pd.DataFrame:
    sep = "," if spec.path.suffix.lower() == ".csv" else "\t"
    df = pd.read_csv(spec.path, sep=sep, low_memory=False)
    if "genotype_id" not in df.columns:
        raise ValueError(
            f"{spec.path} is missing 'genotype_id'. Columns: {list(df.columns)[:20]}"
        )
    col = spec.score_col
    if col is None:
        col = next((c for c in DEFAULT_SCORE_COLS if c in df.columns), None)
        if col is None:
            raise ValueError(
                f"Could not auto-detect score column in {spec.path}. "
                f"Tried {DEFAULT_SCORE_COLS}. Found columns: {list(df.columns)[:20]}"
            )
    out = df[["genotype_id", col]].rename(columns={col: "score"}).copy()
    out["genotype_id"] = out["genotype_id"].astype(str).str.strip()
    out["method"] = spec.label
    out["score_col_used"] = col
    out = out.dropna(subset=["score"]).drop_duplicates(subset=["genotype_id"])
    log.info("Loaded %d genotype scores for method '%s' (col=%s)",
             len(out), spec.label, col)
    return out


def load_labels(path: Path) -> pd.DataFrame:
    sep = "," if path.suffix.lower() == ".csv" else "\t"
    df = pd.read_csv(path, sep=sep, low_memory=False)
    needed = ["genotype_id", "benchmark_group"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ValueError(f"Labels file {path} is missing columns: {missing}")
    df = df[needed].copy()
    df["genotype_id"] = df["genotype_id"].astype(str).str.strip()
    df["benchmark_group"] = df["benchmark_group"].astype(str).str.strip()
    df = df.drop_duplicates(subset=["genotype_id"])
    log.info(
        "Loaded labels for %d genotypes; group counts:\n%s",
        len(df),
        df["benchmark_group"].value_counts().to_string(),
    )
    return df


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
            f"columns nor a 'genotype_id' column for groupby. "
            f"Found: {list(df.columns)[:20]}"
        )
    log.info("Loaded n_mp_terms for %d genotypes from %s "
             "(median=%d, q90=%d, max=%d)",
             len(out), path.name,
             int(np.median(list(out.values()))),
             int(np.percentile(list(out.values()), 90)),
             int(np.max(list(out.values()))))
    return out


def parse_n_mp_thresholds(arg: str) -> list[int]:
    if not arg:
        return [1]
    parts = [p.strip() for p in str(arg).split(",") if p.strip()]
    ks = sorted({int(p) for p in parts} | {1})
    return ks


def _ranks_higher_is_better(scores: np.ndarray) -> np.ndarray:
    s = pd.Series(scores)
    return s.rank(method="average", ascending=False).to_numpy()


def metric_panel(scores: np.ndarray, labels: np.ndarray) -> dict[str, float]:
    out: dict[str, float] = {}
    out["n_pos"] = int((labels == 1).sum())
    out["n_neg"] = int((labels == 0).sum())
    if out["n_pos"] == 0 or out["n_neg"] == 0:
        for k in ("auroc", "auprc", "mrr", "hit@10", "hit@50", "hit@100",
                  "median_rank_pos"):
            out[k] = float("nan")
        return out
    out["auroc"] = float(roc_auc_score(labels, scores))
    out["auprc"] = float(average_precision_score(labels, scores))
    ranks = _ranks_higher_is_better(scores)
    pos_ranks = ranks[labels == 1]
    out["mrr"] = float(np.mean(1.0 / pos_ranks))
    for k in (10, 50, 100):
        out[f"hit@{k}"] = float(np.mean(pos_ranks <= k))
    out["median_rank_pos"] = float(np.median(pos_ranks))
    return out


def stratified_bootstrap_ci(
    scores: np.ndarray,
    labels: np.ndarray,
    n_bootstrap: int,
    rng: np.random.Generator,
    metrics_to_ci: tuple[str, ...] = ("auroc", "auprc", "mrr",
                                       "hit@10", "hit@50", "hit@100"),
) -> dict[str, tuple[float, float]]:
    pos_idx = np.where(labels == 1)[0]
    neg_idx = np.where(labels == 0)[0]
    if len(pos_idx) == 0 or len(neg_idx) == 0:
        return {m: (float("nan"), float("nan")) for m in metrics_to_ci}
    samples: dict[str, list[float]] = {m: [] for m in metrics_to_ci}
    for _ in range(n_bootstrap):
        bp = rng.choice(pos_idx, size=len(pos_idx), replace=True)
        bn = rng.choice(neg_idx, size=len(neg_idx), replace=True)
        idx = np.concatenate([bp, bn])
        sub_scores = scores[idx]
        sub_labels = labels[idx]
        m = metric_panel(sub_scores, sub_labels)
        for k in metrics_to_ci:
            v = m.get(k, float("nan"))
            if not np.isnan(v):
                samples[k].append(v)
    cis: dict[str, tuple[float, float]] = {}
    for k, vals in samples.items():
        if vals:
            lo = float(np.percentile(vals, 2.5))
            hi = float(np.percentile(vals, 97.5))
        else:
            lo, hi = float("nan"), float("nan")
        cis[k] = (lo, hi)
    return cis


def evaluate_contrast(
    contrast_id: str,
    contrast_def: dict,
    method_scores: pd.DataFrame,
    labels: pd.DataFrame,
    n_bootstrap: int,
    rng: np.random.Generator,
    min_n_for_report: int = 20,
    min_n_for_bootstrap: int = 5,
    n_mp_threshold: int = 1,
    n_mp_by_geno: Optional[dict] = None,
    emit_curves: bool = True,
):
    pos_groups = set(contrast_def["positive"])
    neg_groups = set(contrast_def["negative"])
    pos_genos = labels[labels["benchmark_group"].isin(pos_groups)]["genotype_id"]
    neg_genos = labels[labels["benchmark_group"].isin(neg_groups)]["genotype_id"]
    keep = set(pos_genos.tolist()) | set(neg_genos.tolist())

    sub = method_scores[method_scores["genotype_id"].isin(keep)].copy()
    sub["label"] = np.where(sub["genotype_id"].isin(set(pos_genos)), 1, 0)

    if n_mp_threshold is not None and n_mp_threshold > 1 and n_mp_by_geno is not None:
        eligible = {g for g, k in n_mp_by_geno.items() if k >= n_mp_threshold}
        sub = sub[sub["genotype_id"].isin(eligible)].copy()

    if sub.empty or sub["label"].nunique() < 2:
        log.warning(
            "Contrast %s (n_mp>=%d) has insufficient data; skipping.",
            contrast_id, n_mp_threshold,
        )
        return None, None, None, None

    method = sub["method"].iloc[0]
    scores = sub["score"].to_numpy()
    labs = sub["label"].to_numpy()

    panel = metric_panel(scores, labs)

    n_pos = int(panel["n_pos"])
    n_neg = int(panel["n_neg"])
    if n_pos < min_n_for_bootstrap or n_neg < min_n_for_bootstrap:
        log.warning(
            "Contrast %s: n_pos=%d, n_neg=%d below min_n_for_bootstrap=%d; "
            "reporting point estimate with CI = NaN. Bootstrap on this n "
            "produces artifact CIs (e.g. n_pos=1 → identical resamples).",
            contrast_id, n_pos, n_neg, min_n_for_bootstrap,
        )
        cis = {m: (float("nan"), float("nan")) for m in
               ("auroc", "auprc", "mrr", "hit@10", "hit@50", "hit@100")}
        ci_method = "skipped_low_n"
    else:
        cis = stratified_bootstrap_ci(scores, labs, n_bootstrap, rng)
        ci_method = "stratified_bootstrap"

    sub["rank"] = _ranks_higher_is_better(scores)
    sub["contrast"] = contrast_id
    sub["n_mp_threshold"] = n_mp_threshold

    if emit_curves:
        fpr, tpr, thr_roc = roc_curve(labs, scores)
        roc_df = pd.DataFrame(dict(method=method, contrast=contrast_id,
                                    fpr=fpr, tpr=tpr, threshold=thr_roc,
                                    n_mp_threshold=n_mp_threshold))
        prec, rec, thr_pr = precision_recall_curve(labs, scores)
        thr_pr_full = np.concatenate([thr_pr, [np.nan]])
        pr_df = pd.DataFrame(dict(method=method, contrast=contrast_id,
                                   precision=prec, recall=rec, threshold=thr_pr_full,
                                   n_mp_threshold=n_mp_threshold))
    else:
        roc_df = None
        pr_df = None

    rows = []
    for metric_name in ("auroc", "auprc", "mrr", "hit@10", "hit@50", "hit@100",
                        "median_rank_pos"):
        v = panel.get(metric_name, float("nan"))
        if metric_name in cis:
            lo, hi = cis[metric_name]
        else:
            lo, hi = float("nan"), float("nan")
        rows.append(dict(
            method=method,
            contrast=contrast_id,
            n_mp_threshold=n_mp_threshold,
            description=contrast_def["description"],
            positive_group=" + ".join(sorted(pos_groups)),
            negative_group=" + ".join(sorted(neg_groups)),
            metric=metric_name,
            value=v,
            ci_low=lo,
            ci_high=hi,
            ci_method=ci_method,
            n_pos=panel["n_pos"],
            n_neg=panel["n_neg"],
            n_bootstrap=n_bootstrap if ci_method == "stratified_bootstrap" else 0,
        ))
    metrics_df = pd.DataFrame(rows)
    if 'n_pos' in metrics_df.columns and 'n_neg' in metrics_df.columns:
        metrics_df['underpowered'] = (
            (metrics_df['n_pos'] < min_n_for_report)
            | (metrics_df['n_neg'] < min_n_for_report)
        )
        metrics_df['min_n_threshold'] = min_n_for_report
    return metrics_df, roc_df, pr_df, sub[["method", "contrast", "n_mp_threshold",
                                            "genotype_id", "score", "rank", "label"]]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--score_file", action="append", required=True,
                    help="Format: label::path or label::path::score_column. "
                         "Pass once per method.")
    ap.add_argument("--labels_file", type=Path, required=True,
                    help="Benchmark group labels (broad_benchmark_setup/"
                         "06_benchmark_group_table.csv).")
    ap.add_argument(
        "--contrasts_json", type=str, default=None,
        help="Path to JSON file (or inline JSON) with disorder-config "
             "contrast list. Falls back to DEFAULT_ASD_CONTRASTS if omitted. "
             "Supports __all_non_<X>_primary__ token expansion.",
    )
    ap.add_argument(
        "--min_n_for_report", type=int, default=20,
        help="Minimum n on either contrast arm for the AUROC to be "
             "considered powered. Contrasts with n_pos < min OR n_neg < min "
             "still get an AUROC printed but with underpowered=true.",
    )
    ap.add_argument(
        "--min_n_for_bootstrap", type=int, default=5,
        help="Minimum n on either contrast arm to attempt a stratified "
             "bootstrap CI. Below this, the CI is set to NaN with "
             "ci_method='skipped_low_n'. P8 audit fix 2026-05-25.",
    )
    ap.add_argument("--outdir", type=Path, required=True)
    ap.add_argument("--n_bootstrap", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument(
        "--n_mp_thresholds", type=str, default="1,3,4,5,7,10",
        help="Comma-separated list of n_mp_terms thresholds (>=K filter). "
             "Default '1,3,4,5,7,10'. K=1 is always added if absent so the "
             "baseline (no filter) row is always present. AUROC etc. are "
             "computed at every K; ROC/PR curves emitted only at K=1.",
    )
    ap.add_argument(
        "--n_mp_terms_file", type=Path, default=None,
        help="File providing n_mp_terms per genotype for the depth filter. "
             "Either (a) the universe-wide phenotype long table "
             "(broad_benchmark_setup/08_all_genotype_phenotypes_long_blinded.csv "
             "— count rows per genotype) or (b) a precomputed TSV with "
             "'genotype_id' + 'n_mp_terms' columns "
             "(e.g. 07b_per_genotype_covariates.tsv). Auto-detected. Required "
             "when any threshold > 1.",
    )
    args = ap.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)

    labels = load_labels(args.labels_file)
    active_contrasts = (
        load_contrasts_from_config(args.contrasts_json, labels)
        if args.contrasts_json
        else DEFAULT_ASD_CONTRASTS
    )
    log.info('Using %d contrasts: %s',
             len(active_contrasts), list(active_contrasts.keys()))
    specs = [parse_score_spec(s) for s in args.score_file]
    method_dfs = [load_score_file(s) for s in specs]

    n_mp_thresholds = parse_n_mp_thresholds(args.n_mp_thresholds)
    log.info("n_mp depth-filter thresholds: %s", n_mp_thresholds)
    n_mp_by_geno = None
    if any(k > 1 for k in n_mp_thresholds):
        if args.n_mp_terms_file is None:
            raise SystemExit(
                "--n_mp_thresholds includes K > 1 but --n_mp_terms_file is "
                "not set. Pass the universe-wide phenotype long table "
                "(e.g. broad_benchmark_setup/"
                "08_all_genotype_phenotypes_long_blinded.csv)."
            )
        n_mp_by_geno = load_n_mp_per_genotype(args.n_mp_terms_file)

    all_metrics, all_roc, all_pr, all_ranks = [], [], [], []
    t0 = time.time()
    for K in n_mp_thresholds:
        log.info("--- n_mp_threshold = %d ---", K)
        for spec, mdf in zip(specs, method_dfs):
            log.info("=== Method: %s (K=%d) ===", spec.label, K)
            for cid, cdef in active_contrasts.items():
                metrics_df, roc_df, pr_df, ranks_df = evaluate_contrast(
                    cid, cdef, mdf, labels, args.n_bootstrap, rng,
                    min_n_for_report=args.min_n_for_report,
                    min_n_for_bootstrap=args.min_n_for_bootstrap,
                    n_mp_threshold=K,
                    n_mp_by_geno=n_mp_by_geno,
                    emit_curves=(K == 1),
                )
                if metrics_df is None:
                    continue
                all_metrics.append(metrics_df)
                if roc_df is not None:
                    all_roc.append(roc_df)
                if pr_df is not None:
                    all_pr.append(pr_df)
                all_ranks.append(ranks_df)

    metrics_out = args.outdir / "03_metrics_per_contrast.tsv"
    safe_write_csv(pd.concat(all_metrics, ignore_index=True), metrics_out,
                   sep="\t", index=False)
    log.info("Wrote %s", metrics_out)

    roc_out = args.outdir / "04_roc_curves.tsv"
    if all_roc:
        safe_write_csv(pd.concat(all_roc, ignore_index=True), roc_out,
                       sep="\t", index=False)
        log.info("Wrote %s", roc_out)

    pr_out = args.outdir / "05_pr_curves.tsv"
    if all_pr:
        safe_write_csv(pd.concat(all_pr, ignore_index=True), pr_out,
                       sep="\t", index=False)
        log.info("Wrote %s", pr_out)

    ranks_out = args.outdir / "06_per_genotype_ranks.tsv"
    safe_write_csv(pd.concat(all_ranks, ignore_index=True), ranks_out,
                   sep="\t", index=False)
    log.info("Wrote %s", ranks_out)

    cfg = dict(
        methods=[s.label for s in specs],
        score_files=[str(s.path) for s in specs],
        labels_file=str(args.labels_file),
        contrasts=list(active_contrasts.keys()),
        n_bootstrap=args.n_bootstrap,
        seed=args.seed,
        n_mp_thresholds=n_mp_thresholds,
        n_mp_terms_file=(str(args.n_mp_terms_file)
                         if args.n_mp_terms_file is not None else None),
        n_mp_universe_size=(len(n_mp_by_geno) if n_mp_by_geno is not None else 0),
        elapsed_seconds=round(time.time() - t0, 1),
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
    )
    (args.outdir / "99_metrics_run_config.json").write_text(json.dumps(cfg, indent=2))
    log.info("Done in %.1fs", time.time() - t0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
