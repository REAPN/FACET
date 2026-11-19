#!/usr/bin/env python3
"""domain_hypothesis_tests.py
==========================

Usage
-----
    python domain_hypothesis_tests.py \\
        --domain_scores_file <stage3>/05_domain_support.tsv \\
        --labels_file broad_benchmark_setup/06_benchmark_group_table.csv \\
        --analysis_mode strict \\
        --b_family_json <disorder>.disorder.json \\
        --positive_groups SCZ_primary \\
        --negative_groups MDD_primary,Bipolar_primary,...,ASD_primary \\
        --outdir benchmark/domain \\
        --n_permutations 10000 \\
        --n_bootstrap 1000 \\
        --seed 1
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd


from safe_write_util import safe_write_csv
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("domain_tests")


DEFAULT_STRICT_DOMAINS = (
    "social_interaction",
    "communication",
    "repetitive_restricted",
    "sensory_reactivity",
)
DEFAULT_B2_DOMAIN = "social_interaction"
DEFAULT_B3_DOMAIN = "communication"
STRICT_DOMAINS = DEFAULT_STRICT_DOMAINS

DEFAULT_NEGATIVE_GROUPS = (
    "NDD_non_ASD",
    "psychiatric_non_NDD_non_ASD",
    "language_social_confound_non_ASD",
)


def load_domain_scores(path: Path, analysis_mode):
    sep = "," if path.suffix.lower() == ".csv" else "\t"
    df = pd.read_csv(path, sep=sep, low_memory=False)
    needed = {"genotype_id", "domain", "domain_support_score"}
    missing = needed - set(df.columns)
    if missing:
        raise ValueError(f"{path} missing columns: {missing}. "
                         f"Found: {list(df.columns)[:30]}")
    df["genotype_id"] = df["genotype_id"].astype(str).str.strip()
    df["domain"] = df["domain"].astype(str).str.strip()
    if "analysis_mode" in df.columns and analysis_mode is not None:
        df = df[df["analysis_mode"].astype(str).str.lower() == analysis_mode.lower()]
        log.info("Filtered to analysis_mode='%s' (%d rows)", analysis_mode, len(df))

    before = len(df)
    agg_map = {"domain_support_score": "max"}
    for col in ("domain_supported", "n_targets_assessable", "n_targets_supported",
                "n_targets_total", "matched_targets_fraction"):
        if col in df.columns:
            agg_map[col] = "max"
    df = df.groupby(["genotype_id", "domain"], as_index=False).agg(agg_map)
    after = len(df)
    if before != after:
        log.info("Deduplicated (genotype_id, domain): %d -> %d", before, after)
    return df


def load_labels(path: Path):
    sep = "," if path.suffix.lower() == ".csv" else "\t"
    df = pd.read_csv(path, sep=sep, low_memory=False)
    df = df[["genotype_id", "benchmark_group"]].copy()
    df["genotype_id"] = df["genotype_id"].astype(str).str.strip()
    df["benchmark_group"] = df["benchmark_group"].astype(str).str.strip()
    return df.drop_duplicates(subset=["genotype_id"])


def cliffs_delta(pos, neg):
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    if len(pos) * len(neg) > 5_000_000:
        all_v = np.concatenate([pos, neg])
        order = np.argsort(all_v, kind="mergesort")
        is_pos = np.concatenate([np.ones(len(pos), int), np.zeros(len(neg), int)])
        is_pos = is_pos[order]
        cumneg_below = np.cumsum(1 - is_pos)
        gt = float(np.sum(cumneg_below[is_pos == 1])) / (len(pos) * len(neg))
        return 2 * gt - 1
    diff = pos[:, None] - neg[None, :]
    gt = float(np.sum(diff > 0))
    lt = float(np.sum(diff < 0))
    return (gt - lt) / (len(pos) * len(neg))


def cliffs_delta_bootstrap_ci(pos, neg, n_bootstrap, rng):
    if len(pos) == 0 or len(neg) == 0:
        return float("nan"), float("nan")
    samples = []
    for _ in range(n_bootstrap):
        bp = rng.choice(pos, size=len(pos), replace=True)
        bn = rng.choice(neg, size=len(neg), replace=True)
        samples.append(cliffs_delta(bp, bn))
    return float(np.percentile(samples, 2.5)), float(np.percentile(samples, 97.5))


def permutation_test_two_sample(pos, neg, statistic, n_permutations, rng):
    if len(pos) == 0 or len(neg) == 0:
        return float("nan"), float("nan")
    combined = np.concatenate([pos, neg])
    n_pos = len(pos)

    def stat(p, n):
        if statistic == "median":
            return np.median(p) - np.median(n)
        if statistic == "mean":
            return np.mean(p) - np.mean(n)
        raise ValueError(f"Unknown statistic: {statistic}")

    obs = stat(pos, neg)
    perm_stats = np.empty(n_permutations)
    for i in range(n_permutations):
        perm = rng.permutation(combined)
        perm_stats[i] = stat(perm[:n_pos], perm[n_pos:])
    p = float((np.abs(perm_stats) >= abs(obs)).mean())
    return float(obs), p


def compute_strict_composite(domain_long, strict_domains=None):
    if strict_domains is None:
        strict_domains = DEFAULT_STRICT_DOMAINS
    sub = domain_long[domain_long["domain"].isin(strict_domains)].copy()
    if "n_targets_assessable" in sub.columns:
        sub = sub[sub["n_targets_assessable"].fillna(0).astype(float) > 0]
    out = (
        sub.groupby("genotype_id")["domain_support_score"]
        .mean()
        .reset_index()
        .rename(columns={"domain_support_score": "strict_composite"})
    )
    log.info("Strict composite computed for %d genotypes (>=1 assessable strict domain).",
             len(out))
    return out


def compute_cluster_mean(domain_long, domains):
    sub = domain_long[domain_long["domain"].isin(domains)].copy()
    if "n_targets_assessable" in sub.columns:
        sub = sub[sub["n_targets_assessable"].fillna(0).astype(float) > 0]
    out = (
        sub.groupby("genotype_id")["domain_support_score"]
        .mean()
        .reset_index()
        .rename(columns={"domain_support_score": "value"})
    )
    log.info("cluster_mean over %s computed for %d genotypes",
             list(domains), len(out))
    return out


def load_b_family_from_config(arg):
    text = None
    pp = Path(arg) if arg else None
    if pp is not None and pp.exists():
        text = pp.read_text(encoding="utf-8")
    elif arg and arg.strip().startswith(("[", "{")):
        text = arg
    else:
        raise ValueError(
            f"--b_family_json: not a file path and not a JSON string: {arg!r}"
        )
    raw = json.loads(text)
    if isinstance(raw, dict):
        if "b_family" in raw:
            raw = raw["b_family"]
        elif "stage5_benchmark" in raw and isinstance(raw["stage5_benchmark"], dict) \
                and "b_family" in raw["stage5_benchmark"]:
            raw = raw["stage5_benchmark"]["b_family"]
        else:
            raise ValueError(
                "--b_family_json dict must contain 'b_family' or "
                "'stage5_benchmark.b_family'."
            )
    if not isinstance(raw, list):
        raise ValueError("b_family must be a list of entries")
    out = []
    for i, b in enumerate(raw):
        out.append(dict(
            name=b.get("name") or f"B{i+1}",
            type=b.get("type", "composite_mean"),
            domains=b.get("domains"),
            label=b.get("label", ""),
            gated_by=b.get("gated_by"),
            multiplicity_correction=b.get("multiplicity_correction"),
            comparator_pool_id=b.get("comparator_pool_id"),
            comparator_pool_ids=b.get("comparator_pool_ids"),
        ))
    return out


def run_hypothesis(
    hyp_id, description, score_table, score_col,
    pos_genos, neg_genos, n_perm, n_boot, rng,
    family_label, gated_by,
):
    pos_vals = score_table[score_table["genotype_id"].isin(pos_genos)][score_col].dropna().to_numpy()
    neg_vals = score_table[score_table["genotype_id"].isin(neg_genos)][score_col].dropna().to_numpy()

    obs_med, p_med = permutation_test_two_sample(pos_vals, neg_vals, "median", n_perm, rng)
    obs_mean, p_mean = permutation_test_two_sample(pos_vals, neg_vals, "mean", n_perm, rng)
    cd = cliffs_delta(pos_vals, neg_vals)
    cd_lo, cd_hi = cliffs_delta_bootstrap_ci(pos_vals, neg_vals, n_boot, rng)

    return dict(
        hypothesis_id=hyp_id,
        description=description,
        n_pos=int(len(pos_vals)),
        n_neg=int(len(neg_vals)),
        median_pos=float(np.median(pos_vals)) if len(pos_vals) else float("nan"),
        median_neg=float(np.median(neg_vals)) if len(neg_vals) else float("nan"),
        mean_pos=float(np.mean(pos_vals)) if len(pos_vals) else float("nan"),
        mean_neg=float(np.mean(neg_vals)) if len(neg_vals) else float("nan"),
        observed_diff_median=obs_med,
        observed_diff_mean=obs_mean,
        cliffs_delta=cd,
        cliffs_delta_ci_low=cd_lo,
        cliffs_delta_ci_high=cd_hi,
        p_perm_two_sided=p_med,
        p_perm_mean=p_mean,
        family_label=family_label,
        gated_by=gated_by or "",
    )


def holm_correct(p_values):
    n = len(p_values)
    if n == 0:
        return []
    order = np.argsort(p_values)
    adj_sorted = np.empty(n)
    cur_max = 0.0
    for i, idx in enumerate(order):
        adj = (n - i) * p_values[idx]
        adj = min(adj, 1.0)
        cur_max = max(cur_max, adj)
        adj_sorted[i] = cur_max
    out = np.empty(n)
    for i, idx in enumerate(order):
        out[idx] = adj_sorted[i]
    return out.tolist()


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--domain_scores_file", type=Path, required=True)
    ap.add_argument("--labels_file", type=Path, required=True)
    ap.add_argument("--analysis_mode", default="strict")
    ap.add_argument("--positive_groups", default="ASD_primary",
                    help="Comma-separated benchmark groups treated as positives.")
    ap.add_argument("--negative_groups",
                    default=",".join(DEFAULT_NEGATIVE_GROUPS),
                    help="Comma-separated benchmark groups treated as negatives.")
    ap.add_argument("--outdir", type=Path, required=True)
    ap.add_argument("--n_permutations", type=int, default=10000)
    ap.add_argument("--n_bootstrap", type=int, default=1000)
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--strict_domains", type=str, default=None,
                    help="Comma-separated domain names for strict composite (B1).")
    ap.add_argument("--b2_domain", type=str, default=None)
    ap.add_argument("--b3_domain", type=str, default=None)
    ap.add_argument("--b_family_json", type=str, default=None,
                    help="Path to disorder.json or inline JSON list. When "
                         "provided, replaces the legacy ASD-default "
                         "B1/B2/B3 set with config-driven entries.")
    args = ap.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)

    strict_domains = (tuple(s.strip() for s in args.strict_domains.split(","))
                      if args.strict_domains else DEFAULT_STRICT_DOMAINS)
    b2_domain = args.b2_domain or DEFAULT_B2_DOMAIN
    b3_domain = args.b3_domain or DEFAULT_B3_DOMAIN
    log.info("Strict composite domains: %s", list(strict_domains))

    domain_long = load_domain_scores(args.domain_scores_file, args.analysis_mode)
    labels = load_labels(args.labels_file)

    pos_groups = {g.strip() for g in args.positive_groups.split(",")}
    neg_groups = {g.strip() for g in args.negative_groups.split(",")}
    pos_genos = set(labels[labels["benchmark_group"].isin(pos_groups)]["genotype_id"])
    neg_genos = set(labels[labels["benchmark_group"].isin(neg_groups)]["genotype_id"])

    log.info("Positives (%s): %d genotypes", "+".join(sorted(pos_groups)), len(pos_genos))
    log.info("Negatives (%s): %d genotypes", "+".join(sorted(neg_groups)), len(neg_genos))

    if args.b_family_json:
        b_family = load_b_family_from_config(args.b_family_json)
        _SUPPORTED_BTYPES = {"composite_mean", "cluster_mean"}
        _dropped = [b.get("name") for b in b_family if b.get("type") not in _SUPPORTED_BTYPES]
        if _dropped:
            log.warning("Skipping unsupported/obsolete b_family entries %s (supported: %s)",
                        _dropped, sorted(_SUPPORTED_BTYPES))
        b_family = [b for b in b_family if b.get("type") in _SUPPORTED_BTYPES]
        log.info("Loaded %d b_family entries: %s",
                 len(b_family), [b["name"] for b in b_family])

        per_entry_tables = {}
        for b in b_family:
            name = b["name"]
            btype = b["type"]
            doms = b["domains"]
            if btype == "composite_mean":
                if isinstance(doms, str) and doms == "all_strict":
                    use_domains = list(strict_domains)
                elif isinstance(doms, (list, tuple)):
                    use_domains = list(doms)
                else:
                    raise ValueError(
                        f"b_family entry {name}: composite_mean.domains must "
                        f"be 'all_strict' or a list (got {doms!r})"
                    )
                tbl = compute_strict_composite(domain_long, strict_domains=use_domains)
                tbl = tbl.rename(columns={"strict_composite": "value"})
            elif btype == "cluster_mean":
                if not isinstance(doms, (list, tuple)) or not doms:
                    raise ValueError(
                        f"b_family entry {name}: cluster_mean.domains must "
                        f"be a non-empty list (got {doms!r})"
                    )
                tbl = compute_cluster_mean(domain_long, list(doms))
            else:
                raise ValueError(
                    f"b_family entry {name}: unsupported type {btype!r}"
                )
            per_entry_tables[name] = (tbl, b)

        primary_rows = []
        secondary_rows = []
        for name, (tbl, b) in per_entry_tables.items():
            family = "B1_primary" if b["gated_by"] is None else "B2_B3_secondary"
            row = run_hypothesis(
                hyp_id=name,
                description=(b.get("label") or
                             f"{'+'.join(sorted(pos_groups))} vs comparator on {name}"),
                score_table=tbl, score_col="value",
                pos_genos=pos_genos, neg_genos=neg_genos,
                n_perm=args.n_permutations, n_boot=args.n_bootstrap, rng=rng,
                family_label=family,
                gated_by=b["gated_by"],
            )
            if b["gated_by"] is None:
                primary_rows.append(row)
            else:
                secondary_rows.append(row)

        if secondary_rows:
            holm_adj = holm_correct([r["p_perm_two_sided"] for r in secondary_rows])
            for r, p_adj in zip(secondary_rows, holm_adj):
                r["p_holm_within_family"] = p_adj
        for r in primary_rows:
            r["p_holm_within_family"] = float("nan")

        primary_ok = False
        gate_id = None
        if primary_rows:
            r0 = primary_rows[0]
            gate_id = r0["hypothesis_id"]
            primary_ok = (
                r0.get("p_perm_two_sided") is not None
                and r0["p_perm_two_sided"] < args.alpha
                and r0.get("cliffs_delta") is not None
                and r0["cliffs_delta"] > 0
            )
            r0["decision"] = "REJECT_H0_B1" if primary_ok else "FAIL_TO_REJECT_H0_B1"
        for r in secondary_rows:
            if not primary_ok:
                r["decision"] = f"GATED_OUT_BY_{gate_id or 'B1'}"
            else:
                sig = (
                    r["p_holm_within_family"] is not None
                    and r["p_holm_within_family"] < args.alpha
                    and r.get("cliffs_delta") is not None
                    and r["cliffs_delta"] > 0
                )
                r["decision"] = "REJECT_H0" if sig else "FAIL_TO_REJECT_H0"

        rows = primary_rows + secondary_rows
        out_df = pd.DataFrame(rows)
        out_df.insert(0, "comparator_pool_label", "+".join(sorted(neg_groups)))
        out_df.insert(0, "analysis_mode", args.analysis_mode)
        out_path = args.outdir / "09_domain_hypothesis_tests.tsv"
        safe_write_csv(out_df, out_path, sep="\t", index=False)
        log.info("Wrote %s (%d b_family entries)", out_path, len(rows))

        blocks = []
        for name, (tbl, _b) in per_entry_tables.items():
            d = tbl.copy()
            d["domain_or_composite"] = name
            d["group"] = np.where(
                d["genotype_id"].isin(pos_genos), "pos",
                np.where(d["genotype_id"].isin(neg_genos), "neg", "other"),
            )
            blocks.append(d)
        long_out = pd.concat(blocks, ignore_index=True)
        long_path = args.outdir / "10_domain_score_long.tsv"
        safe_write_csv(long_out, long_path, sep="\t", index=False)
        log.info("Wrote %s", long_path)

        cfg = dict(
            domain_scores_file=str(args.domain_scores_file),
            labels_file=str(args.labels_file),
            analysis_mode=args.analysis_mode,
            positive_groups=sorted(pos_groups),
            negative_groups=sorted(neg_groups),
            b_family=b_family,
            b_family_source="config",
            n_permutations=args.n_permutations,
            n_bootstrap=args.n_bootstrap,
            alpha=args.alpha,
            seed=args.seed,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        (args.outdir / "99_domain_hypothesis_run_config.json").write_text(
            json.dumps(cfg, indent=2))
        return 0

    log.warning(
        "No --b_family_json passed; falling back to legacy ASD B1/B2/B3 "
        "hypothesis set. If you are benchmarking a non-ASD disorder this "
        "will produce wrong B-family output -- pass --b_family_json."
    )

    composite = compute_strict_composite(domain_long, strict_domains=strict_domains).rename(
        columns={"strict_composite": "value"}
    )
    social = (
        domain_long[domain_long["domain"] == b2_domain][
            ["genotype_id", "domain_support_score"]
        ].rename(columns={"domain_support_score": "value"})
    )
    comm = (
        domain_long[domain_long["domain"] == b3_domain][
            ["genotype_id", "domain_support_score"]
        ].rename(columns={"domain_support_score": "value"})
    )

    rows = []
    rows.append(run_hypothesis(
        "B1_strict_composite",
        "ASD_primary vs comparator on mean strict domain support",
        composite, "value", pos_genos, neg_genos,
        args.n_permutations, args.n_bootstrap, rng,
        family_label="B1_primary", gated_by=None,
    ))

    pos_label = "+".join(sorted(pos_groups))
    h_b2 = run_hypothesis(
        f"B2_{b2_domain}",
        f"{pos_label} vs comparator on {b2_domain} domain support",
        social, "value", pos_genos, neg_genos,
        args.n_permutations, args.n_bootstrap, rng,
        family_label="B2_B3_secondary", gated_by="B1_strict_composite",
    )
    h_b3 = run_hypothesis(
        f"B3_{b3_domain}",
        f"{pos_label} vs comparator on {b3_domain} domain support",
        comm, "value", pos_genos, neg_genos,
        args.n_permutations, args.n_bootstrap, rng,
        family_label="B2_B3_secondary", gated_by="B1_strict_composite",
    )

    holm_adj = holm_correct([h_b2["p_perm_two_sided"], h_b3["p_perm_two_sided"]])
    h_b2["p_holm_within_family"] = holm_adj[0]
    h_b3["p_holm_within_family"] = holm_adj[1]
    rows[0]["p_holm_within_family"] = float("nan")

    b1_passes = (rows[0]["p_perm_two_sided"] is not None) and (
        rows[0]["p_perm_two_sided"] < args.alpha
    ) and (rows[0]["cliffs_delta"] is not None) and (rows[0]["cliffs_delta"] > 0)
    rows[0]["decision"] = "REJECT_H0_B1" if b1_passes else "FAIL_TO_REJECT_H0_B1"
    if not b1_passes:
        h_b2["decision"] = "GATED_OUT_BY_B1"
        h_b3["decision"] = "GATED_OUT_BY_B1"
    else:
        for h in (h_b2, h_b3):
            sig = (h["p_holm_within_family"] < args.alpha) and (h["cliffs_delta"] > 0)
            h["decision"] = "REJECT_H0" if sig else "FAIL_TO_REJECT_H0"

    rows.extend([h_b2, h_b3])
    out_df = pd.DataFrame(rows)
    out_df.insert(0, "comparator_pool_label", "+".join(sorted(neg_groups)))
    out_df.insert(0, "analysis_mode", args.analysis_mode)
    out_path = args.outdir / "09_domain_hypothesis_tests.tsv"
    safe_write_csv(out_df, out_path, sep="\t", index=False)
    log.info("Wrote %s", out_path)

    blocks = []
    for label_name, df in (("strict_composite", composite),
                           ("social_interaction", social),
                           ("communication", comm)):
        d = df.copy()
        d["domain_or_composite"] = label_name
        d["group"] = np.where(
            d["genotype_id"].isin(pos_genos), "pos",
            np.where(d["genotype_id"].isin(neg_genos), "neg", "other"),
        )
        blocks.append(d)
    long_out = pd.concat(blocks, ignore_index=True)
    long_path = args.outdir / "10_domain_score_long.tsv"
    safe_write_csv(long_out, long_path, sep="\t", index=False)
    log.info("Wrote %s", long_path)

    cfg = dict(
        domain_scores_file=str(args.domain_scores_file),
        labels_file=str(args.labels_file),
        analysis_mode=args.analysis_mode,
        positive_groups=sorted(pos_groups),
        negative_groups=sorted(neg_groups),
        n_permutations=args.n_permutations,
        n_bootstrap=args.n_bootstrap,
        alpha=args.alpha,
        seed=args.seed,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
    )
    (args.outdir / "99_domain_hypothesis_run_config.json").write_text(
        json.dumps(cfg, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
