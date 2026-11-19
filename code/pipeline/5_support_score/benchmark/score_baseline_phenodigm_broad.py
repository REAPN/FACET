#!/usr/bin/env python3
"""score_baseline_phenodigm_broad.py
=================================

Usage example
-------------
    python score_baseline_phenodigm_broad.py         --hpo_targets       07_final_resolved_hpo_terms.tsv         --genotype_long     broad_benchmark_setup/08_all_genotype_phenotypes_long_blinded.csv         --similarity_table  phenio-monarch-hp-mp.0.4.semsimian.tsv         --similarity_column phenodigm_score         --baseline_label    B1_phenodigm_plain         --outdir            benchmark/baseline_scores
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
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("baseline_phenodigm")


def read_hpo_targets(path: Path) -> set[str]:
    df = pd.read_csv(path, sep="\t")
    candidates = ["final_hpo_id", "hpo_id", "HPO_ID", "id"]
    col = next((c for c in candidates if c in df.columns), None)
    if col is None:
        raise ValueError(
            f"Could not find an HPO ID column in {path}. "
            f"Columns present: {list(df.columns)}"
        )
    ids = (
        df[col]
        .dropna()
        .astype(str)
        .str.strip()
        .pipe(lambda s: s[s.str.startswith("HP:")])
        .unique()
        .tolist()
    )
    log.info("Loaded %d unique HPO targets from %s", len(ids), path.name)
    return set(ids)


def read_genotype_phenotypes(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, low_memory=False)
    else:
        df = pd.read_csv(path, sep="\t", low_memory=False)
    gcol = next(
        (c for c in ["genotype_id", "Genotype Accession ID", "geno_id"] if c in df.columns),
        None,
    )
    mcol = next(
        (c for c in ["mp_id", "MP ID", "MP_ID", "mammalian_phenotype_id"] if c in df.columns),
        None,
    )
    if gcol is None or mcol is None:
        raise ValueError(
            f"Could not find genotype/mp columns in {path}. "
            f"Columns present: {list(df.columns)[:30]}"
        )
    out = df[[gcol, mcol]].rename(columns={gcol: "genotype_id", mcol: "mp_id"}).copy()
    out = out.dropna(subset=["genotype_id", "mp_id"])
    out["genotype_id"] = out["genotype_id"].astype(str).str.strip()
    out["mp_id"] = out["mp_id"].astype(str).str.strip()
    out = out[out["mp_id"].str.startswith("MP:")]
    out = out.drop_duplicates()
    log.info(
        "Loaded %d (genotype, MP) rows for %d genotypes and %d unique MP terms",
        len(out),
        out["genotype_id"].nunique(),
        out["mp_id"].nunique(),
    )
    return out


def read_similarity_table_filtered(
    path: Path,
    keep_subjects: set[str],
    keep_objects: set[str],
    similarity_column: str,
    chunksize: int = 1_000_000,
) -> pd.DataFrame:
    log.info("Streaming similarity table %s (chunksize=%d)", path.name, chunksize)
    pieces = []
    n_rows_seen = 0
    keep_subjects_arr = pd.Index(list(keep_subjects))
    keep_objects_arr = pd.Index(list(keep_objects))
    needed_cols = ["subject_id", "object_id", similarity_column]
    for chunk in pd.read_csv(
        path,
        sep="\t",
        chunksize=chunksize,
        usecols=needed_cols,
        dtype={"subject_id": "string", "object_id": "string", similarity_column: "float64"},
    ):
        n_rows_seen += len(chunk)
        chunk = chunk.dropna(subset=[similarity_column])
        chunk = chunk[chunk["subject_id"].isin(keep_subjects_arr)]
        chunk = chunk[chunk["object_id"].isin(keep_objects_arr)]
        if not chunk.empty:
            pieces.append(chunk)
    if not pieces:
        raise RuntimeError(
            f"No rows of {path.name} survived filtering. "
            f"Check that the HPO target IDs and MP term IDs intersect the table."
        )
    raw = pd.concat(pieces, ignore_index=True)
    log.info(
        "Filtered table: %d rows kept from %d streamed (%.2f%%)",
        len(raw),
        n_rows_seen,
        100.0 * len(raw) / max(n_rows_seen, 1),
    )
    pair_sim = (
        raw.groupby(["subject_id", "object_id"], sort=False)[similarity_column]
        .max()
        .reset_index()
        .rename(columns={"subject_id": "hp_id", "object_id": "mp_id", similarity_column: "similarity"})
    )
    log.info("Per-pair similarity rows after ancestor collapse: %d", len(pair_sim))
    return pair_sim


def compute_bma_per_genotype(
    geno_long: pd.DataFrame,
    pair_sim: pd.DataFrame,
    hpo_targets: set[str],
) -> pd.DataFrame:
    n_targets = len(hpo_targets)
    targets_arr = np.array(sorted(hpo_targets))

    mp_max_to_h = (
        pair_sim.groupby("mp_id")["similarity"].max().rename("mp_best_sim_to_any_h")
    )


    pair_sim_by_mp = pair_sim.groupby("mp_id")
    pair_sim_by_hp = pair_sim.groupby("hp_id")

    hp_max_sim = pair_sim.groupby("hp_id")["similarity"].max().to_dict()

    geno_groups = geno_long.groupby("genotype_id")["mp_id"].unique()

    rows = []
    n_genotypes = len(geno_groups)
    log.info("Computing BMA across %d genotypes", n_genotypes)
    t0 = time.time()
    last_log = t0
    for i, (gid, mp_arr) in enumerate(geno_groups.items(), 1):
        mp_set = set(mp_arr.tolist())

        rel = pair_sim[pair_sim["mp_id"].isin(mp_set)]
        if rel.empty:
            asym_h2m = 0.0
            asym_m2h = 0.0
            n_targets_hit = 0
            n_mp_hit = 0
        else:
            hp_max_in_geno = rel.groupby("hp_id")["similarity"].max()
            sum_sim = hp_max_in_geno.reindex(targets_arr).fillna(0.0).sum()
            asym_h2m = float(sum_sim) / n_targets if n_targets else 0.0
            n_targets_hit = int((hp_max_in_geno.reindex(targets_arr).fillna(0.0) > 0).sum())

            mp_max_in_geno = rel.groupby("mp_id")["similarity"].max()
            sum_sim_m = mp_max_in_geno.reindex(list(mp_set)).fillna(0.0).sum()
            asym_m2h = float(sum_sim_m) / max(len(mp_set), 1)
            n_mp_hit = int((mp_max_in_geno.reindex(list(mp_set)).fillna(0.0) > 0).sum())

        bma = 0.5 * (asym_h2m + asym_m2h)
        rows.append(
            dict(
                genotype_id=gid,
                n_mp_terms=len(mp_set),
                n_hpo_targets=n_targets,
                n_targets_with_any_match=n_targets_hit,
                n_mp_with_any_match=n_mp_hit,
                asym_h_to_m=asym_h2m,
                asym_m_to_h=asym_m2h,
                bma_score=bma,
            )
        )
        if time.time() - last_log > 30:
            elapsed = time.time() - t0
            rate = i / max(elapsed, 1e-9)
            remaining = (n_genotypes - i) / max(rate, 1e-9)
            log.info(
                "  progress: %d/%d (%.1f/s, eta %.0fs)",
                i, n_genotypes, rate, remaining,
            )
            last_log = time.time()

    out = pd.DataFrame(rows)
    log.info("BMA scoring complete in %.1fs", time.time() - t0)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--admitted_pairs_tsv", type=Path, default=None,
                    help="Optional (hpo_id, mp_id) allowlist from FACET's admitted candidate pool. "
                         "If given, Phenodigm similarity is kept ONLY for these admitted pairs; every "
                         "other (HP, MP) pair contributes 0, so physiological/endophenotype terms FACET "
                         "never admitted cannot influence the face-validity comparison.")
    ap.add_argument("--hpo_targets", type=Path, required=True,
                    help="Frozen HPO target TSV (07_final_resolved_hpo_terms.tsv).")
    ap.add_argument("--genotype_long", type=Path, required=True,
                    help="Long-format genotype phenotype CSV/TSV "
                         "(broad_benchmark_setup/08_all_genotype_phenotypes_long_blinded.csv).")
    ap.add_argument("--similarity_table", type=Path, required=True,
                    help="Semsimian HP-MP similarity TSV.")
    ap.add_argument("--similarity_column", default="phenodigm_score",
                    help="Column to use as the per-pair similarity. "
                         "Default: phenodigm_score (also valid: jaccard_similarity, "
                         "cosine_similarity, dice_similarity, ancestor_information_content).")
    ap.add_argument("--baseline_label", required=True,
                    help="Label used in output filenames and audit columns. "
                         "Recommend: B1_phenodigm_plain or B2_phenodigm_ic.")
    ap.add_argument("--outdir", type=Path, required=True,
                    help="Directory for outputs.")
    ap.add_argument("--emit_audit", action="store_true",
                    help="Also write 02_baseline_pair_audit__<label>.tsv "
                         "with per-pair collapsed similarities (large file).")
    ap.add_argument("--chunksize", type=int, default=1_000_000,
                    help="Streaming chunk size for the similarity TSV.")
    args = ap.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)

    hpo_targets = read_hpo_targets(args.hpo_targets)
    geno_long = read_genotype_phenotypes(args.genotype_long)
    universe_mp = set(geno_long["mp_id"].unique())

    pair_sim = read_similarity_table_filtered(
        args.similarity_table,
        keep_subjects=hpo_targets,
        keep_objects=universe_mp,
        similarity_column=args.similarity_column,
        chunksize=args.chunksize,
    )

    if args.admitted_pairs_tsv:
        import csv as _csv
        adm=set()
        with open(args.admitted_pairs_tsv) as _f:
            _rd=_csv.DictReader(_f, delimiter="\t")
            _hpc = "hpo_id" if "hpo_id" in _rd.fieldnames else _rd.fieldnames[0]
            _mpc = "mp_id" if "mp_id" in _rd.fieldnames else _rd.fieldnames[1]
            for _r in _rd: adm.add((_r[_hpc], _r[_mpc]))
        _before=len(pair_sim)
        _key=list(zip(pair_sim["hp_id"].tolist(), pair_sim["mp_id"].tolist()))
        _mask=pd.Series([k in adm for k in _key], index=pair_sim.index)
        pair_sim=pair_sim[_mask]
        log.info("Admitted-pair restriction: kept %d of %d pairs (%d admitted pairs loaded).",
                 len(pair_sim), _before, len(adm))

    scores = compute_bma_per_genotype(geno_long, pair_sim, hpo_targets)
    scores.insert(1, "baseline_label", args.baseline_label)

    out_scores = args.outdir / f"01_baseline_genotype_scores__{args.baseline_label}.tsv"
    safe_write_csv(scores, out_scores, sep="\t", index=False)
    log.info("Wrote %s (%d rows)", out_scores, len(scores))

    if args.emit_audit:
        audit = pair_sim.copy()
        audit["source_baseline_label"] = args.baseline_label
        out_audit = args.outdir / f"02_baseline_pair_audit__{args.baseline_label}.tsv"
        safe_write_csv(audit, out_audit, sep="\t", index=False)
        log.info("Wrote %s (%d rows)", out_audit, len(audit))

    cfg = dict(
        baseline_label=args.baseline_label,
        hpo_targets=str(args.hpo_targets),
        genotype_long=str(args.genotype_long),
        similarity_table=str(args.similarity_table),
        similarity_column=args.similarity_column,
        admitted_pairs_tsv=(str(args.admitted_pairs_tsv) if args.admitted_pairs_tsv else None),
        admitted_pair_restriction_applied=bool(args.admitted_pairs_tsv),
        n_hpo_targets=len(hpo_targets),
        n_genotypes_in_universe=int(geno_long["genotype_id"].nunique()),
        n_unique_mp_in_universe=len(universe_mp),
        n_pairs_after_collapse=int(len(pair_sim)),
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
    )
    out_cfg = args.outdir / f"99_baseline_run_config__{args.baseline_label}.json"
    out_cfg.write_text(json.dumps(cfg, indent=2))
    log.info("Wrote %s", out_cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
