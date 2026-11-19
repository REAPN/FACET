#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import aggregate_support_clustered_broad as A


def load_config(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def configure_module_from_config(cfg: Dict[str, Any]) -> None:
    strict_raw = cfg.get("domains", {}).get("strict")
    if strict_raw:
        strict = [d["name"] if isinstance(d, dict) else d for d in strict_raw]
        A.STRICT_DOMAINS = list(strict)
    broad_extras = cfg.get("domains", {}).get("broad_extras")
    if broad_extras is not None:
        A.BROAD_EXTRA_DOMAINS = list(broad_extras)
    if strict_raw or broad_extras:
        A.BROAD_DOMAINS = list(A.STRICT_DOMAINS) + list(getattr(A, "BROAD_EXTRA_DOMAINS", []))

    s3 = cfg.get("stage3_aggregation", {})
    scope_strict = s3.get("allowed_evidence_scope_strict")
    if scope_strict:
        A.ALLOWED_EVIDENCE_SCOPE_STRICT = set(scope_strict)
    scope_broad = s3.get("allowed_evidence_scope_broad")
    if scope_broad:
        A.ALLOWED_EVIDENCE_SCOPE_BROAD = set(scope_broad)


def build_argv_for_regime(
    cfg: Dict[str, Any],
    regime: str,
    overrides: Dict[str, Any],
) -> List[str]:
    s3 = cfg["stage3_aggregation"]
    s2r_outdir = cfg["stage2_rerank"]["outdir"].rstrip("/")
    rerank_default = f"{s2r_outdir}/03_reranked_pairs_filled.tsv"
    reranked_tsv = overrides.get("reranked_pairs_tsv") or rerank_default
    mouse_mp = (
        overrides.get("mouse_mp_csv")
        or cfg["stage2_candidate_features"].get(
            "mouse_mp_csv",
            "broad_benchmark_setup/08_all_genotype_phenotypes_long_blinded.csv",
        )
    )

    outdir_template = overrides.get("outdir_template") or s3["outdir_template"]
    outdir = outdir_template.format(regime=regime).rstrip("/")

    argv = [
        "aggregate_support_clustered_broad.py",
        "--reranked_pairs_tsv", reranked_tsv,
        "--mouse_mp_csv", mouse_mp,
        "--support_threshold", str(s3.get("support_threshold", 0.30)),
        "--lexical_cluster_threshold", str(s3.get("lexical_cluster_threshold", 0.65)),
        "--eligibility_mode", s3.get("eligibility_mode", "score_assisted_broad"),
        "--broad_score_threshold", str(s3.get("broad_score_threshold", 0.57)),
        "--strict_score_threshold", str(s3.get("strict_score_threshold", 0.62)),
        "--strict_analog_gate", s3.get("strict_analog_gate", "strong"),
        "--overall_aggregator", s3.get("overall_aggregator", "mean"),
        "--polarity_mode", regime,
        "--outdir", outdir,
    ]

    taxonomy = overrides.get("taxonomy_tsv") or cfg["stage2_candidate_features"].get(
        "taxonomy_tsv", "mp_term_taxonomy_broad_v3/03_mp_term_taxonomy.tsv",
    )
    argv += ["--taxonomy_tsv", taxonomy]

    polarity_schema_tsv = (
        overrides.get("polarity_schema_tsv")
        or cfg.get("stage3_aggregation", {}).get(
            "polarity_schema_tsv", "polarity_schema_v1/01_term_annotations.tsv"
        )
    )
    argv += ["--polarity_schema_tsv", polarity_schema_tsv]
    return argv


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=str, required=True)
    ap.add_argument("--regime", type=str, default=None,
                    choices=["off", "soft", "strict", "schema"],
                    help="Run only this polarity regime. If omitted, run "
                         "all regimes listed in stage3_aggregation.polarity_regimes_to_run.")
    ap.add_argument("--outdir_template", type=str, default=None,
                    help="Override stage3_aggregation.outdir_template. Must "
                         "contain '{regime}'.")
    ap.add_argument("--reranked_pairs_tsv", type=str, default=None)
    ap.add_argument("--mouse_mp_csv", type=str, default=None)
    ap.add_argument("--taxonomy_tsv", type=str, default=None)
    ap.add_argument("--polarity_schema_tsv", type=str, default=None)
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    disorder_id = cfg["disorder"]["id"]
    s3 = cfg["stage3_aggregation"]

    configure_module_from_config(cfg)

    regimes = ([args.regime] if args.regime
               else list(s3.get("polarity_regimes_to_run", ["off"])))

    print(f"=== stage3_aggregate: disorder={disorder_id} ===")
    print(f"  regimes to run: {regimes}")
    print(f"  STRICT_DOMAINS: {A.STRICT_DOMAINS}")
    print(f"  BROAD_DOMAINS: {A.BROAD_DOMAINS}")
    print()

    overrides = {
        "outdir_template": args.outdir_template,
        "reranked_pairs_tsv": args.reranked_pairs_tsv,
        "mouse_mp_csv": args.mouse_mp_csv,
        "taxonomy_tsv": args.taxonomy_tsv,
        "polarity_schema_tsv": args.polarity_schema_tsv,
    }

    rc = 0
    for regime in regimes:
        new_argv = build_argv_for_regime(cfg, regime, overrides)
        print(f"\n--- regime={regime} ---")
        print(f"  outdir: {new_argv[new_argv.index('--outdir') + 1]}")
        sys.argv = new_argv
        rc_i = A.main()
        if rc_i != 0:
            rc = rc_i
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
