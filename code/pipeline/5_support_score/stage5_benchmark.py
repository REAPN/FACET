#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List


def load_config(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_pool_to_negative_groups(pool_id, contrasts):
    if not pool_id or not contrasts:
        return None
    for c in contrasts:
        if c.get("name") == pool_id:
            return c.get("negative_groups") or c.get("negative") or []
    return None


def build_run_config(
    cfg: Dict[str, Any],
    regime: str,
    mode: str,
    overrides: Dict[str, Any],
) -> Dict[str, Any]:
    s2c = cfg.get("stage2_candidate_features", {})
    s3 = cfg.get("stage3_aggregation", {})
    s4 = cfg.get("stage4_permutation_null", {})
    s5 = cfg["stage5_benchmark"]
    s1 = cfg.get("stage1_hpo_curation", {})

    s3_outdir = s3["outdir_template"].format(regime=regime).rstrip("/")
    s4_outdir = s4["outdir_template"].format(regime=regime).rstrip("/")
    s5_outdir = s5["outdir_template"].format(regime=regime, mode=mode).rstrip("/")

    if overrides.get("labels_file_override"):
        labels_file = overrides["labels_file_override"]
    else:
        labels_file = s5["benchmark_group_table"]

    if overrides.get("outdir_override"):
        s5_outdir = overrides["outdir_override"].format(
            regime=regime, mode=mode,
        ).rstrip("/")

    run_cfg = {
        "labels_file": labels_file,
        "hpo_targets": s1.get("outdir", "pilot_hpo_run_hybrid_v3/").rstrip("/")
            + "/07_final_resolved_hpo_terms.tsv",
        "genotype_long": s2c.get(
            "mouse_mp_csv",
            "broad_benchmark_setup/08_all_genotype_phenotypes_long_blinded.csv",
        ),
        "similarity_table_plain": s2c.get(
            "pairwise_similarity_tsv",
            "phenio-monarch-hp-mp.0.4.semsimian.tsv",
        ),
        "new_pipeline_score_col": s5.get("new_pipeline_score_col", "neg_log10_p"),
        "n_bootstrap": s5.get("n_bootstrap", 1000),
        "n_permutations": s4.get("n_permutations", 10000),
        "seed": s5.get("seed", 1),
        "stability_manifest": s5.get("stability_manifest"),
        "outdir": s5_outdir,
        "analysis_mode": mode,
        "new_pipeline_score_file": f"{s4_outdir}/04_per_genotype_pvalue.tsv",
        "domain_scores_file": f"{s3_outdir}/05_domain_support.tsv",
        "depth_assessability_file": f"{s3_outdir}/07b_per_genotype_covariates.tsv",
    }
    if overrides.get("similarity_table_ic"):
        run_cfg["similarity_table_ic"] = overrides["similarity_table_ic"]

    contrasts = s5.get("contrasts")
    if contrasts:
        run_cfg["contrasts"] = contrasts

    m_family = s5.get("m_family")
    if m_family:
        run_cfg["m_family"] = m_family

    n_mp_thresholds = overrides.get("n_mp_thresholds_override") or s5.get("n_mp_thresholds")
    if n_mp_thresholds:
        run_cfg["n_mp_thresholds"] = n_mp_thresholds
    n_mp_terms_file = overrides.get("n_mp_terms_file_override") or s5.get("n_mp_terms_file")
    if n_mp_terms_file:
        run_cfg["n_mp_terms_file"] = n_mp_terms_file

    b_family = s5.get("b_family")
    if b_family:
        run_cfg["b_family"] = b_family

        positive_label = None
        if m_family and isinstance(m_family, list) and m_family:
            positive_label = m_family[0].get("positive_label")
        if not positive_label:
            disorder_id = cfg.get("disorder", {}).get("id", "")
            if disorder_id:
                positive_label = f"{disorder_id}_primary"
        if positive_label:
            run_cfg["positive_groups"] = positive_label

        b1 = b_family[0] if b_family else None
        if isinstance(b1, dict):
            pool_ids = b1.get("comparator_pool_ids")
            pool_id_single = b1.get("comparator_pool_id")
            if pool_ids and not isinstance(pool_ids, list):
                pool_ids = [pool_ids]
            elif not pool_ids and pool_id_single:
                pool_ids = [pool_id_single]
            else:
                pool_ids = pool_ids or []
            if pool_ids and contrasts:
                union_negs = []
                token_negs = []
                seen = set()
                for pid in pool_ids:
                    negs = _resolve_pool_to_negative_groups(pid, contrasts) or []
                    for n in negs:
                        if (isinstance(n, str)
                                and n.startswith("__all_non_")
                                and n.endswith("__")):
                            token_negs.append(n)
                        elif n not in seen:
                            seen.add(n)
                            union_negs.append(n)
                if union_negs and not token_negs:
                    run_cfg["negative_groups"] = ",".join(union_negs)
                elif token_negs and not union_negs:
                    run_cfg["negative_groups_token"] = token_negs[0]
                elif union_negs and token_negs:
                    run_cfg["negative_groups"] = ",".join(union_negs)
                    run_cfg["negative_groups_token"] = token_negs[0]

    return run_cfg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=str, required=True)
    ap.add_argument("--regime", type=str, default=None,
                    choices=["off", "soft", "strict", "schema"])
    ap.add_argument("--mode", type=str, default=None,
                    choices=["strict", "broad"])
    ap.add_argument("--emit_configs_only", action="store_true",
                    help="Generate the per-run JSON configs but don't invoke "
                         "the benchmark orchestrator.")
    ap.add_argument("--config_outdir", type=str, default="benchmark",
                    help="Where to write the generated run_config_*.json files. "
                         "Default: benchmark/")
    ap.add_argument("--similarity_table_ic", type=str, default=None)
    ap.add_argument(
        "--labels_file_override", type=str, default=None,
        help="Override the disorder config's stage5_benchmark.benchmark_group_table.",
    )
    ap.add_argument(
        "--outdir_override", type=str, default=None,
        help="Override stage5_benchmark.outdir_template. "
             "Supports {regime} and {mode} placeholders.",
    )
    ap.add_argument(
        "--n_mp_thresholds_override", type=str, default=None,
        help="Override stage5_benchmark.n_mp_thresholds. Comma-separated list "
             "(e.g. '1,3,4,5,7,10'). Added 2026-05-28 for Tier 1 ASD runs — "
             "asd.disorder.json has no n_mp_thresholds field and config edits "
             "are scope-fenced under the Tier 1 brief.",
    )
    ap.add_argument(
        "--n_mp_terms_file_override", type=str, default=None,
        help="Override stage5_benchmark.n_mp_terms_file (universe-wide phenotype "
             "long table that feeds the depth sweep). Pair with "
             "--n_mp_thresholds_override.",
    )
    ap.add_argument("--skip_baselines", action="store_true")
    ap.add_argument("--skip_b2", action="store_true")
    ap.add_argument("--reuse_existing", action="store_true")
    ap.add_argument("--dry_run", action="store_true")
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    disorder_id = cfg["disorder"]["id"]
    s3 = cfg.get("stage3_aggregation", {})

    regimes = ([args.regime] if args.regime
               else list(s3.get("polarity_regimes_to_run", ["off"])))
    modes = ([args.mode] if args.mode else ["strict", "broad"])

    n_mp_thresholds_override = None
    if args.n_mp_thresholds_override:
        n_mp_thresholds_override = [
            int(x.strip()) for x in args.n_mp_thresholds_override.split(",") if x.strip()
        ]
    overrides = {
        "similarity_table_ic":       args.similarity_table_ic,
        "labels_file_override":      args.labels_file_override,
        "outdir_override":           args.outdir_override,
        "n_mp_thresholds_override":  n_mp_thresholds_override,
        "n_mp_terms_file_override":  args.n_mp_terms_file_override,
    }

    print(f"=== stage5_benchmark: disorder={disorder_id} ===")
    print(f"  regimes x modes: {len(regimes)} x {len(modes)} = "
          f"{len(regimes) * len(modes)} runs")
    print()

    config_outdir = Path(args.config_outdir)
    config_outdir.mkdir(parents=True, exist_ok=True)

    rc = 0
    for regime in regimes:
        for mode in modes:
            print(f"\n--- regime={regime}, mode={mode} ---")
            run_cfg = build_run_config(cfg, regime, mode, overrides)
            config_path = config_outdir / f"run_config_v3_pol{regime}_{mode}.json"
            config_path.write_text(
                json.dumps(run_cfg, indent=2), encoding="utf-8",
            )
            print(f"  wrote: {config_path}")
            print(f"  outdir: {run_cfg['outdir']}")

            if args.emit_configs_only:
                continue

            cmd: List[str] = [
                sys.executable, "benchmark/run_benchmarks.py",
                "--config", str(config_path),
            ]
            if args.skip_baselines:
                cmd.append("--skip_baselines")
            if args.skip_b2:
                cmd.append("--skip_b2")
            if args.reuse_existing:
                cmd.append("--reuse_existing")
            if args.dry_run:
                cmd.append("--dry_run")

            print(f"  cmd: {' '.join(cmd)}")
            result = subprocess.run(cmd)
            if result.returncode != 0:
                print(f"  FAILED with rc={result.returncode}")
                rc = result.returncode

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
