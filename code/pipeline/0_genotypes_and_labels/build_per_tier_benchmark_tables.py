#!/usr/bin/env python3
"""build_per_tier_benchmark_tables.py
==================================

Usage
-----
    python3 build_per_tier_benchmark_tables.py
    python3 build_per_tier_benchmark_tables.py --disorder MDD   # only one
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from safe_write_util import safe_write_csv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("build_per_tier_benchmark_tables")


TIER_ORDER = [
    "disease_terms",
    "Mendelian-confirmed",
    "Mendelian-suggestive",
    "common-variant-permissive",
    "none",
]

CUMULATIVE_TIERS = {
    "tier_0":  ["disease_terms"],
    "tier_1":  ["disease_terms", "Mendelian-confirmed"],
    "tier_1b": ["disease_terms", "Mendelian-confirmed", "Mendelian-suggestive"],
    "tier_2":  ["disease_terms", "Mendelian-confirmed", "Mendelian-suggestive",
                "common-variant-permissive"],
}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--config", type=Path,
                    default=Path("disorders_rescue_config.json"))
    ap.add_argument("--tier_dir", type=Path,
                    default=Path("disorder_tier_classification"))
    ap.add_argument(
        "--base_labels", type=Path,
        default=Path("broad_benchmark_setup/06_benchmark_group_table.csv"),
        help="The existing benchmark_group_table.csv — provides "
             "disease_terms and the original benchmark_group column.",
    )
    ap.add_argument(
        "--outdir", type=Path,
        default=Path("benchmark_tables_per_tier"),
    )
    ap.add_argument(
        "--disorder", type=str, default=None,
        help="Build tables for only this disorder slug (e.g., MDD). "
             "Default: build for every disorder in the config.",
    )
    ap.add_argument(
        "--dsm5_taxonomy", type=Path,
        default=Path("dsm5_chapter_taxonomy.json"),
        help="DSM-5 chapter-grounded regex taxonomy. Drives subgroup labels "
             "(bipolar_primary, anxiety_primary, psychotic_primary, etc.) "
             "needed by per-disorder Stage 5 contrasts. If the file is "
             "missing, falls back to the legacy 3-bucket scheme "
             "(MDD_primary / psychiatric_other_disorder / broad_other).",
    )
    args = ap.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(args.config.read_text(encoding="utf-8"))

    dsm5_taxonomy = None
    if args.dsm5_taxonomy.exists():
        dsm5_taxonomy = json.loads(args.dsm5_taxonomy.read_text(encoding="utf-8"))
        log.info("Loaded DSM-5 taxonomy with %d chapter buckets",
                 len(dsm5_taxonomy["chapters"]))
        for ch in dsm5_taxonomy["chapters"]:
            ch["_inc_re"] = re.compile(ch["regex"], re.IGNORECASE)
            exc = ch.get("exclude_regex") or ""
            ch["_exc_re"] = re.compile(exc, re.IGNORECASE) if exc else None
    else:
        log.warning("DSM-5 taxonomy file %s not found; falling back to legacy "
                    "3-bucket scheme (psychiatric_other_disorder / broad_other)",
                    args.dsm5_taxonomy)

    log.info("Loading base labels %s …", args.base_labels)
    base = pd.read_csv(args.base_labels, low_memory=False)
    base["genotype_id"] = base["genotype_id"].astype(str).str.strip()
    log.info("  %d genotypes in base labels", len(base))

    disorders = cfg["disorders"]
    if args.disorder:
        disorders = [d for d in disorders if d["name"] == args.disorder]
        if not disorders:
            log.error("--disorder %s not in config", args.disorder)
            return 2

    disorder_regexes = {
        d["name"]: re.compile(d["disease_terms_regex"], re.IGNORECASE)
        for d in cfg["disorders"]
    }

    summary_rows: List[Dict[str, Any]] = []

    for d in disorders:
        name = d["name"]
        label = d["label"]
        log.info("=== %s (%s) ===", name, label)

        tier_path = args.tier_dir / f"{name}_per_genotype_tiers.tsv"
        if not tier_path.exists():
            log.warning("  %s missing — run construct_disorder_tiers.py first. "
                        "Skipping.", tier_path)
            continue
        tiers = pd.read_csv(tier_path, sep="\t", low_memory=False)
        tiers["genotype_id"] = tiers["genotype_id"].astype(str).str.strip()
        log.info("  per-genotype tiers: %d rows", len(tiers))

        merged = base.merge(
            tiers[["genotype_id", "tier",
                   "in_disease_terms", "in_mgi_disease_gene_model",
                   "in_sfari",
                   "n_disgenet_mendelian_confirmed",
                   "n_disgenet_mendelian_suggestive",
                   "n_disgenet_common_variant",
                   "n_disgenet_literature_only",
                   "disgenet_sources_summary"]],
            on="genotype_id", how="left",
        )
        merged["tier"] = merged["tier"].fillna("none")

        comparator_tier_map: Dict[str, str] = {}
        for other_disorder in cfg["disorders"]:
            other_name = other_disorder["name"]
            if other_name == name:
                continue
            other_tier_path = args.tier_dir / f"{other_name}_per_genotype_tiers.tsv"
            if not other_tier_path.exists():
                continue
            other_tiers = pd.read_csv(other_tier_path, sep="\t", low_memory=False)
            other_tiers["genotype_id"] = other_tiers["genotype_id"].astype(str).str.strip()
            comparator_tier_map_per_tier = {}
            for ts_slug, ts_set in CUMULATIVE_TIERS.items():
                in_tier = other_tiers["tier"].isin(ts_set)
                gids = other_tiers.loc[in_tier, "genotype_id"].tolist()
                for gid in gids:
                    comparator_tier_map_per_tier.setdefault(ts_slug, {})[gid] = f"{other_name}_primary"
            for ts_slug, gid_map in comparator_tier_map_per_tier.items():
                if ts_slug not in comparator_tier_map:
                    comparator_tier_map[ts_slug] = {}
                for gid, lab in gid_map.items():
                    if gid not in comparator_tier_map[ts_slug]:
                        comparator_tier_map[ts_slug][gid] = lab
                    elif comparator_tier_map[ts_slug][gid] != lab \
                         and comparator_tier_map[ts_slug][gid] != "mixed_psychiatric_other":
                        comparator_tier_map[ts_slug][gid] = "mixed_psychiatric_other"

        if dsm5_taxonomy is not None:
            target_label = f"{name}_primary"
            chapters = dsm5_taxonomy["chapters"]
            disease_terms_series = merged["disease_terms"].fillna("").astype(str)

            def classify_chapter(s: str) -> str:
                hits = []
                for ch in chapters:
                    if ch["label"] == target_label:
                        continue
                    if not ch["_inc_re"].search(s):
                        continue
                    if ch["_exc_re"] is not None and ch["_exc_re"].search(s):
                        continue
                    hits.append(ch["label"])
                if not hits:
                    return ""
                if len(hits) >= 2:
                    return "mixed_psychiatric_other"
                return hits[0]

            merged["dsm5_chapter_label"] = disease_terms_series.apply(classify_chapter)
        else:
            merged["dsm5_chapter_label"] = ""
            for other_name, regex in disorder_regexes.items():
                if other_name == name:
                    continue
                mask = disease_terms_series.str.contains(regex, na=False) \
                    if False else merged["disease_terms"].astype(str).str.contains(
                        regex, na=False,
                    )
                merged.loc[mask, "dsm5_chapter_label"] = "psychiatric_other_disorder"

        for tier_slug, tier_set in CUMULATIVE_TIERS.items():
            positive_mask = merged["tier"].isin(tier_set) & (merged["tier"] != "none")
            n_pos = int(positive_mask.sum())

            bg = merged["benchmark_group"].astype(str).copy()
            bg = pd.Series(["broad_other"] * len(merged), index=merged.index)
            non_empty = merged["dsm5_chapter_label"].astype(str) != ""
            bg.loc[non_empty] = merged.loc[non_empty, "dsm5_chapter_label"].values

            ct_map = comparator_tier_map.get(tier_slug, {})
            if ct_map:
                gid_series = merged["genotype_id"].astype(str)
                ct_mask = gid_series.isin(ct_map.keys())
                bg.loc[ct_mask] = gid_series[ct_mask].map(ct_map).values

            ct_map_for_mixed = comparator_tier_map.get(tier_slug, {})
            if ct_map_for_mixed:
                gid_series = merged["genotype_id"].astype(str)
                in_other_comp = gid_series.isin(ct_map_for_mixed.keys())
            else:
                in_other_comp = pd.Series([False] * len(merged), index=merged.index)
            mixed_mask = positive_mask & in_other_comp
            pure_mask  = positive_mask & ~in_other_comp
            bg.loc[pure_mask]  = f"{name}_primary"
            bg.loc[mixed_mask] = f"{name}_mixed"

            out = merged.copy()
            out["benchmark_group"]  = bg.values
            out["rescue_tier"]      = merged["tier"]
            out["evidence_source_summary"] = merged["disgenet_sources_summary"].fillna("")

            keep_cols = [
                "genotype_id", "benchmark_group", "disease_terms",
                "rescue_tier", "evidence_source_summary",
                "dsm5_chapter_label",
                "in_disease_terms", "in_mgi_disease_gene_model", "in_sfari",
                "n_disgenet_mendelian_confirmed",
                "n_disgenet_mendelian_suggestive",
                "n_disgenet_common_variant",
                "n_disgenet_literature_only",
            ]
            if name == "ASD":
                for c in ["is_asd_model", "matched_sfari_genes",
                          "contains_sfari_gene", "is_single_gene_model",
                          "is_polygenic_model", "is_mixed_asd_model"]:
                    if c in out.columns and c not in keep_cols:
                        keep_cols.append(c)
            out = out[[c for c in keep_cols if c in out.columns]]

            outpath = args.outdir / f"{name}_{tier_slug}.csv"
            safe_write_csv(out, outpath, index=False)
            bg_counts = bg.value_counts().to_dict()
            n_other = sum(v for k, v in bg_counts.items()
                          if k not in (f"{name}_primary", "broad_other"))
            n_negs = int(bg_counts.get("broad_other", 0))
            log.info(
                "  %s: positive=%d, non_target_psych=%d, broad_other=%d -> %s",
                tier_slug, n_pos, n_other, n_negs, outpath.name,
            )
            summary_rows.append({
                "disorder": name,
                "label":    label,
                "tier_slug":               tier_slug,
                "tier_set":                ", ".join(tier_set),
                "n_positive":              n_pos,
                "n_non_target_psych":      n_other,
                "n_broad_other":           n_negs,
                "labels_file":             str(outpath),
                "benchmark_group_counts":  json.dumps({k: int(v) for k, v in bg_counts.items()}),
            })

    summary_df = pd.DataFrame(summary_rows)
    safe_write_csv(
        summary_df,
        args.outdir / "per_tier_counts_summary.tsv",
        sep="\t", index=False,
    )
    log.info("\n=== Per-tier table counts ===")
    if not summary_df.empty:
        log.info("\n%s",
                 summary_df.pivot(
                     index="disorder", columns="tier_slug", values="n_positive",
                 ).fillna(0).astype(int).to_string())
    log.info("\nDone. Per-tier benchmark tables at %s", args.outdir.resolve())
    log.info("Use each as: --labels_file_override <path>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
