#!/usr/bin/env python3
from __future__ import annotations
import json, logging, os, shutil, subprocess, sys, time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("v2runner")

def cells():
    out = []
    DIS = {
        "ASD": ("ASD_primary", "asd.disorder.json", "benchmark/run_2026-05-11_v3_poloff_{mode}",
                ["T1d_consortium","T1d_provisional","T1g","T1c_consortium"]),
        "SCZ": ("SCZ_primary", "scz.disorder.json", "benchmark/run_2026-05-28_v2_scz_poloff_{mode}",
                ["T1d","T1g","T1c"]),
        "MDD": ("MDD_primary", "mdd.disorder.json", "benchmark/run_2026-XX-XX_v1_mdd_poloff_{mode}",
                ["T1g_headline","T1d_sensitivity","T1c_headline"]),
        "ID":  ("IntellectualDisability_primary", "intellectualdisability_2dom.disorder.json",
                "benchmark/run_2026-06-02_v1_intellectualdisability_2dom_poloff_{mode}",
                ["T1d_consortium","T1c_consortium"]),
    }
    for D,(tag,cfg,base,tiers) in DIS.items():
        for tier in tiers:
            for mode in ("strict","broad"):
                labels = f"benchmark_tables_per_tier/{D}_tier_{tier}_rescuepool_v2.csv"
                out.append((D,tier,mode,labels,tag,base.format(mode=mode),cfg))
    return out

def make_run_config(target, tier, mode, labels, tag, cfg_file):
    outdir = f"benchmark/run_2026-06-04_v3_{target.lower()}_{tier}_rescuepool_v2_poloff_{mode}"
    config_outdir = f"benchmark/rescuepool_v2_configs/{target}_{tier}_{mode}"
    Path(config_outdir).mkdir(parents=True, exist_ok=True)
    Path(outdir).mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "stage5_benchmark.py", "--config", cfg_file,
           "--regime","off","--mode",mode,
           "--labels_file_override", labels,
           "--outdir_override", outdir+"/",
           "--config_outdir", config_outdir, "--emit_configs_only"]
    if target == "ASD":
        cmd += ["--n_mp_thresholds_override","1,3,4,5,7,10",
                "--n_mp_terms_file_override","broad_benchmark_setup/08_all_genotype_phenotypes_long_blinded.csv"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(f"emit_configs_only failed: {r.stderr[-1500:]}")
    cfg_path = Path(config_outdir)/f"run_config_v3_poloff_{mode}.json"
    cfg = json.loads(cfg_path.read_text())
    cfg["contrasts"] = [{
        "name":"A1_rescue",
        "description": f"{target} target_primary (canonical T0 ∪ rescue {tier}, RL-§24 assessable) vs rescue-expanded other_psych_pool.",
        "positive_group": tag, "negative_groups":["other_psych_pool"],
        "expected_direction":">0.5","is_specificity_sanity_check":False,
    }]
    for k in ("b_family","m_family","positive_groups","negative_groups","negative_groups_token"):
        cfg.pop(k, None)
    cfg["similarity_table_ic"] = "phenio-monarch-hp-mp.0.4.semsimian.ic.tsv"
    cfg["n_bootstrap"] = int(os.environ.get("RESCUE_NBOOT", "100"))
    cfg["n_permutations"] = int(os.environ.get("RESCUE_NPERM", "200"))
    cfg_path.write_text(json.dumps(cfg, indent=2))
    return cfg_path, outdir

def prestage(outdir, base, D):
    src = Path(base)/"baseline_scores"; dst = Path(outdir)/"baseline_scores"
    dst.mkdir(parents=True, exist_ok=True)
    ok = False
    for f in ("01_baseline_genotype_scores__B1_phenodigm_plain.tsv",
              "99_baseline_run_config__B1_phenodigm_plain.json"):
        s, d = src/f, dst/f
        if s.exists() and not d.exists():
            shutil.copy2(s, d); ok = True
        elif d.exists():
            ok = True
    if not (dst/"01_baseline_genotype_scores__B1_phenodigm_plain.tsv").exists():
        raise FileNotFoundError(f"no B1 baseline at {src}")
    b2 = Path(f"benchmark/_b2_baseline_{D}/baseline_scores/01_baseline_genotype_scores__B2_phenodigm_ic.tsv")
    if b2.exists() and not (dst/b2.name).exists():
        shutil.copy2(b2, dst/b2.name)
    return ok

def run_cell(cfg_path, outdir, label, timeout=120):
    t0 = time.time()
    cmd = [sys.executable, "benchmark/run_benchmarks.py", "--config", str(cfg_path),
           "--skip_baselines"]
    if (Path(outdir)/"metrics"/"03_metrics_per_contrast.tsv").exists():
        cmd.append("--reuse_existing")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    el = time.time()-t0
    if r.returncode != 0:
        log.error("  FAILED %s rc=%d (%.1fs)\n%s", label, r.returncode, el, r.stderr[-1500:]); return False
    log.info("  OK %s (%.1fs)", label, el); return True

def main(only=None, budget=float(os.environ.get("RESCUE_BUDGET","38"))):
    t_start = time.time()
    done = skipped = 0
    for D,tier,mode,labels,tag,base,cfg_file in cells():
        label = f"{D}_{tier}_{mode}"
        if only and only not in label:
            continue
        outdir = f"benchmark/run_2026-06-04_v3_{D.lower()}_{tier}_rescuepool_v2_poloff_{mode}"
        if (Path(outdir)/"metrics"/"03_metrics_per_contrast.tsv").exists() and \
           (Path(outdir)/"paired"/"07_paired_method_comparison.tsv").exists():
            skipped += 1; continue
        if not Path(labels).exists():
            log.warning("  no labels %s — skip", labels); continue
        if time.time()-t_start > budget:
            log.info("budget reached; stopping (resume by re-running)"); break
        try:
            cfg_path, outdir = make_run_config(D,tier,mode,labels,tag,cfg_file)
            prestage(outdir, base, D)
            if run_cell(cfg_path, outdir, label): done += 1
        except Exception as e:
            log.exception("  exception %s: %s", label, e)
    pending = sum(1 for c in cells()
                  if not (only and only not in f"{c[0]}_{c[1]}_{c[2]}")
                  and not (Path(f"benchmark/run_2026-06-04_v3_{c[0].lower()}_{c[1]}_rescuepool_v2_poloff_{c[2]}")/"paired"/"07_paired_method_comparison.tsv").exists())
    log.info("=== this call: done=%d skipped=%d | pending(paired)=%d ===", done, skipped, pending)
    return 0

if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    raise SystemExit(main(only))
