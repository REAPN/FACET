#!/usr/bin/env python3
"""construct_disorder_tiers.py
===========================

Usage
-----
    python3 construct_disorder_tiers.py
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import pandas as pd

from safe_write_util import safe_write_csv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("construct_disorder_tiers")


DEFAULT_SOURCE_CLASS = {
    "mendelian_confirmed":  {"CLINVAR", "ORPHANET", "CLINGEN", "GENCC", "UNIPROT"},
    "mendelian_suggestive": {"HPO", "CLINPGX", "PSYGENET"},
    "common_variant":       {"GWASCAT", "FINNGEN", "UKBIOBANK"},
    "literature_only":      {"TEXTMINING_HUMAN"},
    "circular_excluded":    {"MGD_HUMAN", "MGD_MOUSE", "RGD", "RGD_RAT",
                             "TEXTMINING_MODELS"},
    "clinical_other":       {"CLINICALTRIALS"},
}

TIER_ORDER = [
    "disease_terms",
    "Mendelian-confirmed",
    "Mendelian-suggestive",
    "common-variant-permissive",
    "none",
]


def extract_sources_from_breakdown(breakdown_json: str) -> Set[str]:
    if not breakdown_json or breakdown_json == "":
        return set()
    try:
        breakdown = json.loads(breakdown_json)
    except Exception:
        return set()
    out: Set[str] = set()
    if not isinstance(breakdown, list):
        return out
    for entry in breakdown:
        if not isinstance(entry, dict):
            continue
        comps = entry.get("components", {})
        if not isinstance(comps, dict):
            continue
        for cat_data in comps.values():
            if not isinstance(cat_data, dict):
                continue
            srcs = cat_data.get("sources", [])
            if isinstance(srcs, list):
                out.update(str(s) for s in srcs if s)
    return out


def classify_sources(
    sources: Set[str], source_class: Dict[str, Set[str]]
) -> Dict[str, int]:
    classes = {k: 0 for k in source_class.keys()}
    for s in sources:
        for klass, members in source_class.items():
            if s in members:
                classes[klass] += 1
    return classes


def load_disease_gene_model(path: Path) -> pd.DataFrame:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                continue
            rows.append(line.rstrip("\n").split("\t"))
    cols = [
        "human_gene_symbol", "human_gene_name", "hgnc_id",
        "disease_name", "doid",
        "mgi_allele_ids_pipe", "mouse_gene_symbol", "mgi_marker_id",
        "repository_sources_pipe", "stock_numbers_pipe",
    ]
    df = pd.DataFrame(rows, columns=cols[:len(rows[0])] if rows else cols)
    for c in ["human_gene_symbol", "mouse_gene_symbol", "doid"]:
        df[c] = df[c].astype(str).str.strip()
    return df


def load_labels(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    df["genotype_id"] = df["genotype_id"].astype(str).str.strip()
    if "disease_terms" not in df.columns:
        log.warning("labels file %s has no `disease_terms` column", path)
        df["disease_terms"] = ""
    df["disease_terms"] = df["disease_terms"].fillna("").astype(str)
    return df


def load_genotype_gene_map(path: Path) -> pd.DataFrame:
    long = pd.read_csv(
        path, usecols=["genotype_id", "all_genes_in_genotype"], low_memory=False,
    )
    long["genotype_id"] = long["genotype_id"].astype(str).str.strip()
    long = long.drop_duplicates(subset=["genotype_id"])
    if "all_genes_in_genotype" not in long.columns:
        log.warning("long table %s missing all_genes_in_genotype", path)
        return pd.DataFrame(columns=["genotype_id", "gene_symbol"])
    long["all_genes_in_genotype"] = long["all_genes_in_genotype"].fillna("").astype(str)
    long["genes_list"] = long["all_genes_in_genotype"].apply(
        lambda s: [g.strip().upper() for g in s.split("|") if g.strip()]
    )
    out = long.explode("genes_list").rename(columns={"genes_list": "gene_symbol"})
    out = out[["genotype_id", "gene_symbol"]]
    out = out[out["gene_symbol"].notna()]
    out = out[out["gene_symbol"] != ""]
    return out


def load_sfari(path: Path) -> Set[str]:
    if not path.exists():
        log.warning("SFARI %s not present; ASD SFARI set will be empty", path)
        return set()
    df = pd.read_csv(path, low_memory=False)
    col = "gene-symbol" if "gene-symbol" in df.columns else df.columns[1]
    syms = set(df[col].dropna().astype(str).str.strip().tolist())
    syms.discard("")
    return syms


def load_disgenet_associations(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep="\t", low_memory=False)
    for c in ("geneSymbol", "diseaseUMLSCUI"):
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip()
    if "scoreBreakdown_json" not in df.columns:
        log.warning("DisGeNET TSV %s missing scoreBreakdown_json column; "
                    "downstream source classification will be empty.", path)
        df["scoreBreakdown_json"] = ""
    return df


def _curated_only_score(breakdown_json: str) -> float:
    if not breakdown_json:
        return 0.0
    try:
        breakdown = json.loads(breakdown_json)
    except Exception:
        return 0.0
    if not isinstance(breakdown, list):
        return 0.0
    max_w = 0.0
    for entry in breakdown:
        if not isinstance(entry, dict):
            continue
        comps = entry.get("components", {})
        cur = comps.get("curated", {}) if isinstance(comps, dict) else {}
        if isinstance(cur, dict):
            w = cur.get("weight", 0.0)
            try:
                w = float(w)
            except (TypeError, ValueError):
                w = 0.0
            if w > max_w:
                max_w = w
    return max_w


def build_gene_evidence_for_disorder(
    disgenet: pd.DataFrame,
    cuis: Set[str],
    source_class: Dict[str, Set[str]],
    min_curated_score: float = 0.3,
    min_pmids: int = 0,
) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    sub = disgenet[disgenet["diseaseUMLSCUI"].astype(str).isin(cuis)].copy()
    if sub.empty:
        return out

    n_pre = len(sub)
    if "scoreBreakdown_json" in sub.columns and min_curated_score > 0:
        sub["_curated_score"] = sub["scoreBreakdown_json"].astype(str).apply(_curated_only_score)
        sub = sub[sub["_curated_score"] >= min_curated_score]
    if "numPMIDs" in sub.columns and min_pmids > 0:
        s_pmids = pd.to_numeric(sub["numPMIDs"], errors="coerce").fillna(0).astype(int)
        sub = sub[s_pmids >= min_pmids]
    n_post = len(sub)
    if n_pre != n_post:
        log.info(
            "  H7 v2 threshold filter (curated_score>=%.2f, numPMIDs>=%d): "
            "%d -> %d associations (dropped %d rows; %.1f%%)",
            min_curated_score, min_pmids, n_pre, n_post, n_pre - n_post,
            100.0 * (n_pre - n_post) / max(n_pre, 1),
        )

    excl = source_class.get("circular_excluded", set())
    for _, row in sub.iterrows():
        gene = str(row.get("geneSymbol", "")).strip()
        if not gene:
            continue
        srcs = extract_sources_from_breakdown(row.get("scoreBreakdown_json", ""))
        srcs_clean = srcs - excl
        if gene not in out:
            out[gene] = {
                "sources": set(),
                "counts":  {k: 0 for k in source_class.keys()},
                "n_associations": 0,
            }
        out[gene]["sources"] |= srcs_clean
        out[gene]["n_associations"] += 1
    for gene, data in out.items():
        data["counts"] = classify_sources(data["sources"], source_class)
    return out


def assign_tier(
    in_disease_terms: bool,
    in_mgi_dgm: bool,
    in_sfari: bool,
    n_mend_conf: int,
    n_mend_sugg: int,
    n_common_var: int,
) -> Tuple[str, str]:
    if in_disease_terms:
        max_cls = "disease_terms"
        return "disease_terms", max_cls

    if in_mgi_dgm and n_mend_conf >= 1:
        return "Mendelian-confirmed", "Mendelian-confirmed"

    if in_mgi_dgm or n_mend_conf >= 1 or in_sfari or n_mend_sugg >= 1:
        return "Mendelian-suggestive", "Mendelian-suggestive"

    if n_common_var >= 1:
        return "common-variant-permissive", "common-variant-permissive"

    return "none", "none"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--config", type=Path,
                    default=Path("disorders_rescue_config.json"))
    ap.add_argument("--mgi_disease_gene_model", type=Path,
                    default=Path("MGI_DiseaseGeneModel.rpt"))
    ap.add_argument("--labels_file", type=Path,
                    default=Path("broad_benchmark_setup/06_benchmark_group_table.csv"))
    ap.add_argument("--genotype_long", type=Path,
                    default=Path("broad_benchmark_setup/"
                                  "08_all_genotype_phenotypes_long_blinded.csv"))
    ap.add_argument("--disgenet_tsv", type=Path,
                    default=Path("disgenet_api_pull_multi/"
                                  "all_gene_disease_associations.tsv"))
    ap.add_argument("--outdir", type=Path,
                    default=Path("disorder_tier_classification"))
    ap.add_argument("--min_disgenet_curated_score", type=float, default=0.3,
                    help="Threshold on the CURATED-ONLY component of DisGeNET's "
                         "composite score (extracted from "
                         "scoreBreakdown.components.curated.weight). Default 0.3 "
                         "is calibrated to DisGeNET's 'moderate confidence' prior "
                         "applied to the curated component only — filters weak "
                         "associations whose curated evidence is thin even if "
                         "their composite score is inflated by anti-circularity-"
                         "excluded model-organism or text-mining contributions. "
                         "H7 v2 audit fix 2026-05-26.")
    ap.add_argument("--min_disgenet_pmids", type=int, default=0,
                    help="Minimum numPMIDs (number of PubMed IDs supporting the "
                         "association). Default 0 to avoid filtering legitimate "
                         "curated-DB-only evidence (CLINVAR/UNIPROT entries often "
                         "have numPMIDs=0). Set to 2 for additional literature-"
                         "replication filter on top of the curated-score gate.")
    args = ap.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(args.config.read_text(encoding="utf-8"))

    source_class_raw = cfg.get("disgenet_source_classification", {})
    source_class = {k: set(v) for k, v in source_class_raw.items()} \
                   if source_class_raw else DEFAULT_SOURCE_CLASS
    log.info("Evidence-source classification:")
    for k, v in source_class.items():
        log.info("  %-25s -> %s", k, sorted(v))

    log.info("Loading MGI_DiseaseGeneModel.rpt …")
    dgm = load_disease_gene_model(args.mgi_disease_gene_model)
    dgm["human_gene_symbol"] = dgm["human_gene_symbol"].astype(str).str.upper()
    log.info("  %d rows; %d unique human genes",
             len(dgm), dgm["human_gene_symbol"].nunique())

    log.info("Loading labels file %s …", args.labels_file)
    labels = load_labels(args.labels_file)
    log.info("  %d genotypes", len(labels))

    log.info("Loading genotype → gene mapping …")
    g2m = load_genotype_gene_map(args.genotype_long)
    log.info("  %d (genotype, gene) pairs", len(g2m))

    g2m_index: Dict[str, List[str]] = {}
    for gid, sub in g2m.groupby("genotype_id"):
        g2m_index[str(gid)] = [
            str(g).upper() for g in sub["gene_symbol"].tolist()
            if g and str(g) != "NAN"
        ]

    log.info("Loading DisGeNET associations %s …", args.disgenet_tsv)
    if not args.disgenet_tsv.exists():
        log.error("DisGeNET TSV not found. Run fetch_disgenet_multi_disorder.py "
                  "first.")
        return 2
    disgenet = load_disgenet_associations(args.disgenet_tsv)
    log.info("  %d associations across %d genes / %d diseases",
             len(disgenet),
             disgenet["geneSymbol"].nunique() if not disgenet.empty else 0,
             disgenet["diseaseUMLSCUI"].nunique() if not disgenet.empty else 0)

    tier_count_rows: List[Dict[str, Any]] = []
    source_count_rows: List[Dict[str, Any]] = []
    run_summary: Dict[str, Any] = {"per_disorder": {}}

    for d in cfg["disorders"]:
        name  = d["name"]
        label = d["label"]
        log.info("=== %s (%s) ===", name, label)

        doids = set(d["doids"])
        cuis  = set(d["umls_cuis"])
        disease_terms_re = re.compile(d["disease_terms_regex"], re.IGNORECASE)

        dgm_genes = set(dgm.loc[dgm["doid"].isin(doids),
                                "human_gene_symbol"].dropna().tolist())
        dgm_genes.discard("")
        dgm_genes.discard("NAN")
        log.info("  MGI_DiseaseGeneModel genes for this disorder: %d", len(dgm_genes))

        sfari_set: Set[str] = set()
        if d.get("special_sources", {}).get("sfari", {}).get("enabled"):
            sfari_path = Path(d["special_sources"]["sfari"]["file"])
            sfari_set = {g.upper() for g in load_sfari(sfari_path)}
            log.info("  SFARI genes:                              %d", len(sfari_set))

        gene_evidence = build_gene_evidence_for_disorder(
            disgenet, cuis, source_class,
            min_curated_score=args.min_disgenet_curated_score,
            min_pmids=args.min_disgenet_pmids,
        )
        log.info("  DisGeNET-evidence genes for this disorder:  %d", len(gene_evidence))

        disease_terms_mask = labels["disease_terms"].str.contains(
            disease_terms_re, na=False
        )
        disease_terms_genotypes = set(labels.loc[disease_terms_mask, "genotype_id"])
        log.info("  Tier-0 disease_terms genotypes:             %d",
                 len(disease_terms_genotypes))

        out_rows: List[Dict[str, Any]] = []
        for _, lr in labels.iterrows():
            gid = lr["genotype_id"]
            in_dt = gid in disease_terms_genotypes

            genes = g2m_index.get(gid, [])
            genes = [g for g in genes if g and g != "NAN"]

            in_mgi   = any(g in dgm_genes for g in genes)
            in_sfari = any(g in sfari_set for g in genes) if sfari_set else False
            agg = {"sources": set(), "counts": {k: 0 for k in source_class}}
            for g in genes:
                if g in gene_evidence:
                    agg["sources"] |= gene_evidence[g]["sources"]
            agg["counts"] = classify_sources(agg["sources"], source_class)

            n_mend_conf  = agg["counts"].get("mendelian_confirmed", 0)
            n_mend_sugg  = agg["counts"].get("mendelian_suggestive", 0)
            n_common_var = agg["counts"].get("common_variant", 0)
            n_lit_only   = agg["counts"].get("literature_only", 0)

            tier, max_cls = assign_tier(
                in_dt, in_mgi, in_sfari,
                n_mend_conf, n_mend_sugg, n_common_var,
            )

            out_rows.append({
                "genotype_id":                gid,
                "gene_symbol":                "|".join(sorted(set(genes))) if genes else "",
                "in_disease_terms":           in_dt,
                "in_mgi_disease_gene_model":  in_mgi,
                "in_sfari":                   in_sfari,
                "n_disgenet_mendelian_confirmed":  n_mend_conf,
                "n_disgenet_mendelian_suggestive": n_mend_sugg,
                "n_disgenet_common_variant":       n_common_var,
                "n_disgenet_literature_only":      n_lit_only,
                "disgenet_sources_summary":   "|".join(sorted(agg["sources"])) if agg["sources"] else "",
                "tier":                       tier,
                "max_evidence_class":         max_cls,
            })

        out_df = pd.DataFrame(out_rows)
        out_path = args.outdir / f"{name}_per_genotype_tiers.tsv"
        safe_write_csv(out_df, out_path, sep="\t", index=False)
        log.info("  wrote %s (%d rows)", out_path, len(out_df))

        tier_counts = out_df["tier"].value_counts().to_dict()
        for t in TIER_ORDER:
            tier_count_rows.append({
                "disorder": name,
                "label":    label,
                "tier":     t,
                "n":        int(tier_counts.get(t, 0)),
            })
        cum = {
            "Tier_0_disease_terms":                int(tier_counts.get("disease_terms", 0)),
            "Tier_1_Mendelian_confirmed_cumulative":
                int(tier_counts.get("disease_terms", 0)) +
                int(tier_counts.get("Mendelian-confirmed", 0)),
            "Tier_1b_Mendelian_suggestive_cumulative":
                int(tier_counts.get("disease_terms", 0)) +
                int(tier_counts.get("Mendelian-confirmed", 0)) +
                int(tier_counts.get("Mendelian-suggestive", 0)),
            "Tier_2_common_variant_permissive_cumulative":
                int(tier_counts.get("disease_terms", 0)) +
                int(tier_counts.get("Mendelian-confirmed", 0)) +
                int(tier_counts.get("Mendelian-suggestive", 0)) +
                int(tier_counts.get("common-variant-permissive", 0)),
            "Tier_none":                            int(tier_counts.get("none", 0)),
        }
        log.info("  tier counts (exclusive):  %s",
                 {t: tier_counts.get(t, 0) for t in TIER_ORDER})
        log.info("  tier counts (cumulative): %s", cum)
        run_summary["per_disorder"][name] = {
            "label":              label,
            "exclusive_tiers":    {t: int(tier_counts.get(t, 0)) for t in TIER_ORDER},
            "cumulative_tiers":   cum,
            "n_total_genotypes":  len(out_df),
        }

        for src_class, members in source_class.items():
            if src_class == "circular_excluded":
                continue
            mask = out_df["disgenet_sources_summary"].apply(
                lambda s: bool(set(str(s).split("|")) & members) if s else False
            )
            source_count_rows.append({
                "disorder":            name,
                "evidence_class":      src_class,
                "n_genotypes_with_class_evidence": int(mask.sum()),
            })

    safe_write_csv(
        pd.DataFrame(tier_count_rows),
        args.outdir / "per_disorder_tier_counts.tsv", sep="\t", index=False,
    )
    safe_write_csv(
        pd.DataFrame(source_count_rows),
        args.outdir / "per_evidence_source_counts.tsv", sep="\t", index=False,
    )
    (args.outdir / "99_run_config.json").write_text(
        json.dumps(run_summary, indent=2),
    )


    log.info("\n=== Final per-disorder tier counts ===")
    log.info("%s", pd.DataFrame(tier_count_rows).pivot(
        index="disorder", columns="tier", values="n").fillna(0).astype(int).to_string())
    log.info("\nDone. Outputs at %s", args.outdir.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
