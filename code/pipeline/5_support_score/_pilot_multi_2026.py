#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

SHARED = Path("_pilot_multi_2026")
GENO = Path("broad_benchmark_setup/08_all_genotype_phenotypes_long_blinded.csv")
PUBLISHED = Path("phenio-monarch-hp-mp.0.4.semsimian.tsv")
DASH_FAMILY = set("\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe58\ufe63\uff0d")

CONFIG = {
    "scz": dict(
        targets="pilot_hpo_run_scz_v1/07_final_resolved_hpo_terms.tsv",
        n_targets=41,
        run_dir="benchmark/run_2026-07-28_criterion_v1_scz_poloff_strict",
        labels="benchmark_tables_per_tier/SCZ_tier_0.csv",
        contrast="A2",
        record=dict(facet=0.6995, pheno=0.7423, delta=-0.0428, n_pos=39, n_neg=12447),
    ),
    "id": dict(
        targets="pilot_hpo_run_intellectualdisability_v1/07_final_resolved_hpo_terms.tsv",
        n_targets=25,
        run_dir="benchmark/run_2026-07-28_criterion_v1_intellectualdisability_poloff_strict",
        labels="benchmark_tables_per_tier/IntellectualDisability_tier_0.csv",
        contrast="A2",
        record=dict(facet=0.7331, pheno=0.6429, delta=0.0903, n_pos=73, n_neg=12309),
    ),
    "ncd": dict(
        targets="pilot_hpo_run_neurocognitive_v1/07_final_resolved_hpo_terms.tsv",
        n_targets=28,
        run_dir="benchmark/run_2026-07-28_criterion_v1_neurocognitive_cf_poloff_strict",
        labels="benchmark_tables_per_tier/Neurocognitive_tier_0.csv",
        contrast="A2",
        record=dict(facet=0.6607, pheno=0.5550, delta=0.1057, n_pos=67, n_neg=11536),
    ),
}


def outdir(d: str) -> Path:
    return Path(f"_pilot_{d}_2026")


def read_targets(path: Path) -> list:
    t = pd.read_csv(path, sep="\t")
    col = next((c for c in ["final_hpo_id", "hpo_id", "HPO_ID", "id"] if c in t.columns), None)
    if col is None:
        raise SystemExit(f"No HPO id column in {path}")
    s = t[col].dropna().astype(str).str.strip()
    return sorted(set(s[s.str.startswith("HP:")]))


def load_geno_reduced() -> pd.DataFrame:
    cache = SHARED / "_geno_long_reduced.csv"
    if cache.exists():
        return pd.read_csv(cache)
    g = pd.read_csv(GENO, low_memory=False)
    gcol = next((c for c in ["genotype_id", "Genotype Accession ID", "geno_id"] if c in g.columns), None)
    mcol = next((c for c in ["mp_id", "MP ID", "MP_ID", "mammalian_phenotype_id"] if c in g.columns), None)
    g = g[[gcol, mcol]].rename(columns={gcol: "genotype_id", mcol: "mp_id"}).dropna()
    g["genotype_id"] = g["genotype_id"].astype(str).str.strip()
    g["mp_id"] = g["mp_id"].astype(str).str.strip()
    g = g[g["mp_id"].str.startswith("MP:")].drop_duplicates()
    g.to_csv(cache, index=False)
    return g


def read_pair_sim(path: Path, keep_subjects: set, keep_objects: set, col: str) -> pd.DataFrame:
    pieces = []
    for chunk in pd.read_csv(path, sep="\t", chunksize=1000000,
                             usecols=["subject_id", "object_id", col],
                             dtype={"subject_id": "string", "object_id": "string"}):
        chunk = chunk.dropna(subset=[col])
        chunk = chunk[chunk["subject_id"].isin(keep_subjects)]
        chunk = chunk[chunk["object_id"].isin(keep_objects)]
        if not chunk.empty:
            pieces.append(chunk)
    if not pieces:
        raise SystemExit(f"No rows of {path} survived filtering.")
    raw = pd.concat(pieces, ignore_index=True)
    return (raw.groupby(["subject_id", "object_id"], sort=False)[col].max()
               .reset_index()
               .rename(columns={"subject_id": "hp_id", "object_id": "mp_id", col: "similarity"}))


