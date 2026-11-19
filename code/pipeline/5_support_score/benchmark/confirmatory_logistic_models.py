#!/usr/bin/env python3
"""confirmatory_logistic_models.py
===============================

Usage example
-------------
    python confirmatory_logistic_models.py         --score_file new_pipeline::asd_batch4_ranked_broad/07_recommended_ranking.tsv::recommended_score         --score_file B1_phenodigm_plain::benchmark/baseline_scores/01_baseline_genotype_scores__B1_phenodigm_plain.tsv::bma_score         --score_file B2_phenodigm_ic::benchmark/baseline_scores/01_baseline_genotype_scores__B2_phenodigm_ic.tsv::bma_score         --labels_file broad_benchmark_setup/06_benchmark_group_table.csv         --depth_assessability_file asd_support_aggregated_broad/07_assessability_summary.tsv         --outdir benchmark/logistic         --seed 1
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


from safe_write_util import safe_write_csv
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("logistic_confirm")


DEFAULT_SCORE_COLS = (
    "recommended_score",
    "rank_score",
    "overall_support_score_mean",
    "bma_score",
)


def parse_score_spec(s: str) -> tuple[str, Path, Optional[str]]:
    parts = s.split("::")
    if len(parts) == 2:
        return parts[0], Path(parts[1]), None
    if len(parts) == 3:
        return parts[0], Path(parts[1]), parts[2]
    raise ValueError(f"--score_file must be 'label::path[::col]'. Got: {s}")


def load_score_file(label: str, path: Path, score_col: Optional[str]) -> pd.DataFrame:
    sep = "," if path.suffix.lower() == ".csv" else "\t"
    df = pd.read_csv(path, sep=sep, low_memory=False)
    col = score_col or next((c for c in DEFAULT_SCORE_COLS if c in df.columns), None)
    if col is None:
        raise ValueError(f"Could not detect score column in {path}")
    out = df[["genotype_id", col]].rename(columns={col: "score"}).copy()
    out["genotype_id"] = out["genotype_id"].astype(str).str.strip()
    out["method"] = label
    return out.dropna(subset=["score"]).drop_duplicates(subset=["genotype_id"])


def load_labels(path: Path) -> pd.DataFrame:
    sep = "," if path.suffix.lower() == ".csv" else "\t"
    df = pd.read_csv(path, sep=sep, low_memory=False)
    keep = ["genotype_id", "benchmark_group"]
    if "n_mp_terms" in df.columns:
        keep.append("n_mp_terms")
    df = df[keep].copy()
    df["genotype_id"] = df["genotype_id"].astype(str).str.strip()
    df["benchmark_group"] = df["benchmark_group"].astype(str).str.strip()
    return df.drop_duplicates(subset=["genotype_id"])


def load_covariates(
    path: Optional[Path], labels: pd.DataFrame
) -> pd.DataFrame:
    if path is None:
        if "n_mp_terms" not in labels.columns:
            raise ValueError(
                "No --depth_assessability_file provided and labels file lacks "
                "n_mp_terms; cannot construct annotation-depth covariate."
            )

        df = labels[["genotype_id", "n_mp_terms"]].copy()
        df["assessable_fraction"] = float("nan")
        log.warning("No covariate file given; assessable_fraction will be NaN "
                    "and dropped from models if all-NaN.")
        return df

    sep = "," if path.suffix.lower() == ".csv" else "\t"
    df = pd.read_csv(path, sep=sep, low_memory=False)
    df["genotype_id"] = df["genotype_id"].astype(str).str.strip()

    if "analysis_mode" in df.columns:
        strict_mask = df["analysis_mode"].astype(str).str.lower() == "strict"
        if strict_mask.any():
            n_before = len(df)
            df = df[strict_mask].copy()
            log.info(
                "Covariate file has analysis_mode column; filtered to "
                "strict (%d -> %d rows).", n_before, len(df),
            )

    sort_cols, sort_asc = [], []
    if "supported_domains" in df.columns:
        sort_cols.append("supported_domains"); sort_asc.append(False)
    if "overall_support_score" in df.columns:
        sort_cols.append("overall_support_score"); sort_asc.append(False)
    if "mean_matched_targets_fraction" in df.columns:
        sort_cols.append("mean_matched_targets_fraction"); sort_asc.append(False)
    if sort_cols:
        n_before = len(df)
        df = (df.sort_values(sort_cols, ascending=sort_asc, na_position="last")
                .drop_duplicates(subset=["genotype_id"], keep="first")
                .reset_index(drop=True))
        if n_before != len(df):
            log.info(
                "Deduplicated covariate rows by genotype_id, preferring the "
                "SFARI-matched view (sorted by %s desc): %d -> %d (dropped %d "
                "duplicate SFARI-match/unmatched twins).",
                "/".join(sort_cols), n_before, len(df), n_before - len(df),
            )

    depth_candidates = ["n_mp_terms", "total_retained_terms",
                        "n_unique_mp_terms"]
    depth_col = next((c for c in depth_candidates if c in df.columns), None)
    if depth_col is None:
        if "n_mp_terms" in labels.columns:
            depth_df = labels[["genotype_id", "n_mp_terms"]]
        else:
            raise ValueError("No annotation-depth column found.")
    else:
        depth_df = df[["genotype_id", depth_col]].rename(
            columns={depth_col: "n_mp_terms"}
        )

    af_candidates = ["assessable_fraction",
                     "mean_matched_targets_fraction_mean",
                     "mean_matched_targets_fraction"]
    af_col = next((c for c in af_candidates if c in df.columns), None)
    if af_col is not None:
        af_df = df[["genotype_id", af_col]].rename(
            columns={af_col: "assessable_fraction"}
        )
    else:
        if "assessable_domains_mean" in df.columns:
            af_df = df[["genotype_id", "assessable_domains_mean"]].copy()
            af_df["assessable_fraction"] = af_df["assessable_domains_mean"] / 4.0
            af_df = af_df[["genotype_id", "assessable_fraction"]]
        else:
            af_df = pd.DataFrame(
                {"genotype_id": depth_df["genotype_id"],
                 "assessable_fraction": float("nan")}
            )

    out = depth_df.merge(af_df, on="genotype_id", how="outer")
    out = out.drop_duplicates(subset=["genotype_id"])
    return out


def standardize(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    mu = np.nanmean(x)
    sd = np.nanstd(x, ddof=1)
    if sd == 0 or np.isnan(sd):
        return x - mu
    return (x - mu) / sd


def fit_binary_logit(
    X: pd.DataFrame, y: np.ndarray, used_firth: bool = False
) -> dict:
    from statsmodels.api import Logit

    X = X.copy()
    X.insert(0, "Intercept", 1.0)
    sep_flag = False
    used_firth_local = False
    used_sklearn = False

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            model = Logit(y, X)
            res = model.fit(disp=False, maxiter=200)
        coefs = res.params
        ses = res.bse
        zs = res.tvalues
        ps = res.pvalues
        llf = float(res.llf)
        py = float(np.mean(y))
        ll0 = float(np.sum(y * np.log(py + 1e-12) + (1 - y) * np.log(1 - py + 1e-12)))
        mcfadden = 1 - llf / ll0 if ll0 != 0 else float("nan")
        n_params = X.shape[1]
        aic = 2 * n_params - 2 * llf
        bic = n_params * np.log(len(y)) - 2 * llf
        convergence_status = "converged"
        if np.any(np.abs(zs.values) > 8) or np.any(np.abs(coefs.values) > 50):
            sep_flag = True
    except Exception as e:
        log.warning("MLE logit failed (%s); falling back.", e)
        try:
            from firthlogist import FirthLogisticRegression
            flr = FirthLogisticRegression()
            flr.fit(X.values, y)
            coefs = pd.Series(flr.coef_, index=X.columns)
            ses = pd.Series(flr.bse_, index=X.columns)
            zs = coefs / ses
            from scipy.stats import norm
            ps = pd.Series(2 * (1 - norm.cdf(np.abs(zs))), index=X.columns)
            llf = float(flr.loglik_)
            py = float(np.mean(y))
            ll0 = float(np.sum(y * np.log(py + 1e-12) + (1 - y) * np.log(1 - py + 1e-12)))
            mcfadden = 1 - llf / ll0 if ll0 != 0 else float("nan")
            n_params = X.shape[1]
            aic = 2 * n_params - 2 * llf
            bic = n_params * np.log(len(y)) - 2 * llf
            convergence_status = "firth_used"
            sep_flag = True
            used_firth_local = True
        except Exception as e2:
            log.warning("Firth unavailable or failed (%s); using sklearn L2.", e2)
            from sklearn.linear_model import LogisticRegression
            lr = LogisticRegression(C=1e6, solver="lbfgs", max_iter=1000)
            lr.fit(X.drop(columns=["Intercept"]).values, y)
            coefs = pd.Series([lr.intercept_[0]] + list(lr.coef_[0]), index=X.columns)
            ses = pd.Series([float("nan")] * len(coefs), index=X.columns)
            zs = pd.Series([float("nan")] * len(coefs), index=X.columns)
            ps = pd.Series([float("nan")] * len(coefs), index=X.columns)
            llf = float("nan")
            mcfadden = float("nan")
            aic = float("nan")
            bic = float("nan")
            convergence_status = "sklearn_l2_fallback"
            sep_flag = True
            used_sklearn = True

    or_vals = np.exp(coefs)
    or_lo = np.exp(coefs - 1.96 * ses)
    or_hi = np.exp(coefs + 1.96 * ses)

    rows = []
    for term in coefs.index:
        rows.append(dict(
            term=term,
            coefficient=float(coefs[term]),
            se=float(ses[term]) if not pd.isna(ses[term]) else float("nan"),
            z=float(zs[term]) if not pd.isna(zs[term]) else float("nan"),
            p=float(ps[term]) if not pd.isna(ps[term]) else float("nan"),
            odds_ratio=float(or_vals[term]),
            or_ci_low=float(or_lo[term]) if not pd.isna(or_lo[term]) else float("nan"),
            or_ci_high=float(or_hi[term]) if not pd.isna(or_hi[term]) else float("nan"),
            separation_flag=sep_flag,
        ))
    diag = dict(
        n_obs=len(y),
        positives=int(y.sum()),
        negatives=int(len(y) - y.sum()),
        llf=llf, aic=aic, bic=bic, mcfadden_r2=mcfadden,
        convergence_status=convergence_status,
        used_firth=used_firth_local,
        used_sklearn_fallback=used_sklearn,
    )
    return dict(rows=rows, diagnostics=diag)


def fit_multinomial(X: pd.DataFrame, y_str: np.ndarray, reference: str) -> dict:
    from statsmodels.api import MNLogit

    classes = sorted(set(y_str.tolist()))
    if reference not in classes:
        log.warning("Multinomial reference '%s' not in classes %s; "
                    "falling back to first class.", reference, classes)
        reference = classes[0]
    ordered = [reference] + [c for c in classes if c != reference]
    code_map = {c: i for i, c in enumerate(ordered)}
    y_int = np.array([code_map[c] for c in y_str])

    X = X.copy()
    X.insert(0, "Intercept", 1.0)
    res = MNLogit(y_int, X).fit(disp=False, maxiter=200)

    rows = []
    for cls_idx, col in enumerate(res.params.columns):
        cls_name = ordered[cls_idx + 1]
        for term in res.params.index:
            beta = float(res.params.loc[term, col])
            se = float(res.bse.loc[term, col])
            z = float(res.tvalues.loc[term, col])
            p = float(res.pvalues.loc[term, col])
            rows.append(dict(
                term=term, beta=beta, se=se, z=z, p=p,
                odds_ratio=float(np.exp(beta)),
                or_ci_low=float(np.exp(beta - 1.96 * se)),
                or_ci_high=float(np.exp(beta + 1.96 * se)),
                class_vs_reference=f"{cls_name}_vs_{reference}",
            ))
    diag = dict(
        n_obs=len(y_int),
        llf=float(res.llf),
        aic=float(res.aic),
        bic=float(res.bic),
        convergence_status="converged" if res.mle_retvals.get("converged", True) else "no_convergence",
    )
    return dict(rows=rows, diagnostics=diag, reference=reference)


PSYCH_NON_ASD = {"NDD_non_ASD", "psychiatric_non_NDD_non_ASD",
                 "language_social_confound_non_ASD"}
ALL_NON_ASD = PSYCH_NON_ASD | {"broad_other"}


def load_m_family_from_config(arg, labels_df):
    import json as _json
    from pathlib import Path as _Path
    text = None
    pp = _Path(arg) if arg else None
    if pp is not None and pp.exists():
        text = pp.read_text(encoding="utf-8")
    elif arg and arg.strip().startswith(("[", "{")):
        text = arg
    else:
        raise ValueError(
            f"--m_family_json: not a file path and not a JSON string: {arg!r}"
        )
    raw = _json.loads(text)
    if isinstance(raw, dict):
        if "m_family" in raw:
            raw = raw["m_family"]
        elif "stage5_benchmark" in raw and isinstance(raw["stage5_benchmark"], dict) \
                and "m_family" in raw["stage5_benchmark"]:
            raw = raw["stage5_benchmark"]["m_family"]
        else:
            raise ValueError(
                "--m_family_json dict must contain 'm_family' key or "
                "'stage5_benchmark.m_family'. Got keys: "
                f"{list(raw.keys())[:10]}"
            )
    if not isinstance(raw, list):
        raise ValueError("m_family must be a list of model specs")
    bg_universe = set(labels_df["benchmark_group"].dropna().astype(str).unique())
    out = []
    for i, m in enumerate(raw):
        name = m.get("name") or m.get("id") or f"M{i+1}"
        mtype = m.get("model_type", "binary_logit")
        pos = m.get("positive_label") or m.get("positive_group")
        if not pos:
            raise ValueError(f"m_family entry {name}: missing positive_label")
        pool_id = m.get("comparator_pool_id") or m.get("comparator_pool") or "pool"
        cgroups = m.get("comparator_groups")
        if not cgroups:
            raise ValueError(
                f"m_family entry {name}: missing comparator_groups (explicit "
                "benchmark_group list required after H1 fix)"
            )
        if isinstance(cgroups, str):
            cgroups = [cgroups]
        unknown = [g for g in cgroups if g not in bg_universe]
        if unknown:
            log.warning(
                "m_family %s: %d comparator_groups not present in labels "
                "benchmark_group universe (will be no-op): %s",
                name, len(unknown), unknown,
            )
        if pos not in bg_universe:
            log.warning(
                "m_family %s: positive_label %r not present in labels "
                "(model will produce 0 positives)", name, pos,
            )
        entry = dict(
            name=name,
            model_type=mtype,
            positive_label=pos,
            comparator_pool_id=pool_id,
            comparator_groups=cgroups,
        )
        if mtype == "multinomial_logit":
            ref = m.get("multinomial_reference") or m.get("reference")
            if not ref:
                ref = cgroups[0]
                log.warning(
                    "m_family %s (multinomial): no multinomial_reference set, "
                    "defaulting to first comparator group %r", name, ref,
                )
            entry["multinomial_reference"] = ref
        out.append(entry)
    return out


def asd_default_m_family():
    return [
        dict(
            name="M1_psychiatric_non_ASD",
            model_type="binary_logit",
            positive_label="ASD_primary",
            comparator_pool_id="psychiatric_non_ASD",
            comparator_groups=sorted(PSYCH_NON_ASD),
        ),
        dict(
            name="M2_all_non_ASD",
            model_type="binary_logit",
            positive_label="ASD_primary",
            comparator_pool_id="all_non_ASD",
            comparator_groups=sorted(ALL_NON_ASD),
        ),
        dict(
            name="M3_multinomial_psych_pool",
            model_type="multinomial_logit",
            positive_label="ASD_primary",
            comparator_pool_id="psychiatric_pool_multinomial",
            comparator_groups=sorted(PSYCH_NON_ASD),
            multinomial_reference="NDD_non_ASD",
        ),
    ]


def build_design(
    method_scores: pd.DataFrame, labels: pd.DataFrame, covars: pd.DataFrame,
    pos_groups: set[str], neg_groups: set[str],
) -> tuple[pd.DataFrame, np.ndarray, str]:
    keep = labels[labels["benchmark_group"].isin(pos_groups | neg_groups)].copy()
    if "n_mp_terms" in covars.columns and "n_mp_terms" in keep.columns:
        keep = keep.drop(columns=["n_mp_terms"])
    df = (
        method_scores.merge(keep, on="genotype_id")
        .merge(covars, on="genotype_id", how="left")
    )
    df = df.dropna(subset=["score", "n_mp_terms"])
    if df.empty:
        return None, None, "empty"
    df["log_n_mp_terms"] = np.log(df["n_mp_terms"].astype(float).clip(lower=1))
    df["score_z"] = standardize(df["score"].to_numpy())
    df["log_n_mp_terms_z"] = standardize(df["log_n_mp_terms"].to_numpy())
    has_af = df["assessable_fraction"].notna().any()
    if has_af:
        df["assessable_fraction_z"] = standardize(
            df["assessable_fraction"].fillna(df["assessable_fraction"].mean()).to_numpy()
        )
        feature_cols = ["score_z", "log_n_mp_terms_z", "assessable_fraction_z"]
    else:
        feature_cols = ["score_z", "log_n_mp_terms_z"]

    X = df[feature_cols].astype(float)
    y = df["benchmark_group"].isin(pos_groups).astype(int).to_numpy()
    return X, y, ("with_assessable" if has_af else "without_assessable")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--score_file", action="append", required=True)
    ap.add_argument("--labels_file", type=Path, required=True)
    ap.add_argument("--depth_assessability_file", type=Path, default=None)
    ap.add_argument(
        "--m_family_json", type=str, default=None,
        help="Path to disorder.json (uses stage5_benchmark.m_family) or "
             "inline JSON (list, or {m_family:[...]}). H1 fix 2026-05-27: "
             "without this flag the script falls back to ASD M1/M2/M3 — "
             "passing a non-ASD labels_file without --m_family_json will "
             "produce empty fits (zero positives).",
    )
    ap.add_argument("--outdir", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)

    labels = load_labels(args.labels_file)
    covars = load_covariates(args.depth_assessability_file, labels)

    if args.m_family_json:
        m_family = load_m_family_from_config(args.m_family_json, labels)
        log.info("Loaded %d m_family models from config: %s",
                 len(m_family), [m["name"] for m in m_family])
    else:
        m_family = asd_default_m_family()
        log.warning(
            "No --m_family_json passed; falling back to ASD default m_family. "
            "If you are benchmarking a non-ASD disorder this will produce "
            "0-positive fits — pass --m_family_json <disorder>.disorder.json."
        )

    summary_rows = []
    diag_rows = []
    for spec_str in args.score_file:
        label, path, col = parse_score_spec(spec_str)
        ms = load_score_file(label, path, col)
        log.info("=== Method: %s ===", label)

        for m in m_family:
            mname = m["name"]
            mtype = m["model_type"]
            pos = m["positive_label"]
            pool_id = m["comparator_pool_id"]
            cgroups = set(m["comparator_groups"])

            if mtype == "binary_logit":
                X, y, fset = build_design(
                    ms, labels, covars,
                    pos_groups={pos},
                    neg_groups=cgroups,
                )
                if X is None:
                    log.warning("%s: design matrix empty; skipping", mname)
                    continue
                if len(np.unique(y)) < 2:
                    log.warning(
                        "%s: only one class present (n_pos=%d, n_neg=%d); "
                        "skipping", mname, int((y == 1).sum()), int((y == 0).sum()),
                    )
                    continue
                res = fit_binary_logit(X, y)
                for r in res["rows"]:
                    summary_rows.append(dict(
                        method=label, model_id=mname,
                        model_type="binary_logit",
                        feature_set=fset,
                        comparator_pool=pool_id,
                        positives_label=pos,
                        n_obs=res["diagnostics"]["n_obs"],
                        positives=res["diagnostics"]["positives"],
                        negatives=res["diagnostics"]["negatives"],
                        **r,
                    ))
                diag_rows.append(dict(
                    method=label, model_id=mname,
                    model_type="binary_logit",
                    comparator_pool=pool_id,
                    **res["diagnostics"],
                ))

            elif mtype == "multinomial_logit":
                ref = m["multinomial_reference"]
                keep_groups = {pos} | cgroups
                sub_labels = labels[labels["benchmark_group"].isin(keep_groups)].copy()
                if "n_mp_terms" in covars.columns and "n_mp_terms" in sub_labels.columns:
                    sub_labels = sub_labels.drop(columns=["n_mp_terms"])
                df3 = (
                    ms.merge(sub_labels, on="genotype_id")
                    .merge(covars, on="genotype_id", how="left")
                    .dropna(subset=["score", "n_mp_terms"])
                )
                if df3.empty or df3["benchmark_group"].nunique() < 2:
                    log.warning(
                        "%s (multinomial): insufficient classes; skipping", mname,
                    )
                    continue
                df3["log_n_mp_terms"] = np.log(df3["n_mp_terms"].astype(float).clip(lower=1))
                df3["score_z"] = standardize(df3["score"].to_numpy())
                df3["log_n_mp_terms_z"] = standardize(df3["log_n_mp_terms"].to_numpy())
                cols = ["score_z", "log_n_mp_terms_z"]
                if df3["assessable_fraction"].notna().any():
                    df3["assessable_fraction_z"] = standardize(
                        df3["assessable_fraction"].fillna(df3["assessable_fraction"].mean()).to_numpy()
                    )
                    cols.append("assessable_fraction_z")
                X = df3[cols].astype(float)
                groups_present = set(df3["benchmark_group"].unique())
                if ref not in groups_present:
                    alt = (df3[df3["benchmark_group"] != pos]
                           ["benchmark_group"].value_counts())
                    if len(alt) == 0:
                        log.warning(
                            "%s: no comparator class present; skipping", mname,
                        )
                        continue
                    new_ref = alt.index[0]
                    log.warning(
                        "%s: configured multinomial_reference %r missing from "
                        "labels subset; using largest comparator %r instead",
                        mname, ref, new_ref,
                    )
                    ref = new_ref
                try:
                    res = fit_multinomial(
                        X, df3["benchmark_group"].to_numpy(), reference=ref,
                    )
                    for r in res["rows"]:
                        summary_rows.append(dict(
                            method=label, model_id=mname,
                            model_type="multinomial_logit",
                            feature_set="with_assessable" if "assessable_fraction_z" in cols else "without_assessable",
                            comparator_pool=pool_id,
                            positives_label=f"{pos}_vs_other",
                            n_obs=res["diagnostics"]["n_obs"],
                            positives=int((df3["benchmark_group"] == pos).sum()),
                            negatives=int((df3["benchmark_group"] != pos).sum()),
                            coefficient=r["beta"],
                            se=r["se"], z=r["z"], p=r["p"],
                            odds_ratio=r["odds_ratio"],
                            or_ci_low=r["or_ci_low"],
                            or_ci_high=r["or_ci_high"],
                            separation_flag=False,
                            term=f"{r['term']}::{r['class_vs_reference']}",
                        ))
                    diag_rows.append(dict(
                        method=label, model_id=mname,
                        model_type="multinomial_logit",
                        comparator_pool=pool_id,
                        **res["diagnostics"],
                    ))
                except Exception as e:
                    log.warning("Multinomial fit failed for %s/%s: %s",
                                label, mname, e)
            else:
                log.warning("%s: unsupported model_type %r; skipping",
                            mname, mtype)

    out_summary = args.outdir / "11_logistic_model_summary.tsv"
    safe_write_csv(pd.DataFrame(summary_rows), out_summary, sep="\t", index=False)
    log.info("Wrote %s", out_summary)

    out_diag = args.outdir / "12_model_diagnostics.tsv"
    safe_write_csv(pd.DataFrame(diag_rows), out_diag, sep="\t", index=False)
    log.info("Wrote %s", out_diag)

    cfg = dict(
        score_files=args.score_file,
        labels_file=str(args.labels_file),
        depth_assessability_file=(
            str(args.depth_assessability_file)
            if args.depth_assessability_file else None
        ),
        m_family_json=args.m_family_json,
        m_family_resolved=m_family,
        m_family_source=("config" if args.m_family_json else "asd_default_fallback"),
        seed=args.seed,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
    )
    (args.outdir / "99_logistic_run_config.json").write_text(json.dumps(cfg, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
