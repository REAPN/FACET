#!/usr/bin/env python3
"""run_benchmarks.py
=================

Usage
-----
    python run_benchmarks.py --config benchmark/run_config.json
    python run_benchmarks.py --config <cfg> --dry_run
    python run_benchmarks.py --config <cfg> --reuse_existing
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shlex
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd


from safe_write_util import safe_write_csv
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("orchestrator")


HERE = Path(__file__).resolve().parent


def hash_file(path: Path) -> str:
    if not path.exists():
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def run(cmd, dry_run: bool) -> int:
    line = " ".join(shlex.quote(c) for c in cmd)
    log.info("$ %s", line)
    if dry_run:
        return 0
    rc = subprocess.call(cmd)
    if rc != 0:
        log.error("Command failed (exit %d): %s", rc, line)
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--dry_run", action="store_true")
    ap.add_argument("--reuse_existing", action="store_true")
    ap.add_argument("--skip_baselines", action="store_true",
                    help="Skip baseline scoring (assume already done).")
    ap.add_argument("--skip_b2", action="store_true",
                    help="Skip the B2 IC-weighted Phenodigm baseline.")
    args = ap.parse_args()

    cfg = json.loads(args.config.read_text())
    outdir = Path(cfg["outdir"])
    outdir.mkdir(parents=True, exist_ok=True)
    manifest_rows = []
    t0 = time.time()

    python_exe = sys.executable

    cfg_mode = cfg.get("analysis_mode")
    score_path = cfg["new_pipeline_score_file"]
    if cfg_mode in ("strict", "broad"):
        try:
            sf = pd.read_csv(score_path, sep="\t" if score_path.endswith(".tsv") else ",",
                             low_memory=False)
        except Exception as e:
            log.error("Could not read new_pipeline_score_file %s: %s", score_path, e)
            return 1
        if "analysis_mode" in sf.columns:
            n_before = len(sf)
            sf_mode = sf[sf["analysis_mode"] == cfg_mode].copy()
            n_after = len(sf_mode)
            filtered = outdir / f"00_score_filtered_{cfg_mode}.tsv"
            safe_write_csv(sf_mode, filtered, sep="\t", index=False)
            log.info("Filtered new_pipeline_score_file by analysis_mode=%s: %d -> %d rows",
                     cfg_mode, n_before, n_after)
            cfg["new_pipeline_score_file"] = str(filtered)
            score_path = str(filtered)
            manifest_rows.append(dict(stage="filter", artifact=str(filtered),
                                      hash=hash_file(filtered)))
        else:
            log.warning("Config analysis_mode=%s but score file has no 'analysis_mode' column.",
                        cfg_mode)
        if "domain_analysis_mode" not in cfg:
            cfg["domain_analysis_mode"] = cfg_mode

    baseline_dir = outdir / "baseline_scores"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    b1_out = baseline_dir / "01_baseline_genotype_scores__B1_phenodigm_plain.tsv"
    b2_out = baseline_dir / "01_baseline_genotype_scores__B2_phenodigm_ic.tsv"

    if not args.skip_baselines:
        if not (args.reuse_existing and b1_out.exists()):
            cmd = [
                python_exe, str(HERE / "score_baseline_phenodigm_broad.py"),
                "--hpo_targets", cfg["hpo_targets"],
                "--genotype_long", cfg["genotype_long"],
                "--similarity_table", cfg["similarity_table_plain"],
                "--similarity_column", "phenodigm_score",
                "--baseline_label", "B1_phenodigm_plain",
                "--outdir", str(baseline_dir),
            ]
            if run(cmd, args.dry_run) != 0:
                return 1
            manifest_rows.append(dict(stage="baseline_B1", artifact=str(b1_out),
                                       hash=hash_file(b1_out)))
        if not args.skip_b2 and not (args.reuse_existing and b2_out.exists()):
            sim_ic = cfg.get("similarity_table_ic")
            if sim_ic and Path(sim_ic).exists():
                cmd = [
                    python_exe, str(HERE / "score_baseline_phenodigm_broad.py"),
                    "--hpo_targets", cfg["hpo_targets"],
                    "--genotype_long", cfg["genotype_long"],
                    "--similarity_table", sim_ic,
                    "--similarity_column", "phenodigm_score",
                    "--baseline_label", "B2_phenodigm_ic",
                    "--outdir", str(baseline_dir),
                ]
                if run(cmd, args.dry_run) != 0:
                    return 1
                manifest_rows.append(dict(stage="baseline_B2", artifact=str(b2_out),
                                           hash=hash_file(b2_out)))
            else:
                print("[run_benchmarks] B2 skipped: similarity_table_ic missing/null in config.")

    contrasts_sidecar = None
    if cfg.get("contrasts"):
        contrasts_sidecar = outdir / "00_contrasts.json"
        with open(contrasts_sidecar, "w", encoding="utf-8") as f:
            json.dump(cfg["contrasts"], f, indent=2)
        log.info("Wrote contrasts sidecar: %s (%d contrasts)",
                 contrasts_sidecar, len(cfg["contrasts"]))

    m_family_sidecar = None
    if cfg.get("m_family"):
        m_family_sidecar = outdir / "00_m_family.json"
        with open(m_family_sidecar, "w", encoding="utf-8") as f:
            json.dump(cfg["m_family"], f, indent=2)
        log.info("Wrote m_family sidecar: %s (%d models)",
                 m_family_sidecar, len(cfg["m_family"]))

    b_family_sidecar = None
    if cfg.get("b_family"):
        b_family_sidecar = outdir / "00_b_family.json"
        with open(b_family_sidecar, "w", encoding="utf-8") as f:
            json.dump(cfg["b_family"], f, indent=2)
        log.info("Wrote b_family sidecar: %s (%d entries)",
                 b_family_sidecar, len(cfg["b_family"]))

    if cfg.get("negative_groups_token"):
        import re as _re
        token = cfg["negative_groups_token"]
        m = _re.fullmatch(r"__all_non_([A-Za-z0-9_]+)__", token)
        if m:
            try:
                labels_df = pd.read_csv(cfg["labels_file"], low_memory=False)
                target_bg = m.group(1)
                universe = sorted(set(labels_df["benchmark_group"].dropna()
                                       .astype(str)) - {target_bg})
                existing = cfg.get("negative_groups", "")
                if existing:
                    cur = [s.strip() for s in existing.split(",") if s.strip()]
                    combined = sorted(set(cur) | set(universe))
                    cfg["negative_groups"] = ",".join(combined)
                else:
                    cfg["negative_groups"] = ",".join(universe)
                log.info("Expanded negative_groups token %s -> %d groups",
                         token, len(universe))
            except Exception as e:
                log.warning("Could not expand negative_groups token %s: %s", token, e)

    metrics_dir = outdir / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    metrics_out = metrics_dir / "03_metrics_per_contrast.tsv"

    new_score_arg = (
        f"new_pipeline::{cfg['new_pipeline_score_file']}"
        + (f"::{cfg.get('new_pipeline_score_col', '')}"
           if cfg.get("new_pipeline_score_col") else "")
    )

    if not (args.reuse_existing and metrics_out.exists()):
        cmd = [
            python_exe, str(HERE / "compute_benchmark_metrics.py"),
            "--score_file", new_score_arg,
            "--score_file", f"B1_phenodigm_plain::{b1_out}::bma_score",
        ]
        if not args.skip_b2 and b2_out.exists():
            cmd += ["--score_file", f"B2_phenodigm_ic::{b2_out}::bma_score"]
        cmd += [
            "--labels_file", cfg["labels_file"],
            "--outdir", str(metrics_dir),
            "--n_bootstrap", str(cfg.get("n_bootstrap", 1000)),
            "--seed", str(cfg.get("seed", 1)),
        ]
        if contrasts_sidecar:
            cmd += ["--contrasts_json", str(contrasts_sidecar)]
        if cfg.get("n_mp_thresholds"):
            thr_str = (",".join(str(int(k)) for k in cfg["n_mp_thresholds"])
                       if isinstance(cfg["n_mp_thresholds"], (list, tuple))
                       else str(cfg["n_mp_thresholds"]))
            cmd += ["--n_mp_thresholds", thr_str]
        if cfg.get("n_mp_terms_file"):
            cmd += ["--n_mp_terms_file", str(cfg["n_mp_terms_file"])]
        if run(cmd, args.dry_run) != 0:
            return 1
    for fn in ("03_metrics_per_contrast.tsv", "04_roc_curves.tsv",
               "05_pr_curves.tsv", "06_per_genotype_ranks.tsv"):
        p = metrics_dir / fn
        manifest_rows.append(dict(stage="metrics", artifact=str(p), hash=hash_file(p)))

    paired_dir = outdir / "paired"
    paired_dir.mkdir(parents=True, exist_ok=True)
    paired_out = paired_dir / "07_paired_method_comparison.tsv"
    if not (args.reuse_existing and paired_out.exists()):
        cmd = [
            python_exe, str(HERE / "compare_methods_paired.py"),
            "--score_file", new_score_arg,
            "--score_file", f"B1_phenodigm_plain::{b1_out}::bma_score",
        ]
        pairs = ["new_pipeline:B1_phenodigm_plain"]
        if not args.skip_b2 and b2_out.exists():
            cmd += ["--score_file", f"B2_phenodigm_ic::{b2_out}::bma_score"]
            pairs += ["new_pipeline:B2_phenodigm_ic", "B1_phenodigm_plain:B2_phenodigm_ic"]
        cmd += [
            "--labels_file", cfg["labels_file"],
            "--outdir", str(paired_dir),
        ]
        for pair in pairs:
            cmd += ["--pair", pair]
        cmd += [
            "--n_bootstrap", str(cfg.get("n_bootstrap", 1000)),
            "--n_permutations", str(cfg.get("n_permutations", 10000)),
            "--seed", str(cfg.get("seed", 1)),
        ]
        if contrasts_sidecar:
            cmd += ["--contrasts_json", str(contrasts_sidecar)]
        if cfg.get("n_mp_thresholds"):
            thr_str = (",".join(str(int(k)) for k in cfg["n_mp_thresholds"])
                       if isinstance(cfg["n_mp_thresholds"], (list, tuple))
                       else str(cfg["n_mp_thresholds"]))
            cmd += ["--n_mp_thresholds", thr_str]
        if cfg.get("n_mp_terms_file"):
            cmd += ["--n_mp_terms_file", str(cfg["n_mp_terms_file"])]
        if run(cmd, args.dry_run) != 0:
            return 1
    for fn in ("07_paired_method_comparison.tsv", "08_score_pair_diffs.tsv"):
        p = paired_dir / fn
        manifest_rows.append(dict(stage="paired", artifact=str(p), hash=hash_file(p)))

    domain_dir = outdir / "domain"
    domain_dir.mkdir(parents=True, exist_ok=True)
    domain_out = domain_dir / "09_domain_hypothesis_tests.tsv"
    if cfg.get("domain_scores_file"):
        if not (args.reuse_existing and domain_out.exists()):
            cmd = [
                python_exe, str(HERE / "domain_hypothesis_tests.py"),
                "--domain_scores_file", cfg["domain_scores_file"],
                "--labels_file", cfg["labels_file"],
                "--analysis_mode", cfg.get("domain_analysis_mode", "strict"),
                "--outdir", str(domain_dir),
                "--n_permutations", str(cfg.get("n_permutations", 10000)),
                "--n_bootstrap", str(cfg.get("n_bootstrap", 1000)),
                "--seed", str(cfg.get("seed", 1)),
            ]
            if cfg.get("strict_domains"):
                cmd += ["--strict_domains", ",".join(cfg["strict_domains"])]
            if cfg.get("b2_domain"):
                cmd += ["--b2_domain", cfg["b2_domain"]]
            if cfg.get("b3_domain"):
                cmd += ["--b3_domain", cfg["b3_domain"]]
            if b_family_sidecar:
                cmd += ["--b_family_json", str(b_family_sidecar)]
            if cfg.get("positive_groups"):
                cmd += ["--positive_groups", cfg["positive_groups"]]
            if cfg.get("negative_groups"):
                cmd += ["--negative_groups", cfg["negative_groups"]]
            if run(cmd, args.dry_run) != 0:
                return 1
        for fn in ("09_domain_hypothesis_tests.tsv", "10_domain_score_long.tsv"):
            p = domain_dir / fn
            manifest_rows.append(dict(stage="domain", artifact=str(p), hash=hash_file(p)))
    else:
        log.warning("No domain_scores_file in config; skipping domain stage.")

    logistic_dir = outdir / "logistic"
    logistic_dir.mkdir(parents=True, exist_ok=True)
    logistic_out = logistic_dir / "11_logistic_model_summary.tsv"
    if not (args.reuse_existing and logistic_out.exists()):
        cmd = [
            python_exe, str(HERE / "confirmatory_logistic_models.py"),
            "--score_file", new_score_arg,
            "--score_file", f"B1_phenodigm_plain::{b1_out}::bma_score",
        ]
        if not args.skip_b2 and b2_out.exists():
            cmd += ["--score_file", f"B2_phenodigm_ic::{b2_out}::bma_score"]
        cmd += [
            "--labels_file", cfg["labels_file"],
            "--outdir", str(logistic_dir),
            "--seed", str(cfg.get("seed", 1)),
        ]
        if cfg.get("depth_assessability_file"):
            cmd += ["--depth_assessability_file", cfg["depth_assessability_file"]]
        if m_family_sidecar:
            cmd += ["--m_family_json", str(m_family_sidecar)]
        if run(cmd, args.dry_run) != 0:
            return 1
    for fn in ("11_logistic_model_summary.tsv", "12_model_diagnostics.tsv"):
        p = logistic_dir / fn
        manifest_rows.append(dict(stage="logistic", artifact=str(p), hash=hash_file(p)))

    if cfg.get("stability_manifest"):
        stab_dir = outdir / "stability"
        stab_dir.mkdir(parents=True, exist_ok=True)
        existing = HERE.parent / "assess_run_stability.py"
        if existing.exists():
            cmd = [
                python_exe, str(existing),
                "--manifest", cfg["stability_manifest"],
                "--outdir", str(stab_dir),
            ]
            run(cmd, args.dry_run)
            for p in stab_dir.glob("*.tsv"):
                manifest_rows.append(dict(
                    stage="stability", artifact=str(p), hash=hash_file(p)
                ))
        else:
            log.warning(
                "assess_run_stability.py not found at %s; skipping.",
                existing,
            )

    summary_path = outdir / "99_headline_summary.tsv"
    if not args.dry_run:
        metrics_out = outdir / "metrics" / "03_metrics_per_contrast.tsv"
        try:
            mdf = pd.read_csv(metrics_out, sep="\t")
            safe_write_csv(mdf, summary_path, sep="\t", index=False)
            manifest_rows.append(dict(
                stage="headline", artifact=str(summary_path),
                hash=hash_file(summary_path),
            ))
        except Exception as e:
            log.warning("headline summary skipped: %s", e)

    manifest = pd.DataFrame(manifest_rows)
    manifest_path = outdir / "00_run_manifest.tsv"
    safe_write_csv(manifest, manifest_path, sep="\t", index=False)
    log.info("Wrote manifest %s", manifest_path)
    log.info("Total elapsed: %.1fs", time.time() - t0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
