#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import permutation_null_per_genotype as P


def load_config(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _domain_names(cfg: Dict[str, Any]) -> List[str]:
    raw = cfg.get("domains", {}).get("strict", [])
    return [d["name"] if isinstance(d, dict) else d for d in raw]


def _broad_extra_names(cfg: Dict[str, Any]) -> List[str]:
    raw = cfg.get("domains", {}).get("broad_extras", [])
    return [d["name"] if isinstance(d, dict) else d for d in raw]


def build_argv_for_regime(
    cfg: Dict[str, Any],
    regime: str,
    overrides: Dict[str, Any],
) -> List[str]:
    s3 = cfg["stage3_aggregation"]
    s4 = cfg["stage4_permutation_null"]
    s2r_outdir = cfg["stage2_rerank"]["outdir"].rstrip("/")
    s3_outdir_template = s3["outdir_template"]
    s4_outdir_template = overrides.get("outdir_template") or s4["outdir_template"]

    if overrides.get("stage3_baseline"):
        baseline_dir = Path(overrides["stage3_baseline"])
        s3_outdir = baseline_dir / s3_outdir_template.format(regime=regime).rstrip("/")
    else:
        s3_outdir = Path(s3_outdir_template.format(regime=regime).rstrip("/"))
    overall_tsv = (
        overrides.get("overall_support_tsv")
        or str(s3_outdir / "06_overall_genotype_support.tsv")
    )

    if overrides.get("reranked_pairs_tsv"):
        reranked = overrides["reranked_pairs_tsv"]
    elif overrides.get("stage3_baseline"):
        baseline_dir = Path(overrides["stage3_baseline"])
        candidate = baseline_dir / f"{s2r_outdir}/03_reranked_pairs_filled.tsv"
        reranked = str(candidate) if candidate.exists() else f"{s2r_outdir}/03_reranked_pairs_filled.tsv"
    else:
        reranked = f"{s2r_outdir}/03_reranked_pairs_filled.tsv"

    mouse_mp = (
        overrides.get("mouse_mp_csv")
        or cfg["stage2_candidate_features"].get(
            "mouse_mp_csv",
            "broad_benchmark_setup/08_all_genotype_phenotypes_long_blinded.csv",
        )
    )

    outdir = s4_outdir_template.format(regime=regime).rstrip("/")

    argv = [
        "permutation_null_per_genotype.py",
        "--reranked_pairs_tsv", reranked,
        "--overall_support_tsv", overall_tsv,
        "--mouse_mp_csv", mouse_mp,
        "--n_permutations", str(s4.get("n_permutations", 10000)),
        "--seed", str(s4.get("seed", 1)),
        "--max_depth_cap", str(s4.get("max_depth_cap", 200)),
        "--outdir", outdir,
    ]

    strict_names = _domain_names(cfg)
    if strict_names:
        broad_extras = _broad_extra_names(cfg)
        broad_names = strict_names + broad_extras
        argv += [
            "--strict_domains", ",".join(strict_names),
            "--broad_domains", ",".join(broad_names),
        ]

    scope_strict = s3.get("allowed_evidence_scope_strict")
    if scope_strict:
        argv += ["--allowed_evidence_scope_strict", ",".join(scope_strict)]
    scope_broad = s3.get("allowed_evidence_scope_broad")
    if scope_broad:
        argv += ["--allowed_evidence_scope_broad", ",".join(scope_broad)]

    return argv


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=str, required=True)
    ap.add_argument("--regime", type=str, default=None,
                    choices=["off", "soft", "strict", "schema"])
    ap.add_argument("--outdir_template", type=str, default=None)
    ap.add_argument("--reranked_pairs_tsv", type=str, default=None)
    ap.add_argument("--overall_support_tsv", type=str, default=None)
    ap.add_argument("--mouse_mp_csv", type=str, default=None)
    ap.add_argument("--stage3_baseline", type=str, default=None,
                    help="Use Stage 3 outputs from this baseline dir (for parity testing) "
                         "instead of canonical pipeline paths.")
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    disorder_id = cfg["disorder"]["id"]
    s3 = cfg["stage3_aggregation"]
    regimes = ([args.regime] if args.regime
               else list(s3.get("polarity_regimes_to_run", ["off"])))

    overrides: Dict[str, Any] = {
        "outdir_template": args.outdir_template,
        "reranked_pairs_tsv": args.reranked_pairs_tsv,
        "overall_support_tsv": args.overall_support_tsv,
        "mouse_mp_csv": args.mouse_mp_csv,
        "stage3_baseline": args.stage3_baseline,
    }

    print(f"=== stage4_permutation_null: disorder={disorder_id} ===")
    print(f"  regimes to run: {regimes}")
    print()

    rc = 0
    for regime in regimes:
        new_argv = build_argv_for_regime(cfg, regime, overrides)
        print(f"\n--- regime={regime} ---")
        print(f"  overall_support_tsv: {new_argv[new_argv.index('--overall_support_tsv') + 1]}")
        print(f"  outdir:              {new_argv[new_argv.index('--outdir') + 1]}")
        sys.argv = new_argv
        rc_i = P.main()
        if rc_i:
            rc = rc_i
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
