#!/usr/bin/env python3
import os, subprocess, sys
from pathlib import Path

ROOT = Path(os.environ.get("LIULAB_ROOT") or ".").resolve()
IC = ROOT / "phenio-monarch-hp-mp.0.4.semsimian.ic.tsv"
LONG = ROOT / "broad_benchmark_setup/08_all_genotype_phenotypes_long_blinded.csv"
SCRIPT = ROOT / "benchmark/score_baseline_phenodigm_broad.py"

HPO = {
    "ASD": "pilot_hpo_run_hybrid_v3/07_final_resolved_hpo_terms.tsv",
    "SCZ": "pilot_hpo_run_scz_v1/07_final_resolved_hpo_terms.tsv",
    "MDD": "pilot_hpo_run_mdd_v1/07_final_resolved_hpo_terms.tsv",
    "ID":  "pilot_hpo_run_intellectualdisability_v1/07_final_resolved_hpo_terms.tsv",
}

def main():
    assert IC.exists(), f"missing IC table {IC}"
    for D, hpo in HPO.items():
        outdir = ROOT / f"benchmark/_b2_baseline_{D}/baseline_scores"
        out = outdir / "01_baseline_genotype_scores__B2_phenodigm_ic.tsv"
        if out.exists():
            print(f"[{D}] B2 already present: {out}"); continue
        outdir.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, str(SCRIPT),
               "--hpo_targets", hpo,
               "--genotype_long", str(LONG),
               "--similarity_table", str(IC),
               "--similarity_column", "phenodigm_score",
               "--baseline_label", "B2_phenodigm_ic",
               "--outdir", str(outdir)]
        print(f"[{D}] computing B2_phenodigm_ic ...")
        r = subprocess.run(cmd)
        if r.returncode != 0:
            print(f"[{D}] FAILED"); return 1
    print("=== B2 baselines ready under benchmark/_b2_baseline_{D}/ ===")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