def score_bma(pair: pd.DataFrame, geno: pd.DataFrame, targets: list, label: str) -> pd.DataFrame:
    universe = sorted(geno["mp_id"].unique())
    mp_index = {m: i for i, m in enumerate(universe)}
    t_index = {h: i for i, h in enumerate(targets)}
    n_t, n_m = len(targets), len(universe)
    M = np.zeros((n_t, n_m), dtype=np.float64)
    M[pair["hp_id"].map(t_index).to_numpy(),
      pair["mp_id"].map(mp_index).to_numpy()] = pair["similarity"].to_numpy()
    colmax = M.max(axis=0)
    g = geno.copy()
    g["mp_ix"] = g["mp_id"].map(mp_index)
    rows = []
    for gid, sub in g.groupby("genotype_id", sort=True):
        idx = sub["mp_ix"].to_numpy()
        k = len(idx)
        per_target_max = M[:, idx].max(axis=1) if k else np.zeros(n_t)
        h2m = float(per_target_max.sum()) / n_t
        m2h_vals = colmax[idx]
        m2h = float(m2h_vals.sum()) / max(k, 1)
        rows.append((gid, k, n_t, int((per_target_max > 0).sum()),
                     int((m2h_vals > 0).sum()), h2m, m2h, 0.5 * (h2m + m2h)))
    out = pd.DataFrame(rows, columns=[
        "genotype_id", "n_mp_terms", "n_hpo_targets",
        "n_targets_with_any_match", "n_mp_with_any_match",
        "asym_h_to_m", "asym_m_to_h", "bma_score"])
    out.insert(1, "baseline_label", label)
    return out


def cmd_prepare(_args) -> int:
    SHARED.mkdir(exist_ok=True)
    geno = load_geno_reduced()
    mp = sorted(geno["mp_id"].unique())
    (SHARED / "mp_universe.txt").write_text("\n".join(mp) + "\n")
    print(f"universe: {geno['genotype_id'].nunique()} genotypes (expect 76060), "
          f"{len(mp)} MP terms (expect 11485)")
    if geno["genotype_id"].nunique() != 76060 or len(mp) != 11485:
        print("PREPARE FAIL: universe mismatch"); return 1
    for d, cfg in CONFIG.items():
        hp = read_targets(Path(cfg["targets"]))
        (SHARED / f"hp_targets_{d}.txt").write_text("\n".join(hp) + "\n")
        print(f"{d}: {len(hp)} targets (expect {cfg['n_targets']})")
        if len(hp) != cfg["n_targets"]:
            print(f"PREPARE FAIL: {d} target count mismatch"); return 1
        outdir(d).mkdir(exist_ok=True)
    print("prepare: PASS")
    return 0


