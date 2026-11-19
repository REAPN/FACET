#!/usr/bin/env python3
"""permutation_null_per_genotype.py
================================
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("perm_null")


DEFAULT_STRICT_DOMAINS = {"social_interaction", "communication",
                          "repetitive_restricted", "sensory_reactivity"}
DEFAULT_BROAD_DOMAINS = DEFAULT_STRICT_DOMAINS | {"developmental_support",
                                                  "cognitive_behavioral_support",
                                                  "motor_support"}
DEFAULT_ALLOWED_EVIDENCE_SCOPE_STRICT = {"organism_behavior", "organism_sensory",
                                          "developmental_behavior"}
DEFAULT_ALLOWED_EVIDENCE_SCOPE_BROAD = (DEFAULT_ALLOWED_EVIDENCE_SCOPE_STRICT
                                         | {"unclear"})
STRONG_ANALOG = {"direct_analog", "close_support"}

STRICT_DOMAINS = DEFAULT_STRICT_DOMAINS
BROAD_DOMAINS = DEFAULT_BROAD_DOMAINS
ALLOWED_EVIDENCE_SCOPE_STRICT = DEFAULT_ALLOWED_EVIDENCE_SCOPE_STRICT
ALLOWED_EVIDENCE_SCOPE_BROAD = DEFAULT_ALLOWED_EVIDENCE_SCOPE_BROAD


def noisy_or(scores: np.ndarray) -> float:
    vals = scores[(~np.isnan(scores)) & (scores > 0)]
    if vals.size == 0:
        return 0.0
    prod = float(np.prod(1.0 - np.clip(vals, 0.0, 1.0)))
    return 1.0 - prod


def build_lookups(rer: pd.DataFrame,
                  scope_strict: set = None,
                  scope_broad: set = None,
                  ) -> Tuple[Dict, Dict, Dict, np.ndarray, List[str], pd.DataFrame]:
    if scope_strict is None:
        scope_strict = DEFAULT_ALLOWED_EVIDENCE_SCOPE_STRICT
    if scope_broad is None:
        scope_broad = DEFAULT_ALLOWED_EVIDENCE_SCOPE_BROAD

    rer = rer.copy()
    rer["strict_eligible"] = rer["strict_eligible"].fillna(False)
    rer["broad_eligible"] = rer["broad_eligible"].fillna(False)
    rer["comparable_observable"] = rer["comparable_observable"].fillna(False)
    rer["evidence_scope"] = rer["evidence_scope"].fillna("unclear").astype(str)
    rer["behavioral_analog_type"] = rer["behavioral_analog_type"].fillna("").astype(str)

    in_strict_scope = rer["evidence_scope"].isin(scope_strict)
    in_broad_scope = rer["evidence_scope"].isin(scope_broad)
    strong_analog = rer["behavioral_analog_type"].isin(STRONG_ANALOG)

    rer["strict_assessable"] = (rer["comparable_observable"].astype(bool)
                                & in_strict_scope)
    rer["broad_assessable"] = (rer["comparable_observable"].astype(bool)
                               & in_broad_scope)

    rer["strict_cand"] = (rer["strict_eligible"].astype(bool)
                          & rer["comparable_observable"].astype(bool)
                          & in_strict_scope
                          & strong_analog)
    rer["broad_cand"] = (rer["broad_eligible"].astype(bool)
                         & rer["comparable_observable"].astype(bool)
                         & in_broad_scope)

    rer["in_strict_scope_no_candidate"] = (rer["strict_assessable"]
                                           & ~rer["strict_cand"])
    rer["in_broad_scope_no_candidate"] = (rer["broad_assessable"]
                                          & ~rer["broad_cand"])

    target_domain = (rer.drop_duplicates("target_id")
                        .set_index("target_id")["human_domain"].to_dict())
    targets = list(target_domain.keys())
    n_targets = len(targets)
    t_to_idx = {t: i for i, t in enumerate(targets)}
    t_domain_arr = np.array([target_domain[t] for t in targets])

    mp_lookup: Dict[str, List[Tuple[int, float, bool, bool, bool, bool]]] = defaultdict(list)
    keep = (rer["strict_cand"] | rer["broad_cand"]
            | rer["strict_assessable"] | rer["broad_assessable"])
    for _, r in rer[keep].iterrows():
        mp_lookup[str(r["mp_id"])].append(
            (t_to_idx[r["target_id"]],
             float(r["final_pair_score"]),
             bool(r["strict_cand"]),
             bool(r["broad_cand"]),
             bool(r["strict_assessable"]),
             bool(r["broad_assessable"]))
        )
    return mp_lookup, target_domain, t_to_idx, t_domain_arr, targets, rer


def support_score(mp_ids: List[str], mp_lookup: Dict, t_domain_arr: np.ndarray,
                  n_targets: int, mode: str,
                  domains_strict: set = None,
                  domains_broad: set = None,
                  ) -> Tuple[float, int]:
    if domains_strict is None:
        domains_strict = DEFAULT_STRICT_DOMAINS
    if domains_broad is None:
        domains_broad = DEFAULT_BROAD_DOMAINS

    domains_set = domains_strict if mode == "strict" else domains_broad
    cand_idx = 2 if mode == "strict" else 3
    assess_idx = 4 if mode == "strict" else 5

    per_target_cand_scores: Dict[int, List[float]] = defaultdict(list)
    assessable_targets: set = set()
    for mp in mp_ids:
        if mp in mp_lookup:
            for entry in mp_lookup[mp]:
                tidx = entry[0]
                if entry[assess_idx]:
                    assessable_targets.add(tidx)
                    if entry[cand_idx]:
                        per_target_cand_scores[tidx].append(entry[1])
    if not assessable_targets:
        return 0.0, 0

    target_score: Dict[int, float] = {}
    for tidx in assessable_targets:
        scores = per_target_cand_scores.get(tidx)
        if scores:
            target_score[tidx] = noisy_or(np.array(scores))
        else:
            target_score[tidx] = 0.0

    domain_scores: Dict[str, List[float]] = defaultdict(list)
    for tidx, s in target_score.items():
        d = t_domain_arr[tidx]
        if d in domains_set:
            domain_scores[d].append(s)
    if not domain_scores:
        return 0.0, 0
    return (float(np.mean([np.mean(v) for v in domain_scores.values()])),
            len(domain_scores))


def build_null(universe: np.ndarray, depths: List[int], mp_lookup: Dict,
               t_domain_arr: np.ndarray, n_targets: int,
               n_perm: int, seed: int,
               domains_strict: set = None,
               domains_broad: set = None,
               ) -> Dict[Tuple[str, int], np.ndarray]:
    if domains_strict is None:
        domains_strict = DEFAULT_STRICT_DOMAINS
    if domains_broad is None:
        domains_broad = DEFAULT_BROAD_DOMAINS
    rng = np.random.default_rng(seed)
    out: Dict[Tuple[str, int], np.ndarray] = {}
    for mode in ("strict", "broad"):
        log.info("Building null for mode=%s ...", mode)
        for k in depths:
            if k <= 0 or k > universe.size:
                continue
            scores = np.zeros(n_perm, dtype=float)
            for i in range(n_perm):
                sampled = rng.choice(universe, size=k, replace=False)
                s, _ = support_score(sampled.tolist(), mp_lookup,
                                     t_domain_arr, n_targets, mode,
                                     domains_strict=domains_strict,
                                     domains_broad=domains_broad)
                scores[i] = s
            out[(mode, k)] = scores
            n_nonzero = int((scores > 0).sum())
            log.info("  k=%d: max=%.3f, mean=%.4f, %d/%d non-zero (%.2f%%)",
                     k, scores.max() if scores.size else 0,
                     scores.mean() if scores.size else 0,
                     n_nonzero, n_perm, 100 * n_nonzero / max(1, n_perm))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reranked_pairs_tsv", type=str,
                    default="asd_pair_rerank_v3_broad_v3/03_reranked_pairs_filled.tsv")
    ap.add_argument("--overall_support_tsv", type=str,
                    default="asd_support_aggregated_broad_v3_rigorous/06_overall_genotype_support.tsv")
    ap.add_argument("--mouse_mp_csv", type=str,
                    default="broad_benchmark_setup/08_all_genotype_phenotypes_long_blinded.csv")
    ap.add_argument("--n_permutations", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--max_depth_cap", type=int, default=200,
                    help=("Genotypes with more MP terms than this cap reuse the "
                          "null from the cap. Most random k-draws above this size "
                          "saturate (every random draw hits at least one candidate-"
                          "pool MP), so the null becomes flat."))
    ap.add_argument("--outdir", type=str, default="asd_pvalue_broad_v3")

    def _csv(s): return [x.strip() for x in s.split(",") if x.strip()]
    ap.add_argument("--strict_domains", type=str, default=None,
                    help=("Comma-separated domain names that count toward the "
                          "strict null. If omitted, falls back to "
                          "DEFAULT_STRICT_DOMAINS (ASD's 4)."))
    ap.add_argument("--broad_domains", type=str, default=None,
                    help=("Comma-separated domain names for the broad null. "
                          "If omitted, falls back to DEFAULT_BROAD_DOMAINS "
                          "(ASD strict + developmental/cognitive/motor support)."))
    ap.add_argument("--allowed_evidence_scope_strict", type=str, default=None,
                    help=("Comma-separated evidence_scope tokens admitted to "
                          "the strict null. If omitted, ASD defaults."))
    ap.add_argument("--allowed_evidence_scope_broad", type=str, default=None,
                    help=("Comma-separated evidence_scope tokens admitted to "
                          "the broad null. If omitted, ASD defaults."))
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    domains_strict = (set(_csv(args.strict_domains))
                      if args.strict_domains else DEFAULT_STRICT_DOMAINS)
    domains_broad = (set(_csv(args.broad_domains))
                     if args.broad_domains else DEFAULT_BROAD_DOMAINS)
    scope_strict = (set(_csv(args.allowed_evidence_scope_strict))
                    if args.allowed_evidence_scope_strict
                    else DEFAULT_ALLOWED_EVIDENCE_SCOPE_STRICT)
    scope_broad = (set(_csv(args.allowed_evidence_scope_broad))
                   if args.allowed_evidence_scope_broad
                   else DEFAULT_ALLOWED_EVIDENCE_SCOPE_BROAD)
    log.info("Domain sets: strict=%d, broad=%d | scope: strict=%d, broad=%d",
             len(domains_strict), len(domains_broad),
             len(scope_strict), len(scope_broad))

    log.info("Loading %s", args.reranked_pairs_tsv)
    rer = pd.read_csv(args.reranked_pairs_tsv, sep="\t", low_memory=False)
    log.info("  %d reranked pairs", len(rer))
    mp_lookup, target_domain, t_to_idx, t_domain_arr, targets, rer = build_lookups(
        rer, scope_strict=scope_strict, scope_broad=scope_broad,
    )
    n_targets = len(targets)
    log.info("  unique candidate-pool MP ids: %d, %d targets", len(mp_lookup), n_targets)

    audit = rer[["target_id", "hpo_label", "mp_id", "mp_label", "human_domain",
                 "strict_eligible", "broad_eligible", "comparable_observable",
                 "evidence_scope", "behavioral_analog_type", "final_pair_score",
                 "strict_cand", "broad_cand",
                 "strict_assessable", "broad_assessable",
                 "in_strict_scope_no_candidate",
                 "in_broad_scope_no_candidate"]].copy()
    audit.to_csv(outdir / "01_per_pair_eligibility.tsv", sep="\t", index=False)

    log.info("Loading %s", args.mouse_mp_csv)
    mlong = pd.read_csv(args.mouse_mp_csv, sep="," if args.mouse_mp_csv.endswith(".csv") else "\t",
                        usecols=["genotype_id", "mp_id"], low_memory=False)
    universe = mlong["mp_id"].astype(str).unique()
    log.info("  universe MP ids: %d", universe.size)
    depth_per_gen = mlong.groupby("genotype_id")["mp_id"].nunique().rename("depth_k")
    depth_capped = depth_per_gen.clip(upper=args.max_depth_cap)
    depth_capped.to_csv(outdir / "02_genotype_depths.tsv", sep="\t", header=True)
    unique_depths = sorted(depth_capped.unique().tolist())
    log.info("  per-genotype depth: min=%d, median=%d, max=%d (capped at %d)",
             depth_per_gen.min(), int(depth_per_gen.median()), depth_per_gen.max(),
             args.max_depth_cap)
    log.info("  %d unique depth strata to permute", len(unique_depths))

    log.info("Building empirical null with N=%d per (mode, depth)", args.n_permutations)
    null = build_null(universe, unique_depths, mp_lookup, t_domain_arr, n_targets,
                      args.n_permutations, args.seed,
                      domains_strict=domains_strict,
                      domains_broad=domains_broad)

    null_rows = []
    for (mode, k), scores in null.items():
        null_rows.append({
            "analysis_mode": mode,
            "depth_k": k,
            "n_perm": len(scores),
            "null_mean": float(scores.mean()),
            "null_sd": float(scores.std(ddof=0)),
            "null_p50": float(np.percentile(scores, 50)),
            "null_p95": float(np.percentile(scores, 95)),
            "null_p99": float(np.percentile(scores, 99)),
            "null_max": float(scores.max()),
            "null_pct_zero": float(100 * (scores == 0).mean()),
        })
    pd.DataFrame(null_rows).to_csv(outdir / "03_null_distribution_per_depth.tsv",
                                    sep="\t", index=False)

    log.info("Loading %s", args.overall_support_tsv)
    ov = pd.read_csv(args.overall_support_tsv, sep="\t", low_memory=False)
    ov["depth_k"] = ov["genotype_id"].map(depth_capped).fillna(0).astype(int)
    log.info("  overall_support rows: %d, with non-NaN score: %d",
             len(ov), ov["overall_support_score"].notna().sum())

    if "matched_sfari_genes" in ov.columns:
        has_match = (ov["matched_sfari_genes"].notna()
                     & ov["matched_sfari_genes"].astype(str).str.strip().ne(""))
        ov = ov.assign(_has_match=has_match.astype(int))
    else:
        ov = ov.assign(_has_match=0)
    before = len(ov)
    ov = (ov.sort_values(["_has_match", "overall_support_score"],
                         ascending=[False, False], na_position="last")
            .drop_duplicates(subset=["genotype_id", "analysis_mode"], keep="first")
            .drop(columns=["_has_match"]))
    after = len(ov)
    log.info("  deduplicated overall_support to one row per (genotype_id, "
             "analysis_mode): %d -> %d rows (dropped %d duplicate "
             "SFARI-match/unmatched twins; kept SFARI-matched row when present)",
             before, after, before - after)

    out_rows = []
    for _, r in ov.iterrows():
        gid = r["genotype_id"]
        mode = r["analysis_mode"]
        obs = r["overall_support_score"]
        k = int(r["depth_k"])
        if k == 0:
            continue
        null_arr = null.get((mode, k))
        if null_arr is None:
            continue
        if pd.isna(obs):
            obs_use = 0.0
        else:
            obs_use = float(obs)
        n_ge = int((null_arr >= obs_use).sum())
        p = (1 + n_ge) / (len(null_arr) + 1)
        nlog10p = -float(np.log10(p))
        pct = 100.0 * (1.0 - n_ge / len(null_arr))
        out_rows.append({
            "genotype_id": gid,
            "matched_sfari_genes": r.get("matched_sfari_genes", ""),
            "analysis_mode": mode,
            "depth_k": k,
            "observed_score": obs_use,
            "p_value": p,
            "neg_log10_p": nlog10p,
            "percentile_rank": pct,
            "null_p95": float(np.percentile(null_arr, 95)),
            "null_max": float(null_arr.max()),
        })

    out_df = pd.DataFrame(out_rows)
    out_df.to_csv(outdir / "04_per_genotype_pvalue.tsv", sep="\t", index=False)
    log.info("Wrote 04_per_genotype_pvalue.tsv: %d rows", len(out_df))

    config = {
        "reranked_pairs_tsv": args.reranked_pairs_tsv,
        "overall_support_tsv": args.overall_support_tsv,
        "mouse_mp_csv": args.mouse_mp_csv,
        "n_permutations": args.n_permutations,
        "seed": args.seed,
        "max_depth_cap": args.max_depth_cap,
        "strict_domains": sorted(domains_strict),
        "broad_domains": sorted(domains_broad),
        "allowed_evidence_scope_strict": sorted(scope_strict),
        "allowed_evidence_scope_broad": sorted(scope_broad),
        "domain_source": ("CLI-provided" if args.strict_domains
                          else "module-default (ASD)"),
        "elapsed_seconds": round(time.time() - t0, 1),
        "method": ("Empirical permutation null per depth: replaces rarefaction. "
                   "Strict gate enforces Strategy B (analog ∈ {direct, close}); "
                   "broad gate uses score-assisted broad eligibility. "
                   "Score function mirrors aggregate_support_clustered_broad "
                   "(per-domain mean over assessable targets including zeros, "
                   "per-overall mean over assessable domains). Faithfulness fix "
                   "landed 2026-05-14; pre-fix null averaged hit-only targets, "
                   "producing a conservative bias on p-values. See lab notebook "
                   "entry 'Stage 3 ↔ Stage 4 score-function inconsistency'."),
        "score_function_fix_version": "2026-05-14",
    }
    (outdir / "05_run_config.json").write_text(json.dumps(config, indent=2))
    log.info("Done in %.1fs. Outputs at %s", time.time() - t0, outdir.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