def cmd_analyze(args) -> int:
    d = args.disorder
    cfg = CONFIG[d]
    out = outdir(d)
    semsim = out / f"{d}_unfiltered_2026.semsimian.tsv"
    hp = [l.strip() for l in (SHARED / f"hp_targets_{d}.txt").read_text().splitlines() if l.strip()]
    mp = [l.strip() for l in (SHARED / "mp_universe.txt").read_text().splitlines() if l.strip()]
    geno = load_geno_reduced()

    df = pd.read_csv(semsim, sep="\t", low_memory=False)
    need = ["subject_id", "object_id", "ancestor_id", "ancestor_information_content",
            "jaccard_similarity", "phenodigm_score"]
    if [c for c in need if c not in df.columns]:
        print(f"[{d}] FAIL: semsimian output missing columns"); return 1
    n_pairs = df.groupby(["subject_id", "object_id"]).ngroups
    n_exp = len(hp) * len(mp)
    cov = 100.0 * n_pairs / n_exp
    print(f"[{d}] coverage: {n_pairs} of {n_exp} pairs ({cov:.2f} percent); "
          f"{n_exp - n_pairs} share no is_a ancestor and score 0 downstream")
    if cov < 80:
        print(f"[{d}] FAIL: coverage under 80 percent, output looks truncated"); return 1
    icc = df.dropna(subset=["ancestor_information_content"]).groupby(
        "ancestor_id")["ancestor_information_content"].agg(["min", "max"])
    if int((icc["max"] - icc["min"] > 1e-9).sum()):
        print(f"[{d}] FAIL: inconsistent ancestor IC"); return 1
    print(f"[{d}] IC consistent across {len(icc)} distinct ancestors")

    record_base = Path(cfg["run_dir"]) / ("baseline_scores/"
                    "01_baseline_genotype_scores__B1_phenodigm_plain.tsv")
    pub_pair = read_pair_sim(PUBLISHED, set(hp), set(mp), "phenodigm_score")
    check = score_bma(pub_pair, geno, hp, "check")
    rec = pd.read_csv(record_base, sep="\t")
    m = rec.merge(check, on="genotype_id", suffixes=("_rec", "_new"))
    worst = 0.0
    for c in ["n_targets_with_any_match", "n_mp_with_any_match",
              "asym_h_to_m", "asym_m_to_h", "bma_score"]:
        worst = max(worst, float((m[c + "_rec"] - m[c + "_new"]).abs().max()))
    if len(m) != len(rec) or worst > 1e-10:
        print(f"[{d}] FAIL: scorer does not reproduce the run of record "
              f"(rows {len(m)}/{len(rec)}, max diff {worst:.3e})"); return 1
    print(f"[{d}] scorer self-check PASS: reproduces run of record, max diff {worst:.3e}")

    pub_j = read_pair_sim(PUBLISHED, set(hp), set(mp), "jaccard_similarity")
    ours = (df.groupby(["subject_id", "object_id"], as_index=False)["jaccard_similarity"]
              .max().rename(columns={"subject_id": "hp_id", "object_id": "mp_id",
                                     "jaccard_similarity": "j_2026"}))
    dr = pub_j.rename(columns={"similarity": "j_published"}).merge(
        ours, on=["hp_id", "mp_id"], how="left")
    dr["delta"] = dr["j_2026"] - dr["j_published"]
    q = dr["delta"].dropna().quantile([0.05, 0.5, 0.95])
    print(f"[{d}] release drift vs published ({len(dr)} shared pairs, "
          f"{int(dr['j_2026'].isna().sum())} missing): delta J p5 {q.iloc[0]:.3f} "
          f"p50 {q.iloc[1]:.3f} p95 {q.iloc[2]:.3f}")
    dr.to_csv(out / f"release_drift_{d}_targets.tsv", sep="\t", index=False)

    arm2 = df[df["jaccard_similarity"] >= 0.4]
    arm2_path = out / f"arm2_thresh04_2026.semsimian.tsv"
    arm2.to_csv(arm2_path, sep="\t", index=False)
    print(f"[{d}] arm2: {len(arm2)} rows at J >= 0.4; arm3: {len(df)} rows, no cap")
    bs = out / "baseline_scores"
    bs.mkdir(exist_ok=True)
    for arm, src in [("arm2", arm2_path), ("arm3", semsim)]:
        pair = read_pair_sim(src, set(hp), set(mp), "phenodigm_score")
        t0 = time.time()
        scores = score_bma(pair, geno, hp, f"B1_phenodigm_{arm}_2026")
        p = bs / f"01_baseline_genotype_scores__B1_phenodigm_{arm}_2026.tsv"
        scores.to_csv(p, sep="\t", index=False)
        cfg_out = dict(baseline_label=f"B1_phenodigm_{arm}_2026",
                       scorer="_pilot_multi_2026.py score_bma, self-checked against "
                              "this disorder's run of record this run",
                       hpo_targets=cfg["targets"], similarity_table=str(src),
                       similarity_column="phenodigm_score",
                       admitted_pairs_tsv=None, admitted_pair_restriction_applied=False,
                       n_hpo_targets=len(hp), n_pairs_after_collapse=int(len(pair)),
                       timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"))
        (bs / f"99_baseline_run_config__B1_phenodigm_{arm}_2026.json").write_text(
            json.dumps(cfg_out, indent=2))
        print(f"[{d}] scored {arm} ({len(pair)} pairs) in {time.time() - t0:.1f}s")

    cmd = [sys.executable, "benchmark/compare_methods_paired.py",
           "--score_file", f"new_pipeline::{cfg['run_dir']}/00_score_filtered_strict.tsv::neg_log10_p",
           "--score_file", f"B1_phenodigm_arm2_2026::{bs}/01_baseline_genotype_scores__B1_phenodigm_arm2_2026.tsv::bma_score",
           "--score_file", f"B1_phenodigm_arm3_2026::{bs}/01_baseline_genotype_scores__B1_phenodigm_arm3_2026.tsv::bma_score",
           "--pair", "new_pipeline:B1_phenodigm_arm2_2026",
           "--pair", "new_pipeline:B1_phenodigm_arm3_2026",
           "--labels_file", cfg["labels"],
           "--contrasts_json", f"{cfg['run_dir']}/00_contrasts.json",
           "--n_mp_thresholds", "4",
           "--n_mp_terms_file", str(GENO),
           "--outdir", str(out / "paired")]
    print(f"[{d}] running paired comparison...")
    r = subprocess.run(cmd)
    if r.returncode != 0:
        print(f"[{d}] FAIL: paired comparison exited {r.returncode}"); return 1
    return cmd_report(args)


def pick(path: Path, contrast: str, method_b: str) -> dict:
    df = pd.read_csv(path, sep="\t")
    r = df[(df.contrast == contrast) & (df.n_mp_threshold == 4)
           & (df.metric == "auroc") & (df.method_a == "new_pipeline")
           & (df.method_b == method_b)]
    if len(r) != 1:
        raise SystemExit(f"{path}: expected one {contrast} K4 auroc row for {method_b}, got {len(r)}")
    r = r.iloc[0]
    return dict(facet=float(r.value_a), pheno=float(r.value_b), delta=float(r.delta),
                p=float(r.p_delong), n_pos=int(r.n_pos), n_neg=int(r.n_neg))


def cmd_report(args) -> int:
    d = args.disorder
    cfg = CONFIG[d]
    out = outdir(d)
    rec = pick(Path(cfg["run_dir"]) / "paired/07_paired_method_comparison.tsv",
               cfg["contrast"], "B1_phenodigm_plain")
    exp = cfg["record"]
    if abs(rec["delta"] - exp["delta"]) > 5e-4 or rec["n_pos"] != exp["n_pos"]:
        print(f"[{d}] FAIL: run-of-record row does not match the pinned record "
              f"({rec['delta']:+.4f}/{rec['n_pos']} vs {exp['delta']:+.4f}/{exp['n_pos']})")
        return 1
    a2 = pick(out / "paired/07_paired_method_comparison.tsv", cfg["contrast"], "B1_phenodigm_arm2_2026")
    a3 = pick(out / "paired/07_paired_method_comparison.tsv", cfg["contrast"], "B1_phenodigm_arm3_2026")
    lines = [f"# {d.upper()} three-arm paired comparison. Current 2026 graph.", ""]
    lines.append(f"Paired discrimination AUROCs, contrast {cfg['contrast']}, strict K=4, "
                 "matched intersection, FACET by neg_log10_p, baseline by bma_score.")
    lines.append("")
    lines.append("| arm | FACET | Phenodigm | delta | p (DeLong) | n_pos | n_neg |")
    lines.append("|---|---|---|---|---|---|---|")
    for label, v in [("1: published table, J >= 0.4", rec),
                     ("2: 2026 graph, J >= 0.4", a2),
                     ("3: 2026 graph, unfiltered", a3)]:
        lines.append(f"| {label} | {v['facet']:.4f} | {v['pheno']:.4f} | {v['delta']:+.4f} "
                     f"| {v['p']:.2e} | {v['n_pos']} | {v['n_neg']:,} |")
    lines.append("")
    lines.append(f"Release drift (arm2 minus arm1, Phenodigm): {a2['pheno'] - rec['pheno']:+.4f}")
    lines.append(f"Publication floor effect (arm3 minus arm2, Phenodigm): {a3['pheno'] - a2['pheno']:+.4f}")
    lines.append("")
    if a3["delta"] > a2["delta"] + 0.005:
        lines.append("KILL GATE FIRED: the FACET margin GREW when the floor came off."
                     " Unfilling zeros can only raise Phenodigm. Treat as an error;"
                     " do not quote anything in this file.")
    else:
        lines.append("Kill gate: not fired.")
    for name, v in [("arm2", a2), ("arm3", a3)]:
        if (v["n_pos"], v["n_neg"]) != (rec["n_pos"], rec["n_neg"]):
            lines.append(f"WARNING: {name} universe {v['n_pos']}/{v['n_neg']} differs "
                         f"from record {rec['n_pos']}/{rec['n_neg']}.")
    report = "\n".join(lines) + "\n"
    if any(c in DASH_FAMILY for c in report):
        raise SystemExit("dash-family character in report; refusing to write")
    (out / "REPORT.md").write_text(report)
    print(report)
    return 0


def cmd_summary(_args) -> int:
    rows = []
    specs = [("asd", "A1prime",
              "benchmark/run_2026-07-28_criterion_v1_asd_poloff_strict",
              Path("_pilot_asd_2026"))]
    specs += [(d, CONFIG[d]["contrast"], CONFIG[d]["run_dir"], outdir(d)) for d in CONFIG]
    lines = ["# Four-disorder three-arm summary. Paired discrimination AUROCs, strict K=4.", "",
             "| disorder | contrast | arm1 Pheno | arm2 Pheno | arm3 Pheno | delta arm1 | delta arm3 | p arm3 | floor effect | gate |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for d, contrast, run_dir, o in specs:
        try:
            rec = pick(Path(run_dir) / "paired/07_paired_method_comparison.tsv",
                       contrast, "B1_phenodigm_plain")
            a2 = pick(o / "paired/07_paired_method_comparison.tsv", contrast, "B1_phenodigm_arm2_2026")
            a3 = pick(o / "paired/07_paired_method_comparison.tsv", contrast, "B1_phenodigm_arm3_2026")
        except (SystemExit, FileNotFoundError) as e:
            lines.append(f"| {d.upper()} | {contrast} | INCOMPLETE: {e} | | | | | | | |")
            continue
        gate = "GREW, ERROR" if a3["delta"] > a2["delta"] + 0.005 else "clean"
        lines.append(f"| {d.upper()} | {contrast} | {rec['pheno']:.4f} | {a2['pheno']:.4f} "
                     f"| {a3['pheno']:.4f} | {rec['delta']:+.4f} | {a3['delta']:+.4f} "
                     f"| {a3['p']:.2e} | {a3['pheno'] - a2['pheno']:+.4f} | {gate} |")
    lines.append("")
    lines.append("Arm 1 = published 2024-08-14 table at J >= 0.4 (run of record). Arm 2 =")
    lines.append("recomputed on the current 2026 phenio-monarch.db at J >= 0.4. Arm 3 = same")
    lines.append("graph, floor removed. Floor effect = arm3 minus arm2 Phenodigm AUROC.")
    hits = []
    for p in Path(".").glob("_pilot_*_2026/REPORT.md"):
        text = p.read_text(encoding="utf-8", errors="replace")
        hits += [(str(p), unicodedata.name(ch, "?")) for ch in DASH_FAMILY if ch in text]
    lines.append("Dash sweep of all pilot reports: " + ("FAILED " + str(hits) if hits else "clean."))
    report = "\n".join(lines) + "\n"
    if any(c in DASH_FAMILY for c in report):
        raise SystemExit("dash-family character in summary; refusing to write")
    SHARED.mkdir(exist_ok=True)
    (SHARED / "REPORT_ALL.md").write_text(report)
    print(report)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prepare")
    for name in ["analyze", "report"]:
        p = sub.add_parser(name)
        p.add_argument("--disorder", required=True, choices=list(CONFIG))
    sub.add_parser("summary")
    args = ap.parse_args()
    return {"prepare": cmd_prepare, "analyze": cmd_analyze,
            "report": cmd_report, "summary": cmd_summary}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
