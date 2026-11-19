#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import pandas as pd


ALLOWED_HUMAN_RELATIONS = {
    "exact",
    "broader",
    "narrower",
    "broader_than_source",
    "narrower_than_source",
    "related",
    "proxy_related",
}

CORE_MP_PATTERNS = [
    r"social",
    r"conspecific",
    r"communication",
    r"communicative",
    r"vocali[sz]",
    r"ultrasonic",
    r"echolali",
    r"repetit",
    r"stereotyp",
    r"persever",
    r"groom",
    r"ritual",
    r"sameness",
    r"sensory",
    r"auditory",
    r"visual",
    r"olfactor",
    r"tactile",
    r"somatosensor",
    r"response to novel",
    r"novel object",
    r"nest building",
    r"marble buri",
]

EXTENDED_MP_PATTERNS = CORE_MP_PATTERNS + [
    r"behavior",
    r"behavioral",
    r"locomot",
    r"activity",
    r"explor",
    r"anx",
    r"fear",
    r"learning",
    r"memory",
    r"cognit",
    r"attention",
    r"motor",
    r"gait",
    r"coordination",
    r"balance",
    r"seizure",
    r"sleep",
    r"startle",
    r"prepulse",
    r"brain",
    r"cortex",
    r"cortical",
    r"hippocamp",
    r"cerebell",
    r"synap",
    r"neuron",
    r"axo",
    r"dendrit",
    r"nervous system",
    r"neuro",
    r"development",
]

GENERIC_MP_PATTERNS = [
    r"^abnormal behavior$",
    r"^abnormal behavioral response$",
    r"^abnormal home cage behavior$",
    r"^abnormal nervous system morphology$",
    r"^abnormal nervous system physiology$",
    r"^abnormal brain morphology$",
    r"^abnormal brain physiology$",
]


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".tsv":
        return pd.read_csv(path, sep="\t")
    return pd.read_csv(path)


def ensure_bool(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().map({
        "true": True,
        "false": False,
        "1": True,
        "0": False,
        "yes": True,
        "no": False,
    }).fillna(False)


def join_text(*parts: Optional[str]) -> str:
    vals = [str(x).strip() for x in parts if pd.notna(x) and str(x).strip()]
    return " ".join(vals)


def compile_union_regex(patterns: Sequence[str]) -> str:
    return "(?:" + "|".join(patterns) + ")"


def unique_preserve_order(items: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def load_human_profile(
    path: Path,
    min_confidence: float,
    exclude_hpo_ids: Set[str],
) -> pd.DataFrame:
    df = read_table(path).copy()
    required = {"hpo_id", "hpo_label"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required HPO columns: {sorted(missing)}")

    for col, default in {
        "centrality": "supporting",
        "mapping_relation": "exact",
        "confidence": 1.0,
        "manual_review": False,
        "category": "other",
        "normalized_phenotype": "",
        "temporality": "unspecified",
        "rationale": "",
    }.items():
        if col not in df.columns:
            df[col] = default

    df["manual_review"] = ensure_bool(df["manual_review"])
    df["confidence"] = pd.to_numeric(df["confidence"], errors="coerce").fillna(0.0)
    df["mapping_relation"] = df["mapping_relation"].astype(str).str.strip().str.lower()
    df["centrality"] = df["centrality"].astype(str).str.strip().str.lower()

    df = df[df["hpo_id"].notna()].copy()
    df["hpo_id"] = df["hpo_id"].astype(str).str.strip()
    df = df[~df["hpo_id"].isin(exclude_hpo_ids)].copy()
    df = df[df["confidence"] >= min_confidence].copy()
    df = df[df["mapping_relation"].isin(ALLOWED_HUMAN_RELATIONS)].copy()
    df = df.drop_duplicates(subset=["hpo_id"]).reset_index(drop=True)

    if df.empty:
        raise ValueError("No HPO terms remain after applying filters.")

    df["layer_core"] = df["centrality"].eq("core")
    df["layer_extended"] = df["centrality"].isin(["core", "supporting"])
    df["layer_full"] = True
    return df


def load_mouse_profiles(path: Path) -> pd.DataFrame:
    df = read_table(path).copy()
    required = {"genotype_id", "mp_id", "mp_term"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required mouse columns: {sorted(missing)}")

    for col in [
        "mp_definition",
        "matched_sfari_genes",
        "allelic_composition",
        "allele_symbols",
        "matched_marker_names",
        "pubmed_ids",
        "autism_disease_terms",
    ]:
        if col not in df.columns:
            df[col] = ""

    df = df[df["genotype_id"].notna() & df["mp_id"].notna()].copy()
    df["genotype_id"] = df["genotype_id"].astype(str).str.strip()
    df["mp_id"] = df["mp_id"].astype(str).str.strip()
    df["mp_term"] = df["mp_term"].astype(str)
    df["mp_definition"] = df["mp_definition"].fillna("").astype(str)
    df["mp_text"] = (
        df["mp_term"].fillna("") + " " + df["mp_definition"].fillna("")
    ).str.lower()

    generic_re = compile_union_regex(GENERIC_MP_PATTERNS)
    core_re = compile_union_regex(CORE_MP_PATTERNS)
    extended_re = compile_union_regex(EXTENDED_MP_PATTERNS)

    df["is_generic_mp"] = df["mp_term"].str.lower().str.contains(generic_re, regex=True, na=False)
    df["layer_core"] = df["mp_text"].str.contains(core_re, regex=True, na=False) & ~df["is_generic_mp"]
    df["layer_extended"] = df["mp_text"].str.contains(extended_re, regex=True, na=False) & ~df["is_generic_mp"]
    df["layer_full"] = True

    keep_cols = [
        c for c in [
            "genotype_id",
            "matched_sfari_genes",
            "allelic_composition",
            "allele_symbols",
            "matched_marker_names",
            "autism_disease_terms",
            "mp_id",
            "mp_term",
            "mp_definition",
            "pubmed_ids",
            "layer_core",
            "layer_extended",
            "layer_full",
            "is_generic_mp",
        ] if c in df.columns
    ]
    df = df[keep_cols].drop_duplicates(subset=["genotype_id", "mp_id"]).reset_index(drop=True)
    return df


@dataclass
class SimilarityColumnMap:
    subject_id: str
    object_id: str
    jaccard: Optional[str]
    ancestor_ic: Optional[str]
    phenodigm: Optional[str]
    ancestor_id: Optional[str]
    ancestor_label: Optional[str]


def find_first_present(columns: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    norm = {c.lower(): c for c in columns}
    for cand in candidates:
        if cand.lower() in norm:
            return norm[cand.lower()]
    return None


def detect_similarity_columns(df: pd.DataFrame) -> SimilarityColumnMap:
    cols = list(df.columns)
    subject_id = find_first_present(cols, [
        "subject_id", "subject", "term1", "set1_term", "source_id", "source",
    ])
    object_id = find_first_present(cols, [
        "object_id", "object", "term2", "set2_term", "target_id", "target",
    ])
    jaccard = find_first_present(cols, [
        "jaccard_similarity", "jaccard", "jaccard_score",
    ])
    ancestor_ic = find_first_present(cols, [
        "ancestor_information_content", "ancestor_ic", "information_content", "ic",
    ])
    phenodigm = find_first_present(cols, [
        "phenodigm_score", "phenodigm", "score",
    ])
    ancestor_id = find_first_present(cols, ["ancestor_id", "match_subsumer", "subsumer_id"])
    ancestor_label = find_first_present(cols, ["ancestor_label", "match_subsumer_label", "subsumer_label"])

    if subject_id is None or object_id is None:
        raise ValueError(
            "Could not identify subject/object term columns in the similarity table. "
            f"Columns seen: {cols}"
        )
    return SimilarityColumnMap(
        subject_id=subject_id,
        object_id=object_id,
        jaccard=jaccard,
        ancestor_ic=ancestor_ic,
        phenodigm=phenodigm,
        ancestor_id=ancestor_id,
        ancestor_label=ancestor_label,
    )


def write_term_list(path: Path, terms: Iterable[str]) -> None:
    path.write_text("\n".join(unique_preserve_order(t for t in terms if t)), encoding="utf-8")


def maybe_generate_pairwise_similarity(
    pairwise_similarity_tsv: Optional[Path],
    phenio_db: Optional[Path],
    ic_file: Optional[Path],
    hp_terms: Sequence[str],
    mp_terms: Sequence[str],
    workdir: Path,
    min_jaccard_similarity: float,
    predicates: str,
) -> Path:
    if pairwise_similarity_tsv is not None:
        if not pairwise_similarity_tsv.exists():
            raise FileNotFoundError(f"Pairwise similarity file not found: {pairwise_similarity_tsv}")
        return pairwise_similarity_tsv

    if phenio_db is None or ic_file is None:
        raise ValueError(
            "Either provide --pairwise_similarity_tsv, or provide both --phenio_db and --ic_file "
            "so the script can call `runoak similarity`."
        )

    hp_path = workdir / "hp_terms.txt"
    mp_path = workdir / "mp_terms.txt"
    out_path = workdir / "hp_mp_pairwise_similarity.tsv"

    write_term_list(hp_path, hp_terms)
    write_term_list(mp_path, mp_terms)

    adapter = f"semsimian:sqlite:{phenio_db}"
    cmd = [
        "runoak",
        "-i",
        adapter,
        "similarity",
        "-p",
        predicates,
        "--set1-file",
        str(hp_path),
        "--set2-file",
        str(mp_path),
        "--min-jaccard-similarity",
        str(min_jaccard_similarity),
        "--information-content-file",
        str(ic_file),
        "-O",
        "csv",
        "-o",
        str(out_path),
    ]

    print("Running OAK/SemSimian command:")
    print("  " + shlex.join(cmd))
    subprocess.run(cmd, check=True)
    if not out_path.exists():
        raise RuntimeError("OAK command completed but did not produce the expected similarity TSV.")
    return out_path


def load_similarity_table(path: Path) -> Tuple[pd.DataFrame, SimilarityColumnMap]:
    df = read_table(path).copy()
    cmap = detect_similarity_columns(df)

    out = pd.DataFrame({
        "subject_id": df[cmap.subject_id].astype(str).str.strip(),
        "object_id": df[cmap.object_id].astype(str).str.strip(),
    })
    if cmap.jaccard:
        out["jaccard_similarity"] = pd.to_numeric(df[cmap.jaccard], errors="coerce")
    else:
        out["jaccard_similarity"] = pd.NA

    if cmap.ancestor_ic:
        out["ancestor_information_content"] = pd.to_numeric(df[cmap.ancestor_ic], errors="coerce")
    else:
        out["ancestor_information_content"] = pd.NA

    if cmap.phenodigm:
        out["phenodigm_score"] = pd.to_numeric(df[cmap.phenodigm], errors="coerce")
    else:
        out["phenodigm_score"] = pd.NA

    out["ancestor_id"] = df[cmap.ancestor_id] if cmap.ancestor_id else pd.NA
    out["ancestor_label"] = df[cmap.ancestor_label] if cmap.ancestor_label else pd.NA

    out = out.dropna(subset=["subject_id", "object_id"]).drop_duplicates().reset_index(drop=True)
    return out, cmap


def choose_metric_column(df: pd.DataFrame, preferred_metric: str) -> str:
    preferred_metric = preferred_metric.strip().lower()
    if preferred_metric == "phenodigm":
        col = "phenodigm_score"
    elif preferred_metric in {"ancestor_ic", "ic", "ancestor_information_content"}:
        col = "ancestor_information_content"
    elif preferred_metric in {"jaccard", "jaccard_similarity"}:
        col = "jaccard_similarity"
    else:
        raise ValueError(f"Unsupported metric: {preferred_metric}")

    if col not in df.columns or df[col].isna().all():
        fallbacks = ["phenodigm_score", "ancestor_information_content", "jaccard_similarity"]
        for fb in fallbacks:
            if fb in df.columns and not df[fb].isna().all():
                print(f"Requested metric '{preferred_metric}' not available; falling back to '{fb}'.")
                return fb
        raise ValueError("No usable similarity metric column found in pairwise similarity table.")
    return col


def build_pair_lookup(sim_df: pd.DataFrame, metric_col: str) -> Dict[Tuple[str, str], dict]:
    lookup: Dict[Tuple[str, str], dict] = {}
    for row in sim_df.itertuples(index=False):
        key = (row.subject_id, row.object_id)
        score = getattr(row, metric_col)
        if pd.isna(score):
            continue
        prev = lookup.get(key)
        if prev is None or float(score) > float(prev[metric_col]):
            lookup[key] = {
                "score": float(score),
                metric_col: float(score),
                "jaccard_similarity": None if pd.isna(row.jaccard_similarity) else float(row.jaccard_similarity),
                "ancestor_information_content": None if pd.isna(row.ancestor_information_content) else float(row.ancestor_information_content),
                "phenodigm_score": None if pd.isna(row.phenodigm_score) else float(row.phenodigm_score),
                "ancestor_id": row.ancestor_id if not pd.isna(row.ancestor_id) else None,
                "ancestor_label": row.ancestor_label if not pd.isna(row.ancestor_label) else None,
            }
    return lookup


def best_match_average(
    hpo_terms: Sequence[str],
    mp_terms: Sequence[str],
    lookup: Dict[Tuple[str, str], dict],
) -> dict:
    hpo_terms = unique_preserve_order(hpo_terms)
    mp_terms = unique_preserve_order(mp_terms)

    if not hpo_terms or not mp_terms:
        return {
            "n_hpo_terms": len(hpo_terms),
            "n_mp_terms": len(mp_terms),
            "mean_best_hpo_to_mp": 0.0,
            "mean_best_mp_to_hpo": 0.0,
            "bma_score": 0.0,
            "nonzero_hpo_fraction": 0.0,
            "nonzero_mp_fraction": 0.0,
            "top_matches": [],
        }

    hpo_best = []
    for hp in hpo_terms:
        best = None
        for mp in mp_terms:
            rec = lookup.get((hp, mp))
            if rec is not None and (best is None or rec["score"] > best["score"]):
                best = {"hpo_id": hp, "mp_id": mp, **rec}
        if best is None:
            best = {"hpo_id": hp, "mp_id": None, "score": 0.0, "jaccard_similarity": None,
                    "ancestor_information_content": None, "phenodigm_score": None,
                    "ancestor_id": None, "ancestor_label": None}
        hpo_best.append(best)

    mp_best = []
    for mp in mp_terms:
        best = None
        for hp in hpo_terms:
            rec = lookup.get((hp, mp))
            if rec is not None and (best is None or rec["score"] > best["score"]):
                best = {"hpo_id": hp, "mp_id": mp, **rec}
        if best is None:
            best = {"hpo_id": None, "mp_id": mp, "score": 0.0, "jaccard_similarity": None,
                    "ancestor_information_content": None, "phenodigm_score": None,
                    "ancestor_id": None, "ancestor_label": None}
        mp_best.append(best)

    mean_best_h = sum(x["score"] for x in hpo_best) / max(len(hpo_best), 1)
    mean_best_m = sum(x["score"] for x in mp_best) / max(len(mp_best), 1)
    bma = (mean_best_h + mean_best_m) / 2.0

    seen = set()
    top_matches = []
    for item in sorted(hpo_best, key=lambda d: d["score"], reverse=True):
        key = (item["hpo_id"], item["mp_id"], item["ancestor_id"])
        if key in seen:
            continue
        seen.add(key)
        top_matches.append(item)

    return {
        "n_hpo_terms": len(hpo_terms),
        "n_mp_terms": len(mp_terms),
        "mean_best_hpo_to_mp": mean_best_h,
        "mean_best_mp_to_hpo": mean_best_m,
        "bma_score": bma,
        "nonzero_hpo_fraction": sum(x["score"] > 0 for x in hpo_best) / max(len(hpo_best), 1),
        "nonzero_mp_fraction": sum(x["score"] > 0 for x in mp_best) / max(len(mp_best), 1),
        "top_matches": top_matches,
    }


def human_terms_for_layer(hpo_df: pd.DataFrame, layer: str) -> pd.DataFrame:
    flag = f"layer_{layer}"
    if flag not in hpo_df.columns:
        raise ValueError(f"Unknown human layer: {layer}")
    return hpo_df[hpo_df[flag]].copy().reset_index(drop=True)


def mouse_terms_for_layer(mp_df: pd.DataFrame, layer: str) -> pd.DataFrame:
    flag = f"layer_{layer}"
    if flag not in mp_df.columns:
        raise ValueError(f"Unknown mouse layer: {layer}")
    return mp_df[mp_df[flag]].copy().reset_index(drop=True)


def compute_scores(
    hpo_df: pd.DataFrame,
    mp_df: pd.DataFrame,
    sim_lookup: Dict[Tuple[str, str], dict],
    all_layer_pairs: bool,
    top_pairs_per_result: int,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    layer_names = ["core", "extended", "full"]

    human_by_layer = {layer: human_terms_for_layer(hpo_df, layer) for layer in layer_names}
    mouse_by_layer = {layer: mouse_terms_for_layer(mp_df, layer) for layer in layer_names}

    genotype_meta = (
        mp_df.groupby("genotype_id", dropna=False)
        .agg({
            c: "first" for c in [
                "matched_sfari_genes", "allelic_composition", "allele_symbols",
                "matched_marker_names", "autism_disease_terms"
            ] if c in mp_df.columns
        })
        .reset_index()
    )

    score_rows: List[dict] = []
    explain_rows: List[dict] = []

    layer_pairs: List[Tuple[str, str]] = []
    if all_layer_pairs:
        for h in layer_names:
            for m in layer_names:
                layer_pairs.append((h, m))
    else:
        layer_pairs = [("core", "core"), ("extended", "extended"), ("full", "full")]

    for genotype_id, geno_df in mp_df.groupby("genotype_id", dropna=False):
        geno_df = geno_df.copy()
        for human_layer, mouse_layer in layer_pairs:
            hp_layer_df = human_by_layer[human_layer]
            mp_layer_df = geno_df[geno_df[f"layer_{mouse_layer}"]].copy()

            hp_terms = hp_layer_df["hpo_id"].tolist()
            mp_terms = unique_preserve_order(mp_layer_df["mp_id"].tolist())
            agg = best_match_average(hp_terms, mp_terms, sim_lookup)

            meta_row = genotype_meta[genotype_meta["genotype_id"] == genotype_id].iloc[0].to_dict()
            row = {
                "genotype_id": genotype_id,
                "human_layer": human_layer,
                "mouse_layer": mouse_layer,
                **meta_row,
                **{k: v for k, v in agg.items() if k != "top_matches"},
            }
            score_rows.append(row)

            hpo_label_map = dict(zip(hp_layer_df["hpo_id"], hp_layer_df["hpo_label"]))
            mp_label_map = dict(zip(geno_df["mp_id"], geno_df["mp_term"]))
            for rank, match in enumerate(agg["top_matches"][:top_pairs_per_result], start=1):
                explain_rows.append({
                    "genotype_id": genotype_id,
                    "human_layer": human_layer,
                    "mouse_layer": mouse_layer,
                    "match_rank": rank,
                    "score": match["score"],
                    "hpo_id": match["hpo_id"],
                    "hpo_label": hpo_label_map.get(match["hpo_id"]),
                    "mp_id": match["mp_id"],
                    "mp_term": mp_label_map.get(match["mp_id"]),
                    "jaccard_similarity": match.get("jaccard_similarity"),
                    "ancestor_information_content": match.get("ancestor_information_content"),
                    "phenodigm_score": match.get("phenodigm_score"),
                    "ancestor_id": match.get("ancestor_id"),
                    "ancestor_label": match.get("ancestor_label"),
                })

    scores = pd.DataFrame(score_rows)
    explain = pd.DataFrame(explain_rows)
    scores = scores.sort_values(["human_layer", "mouse_layer", "bma_score"], ascending=[True, True, False])
    return scores, explain


def write_summary_files(
    outdir: Path,
    hpo_df: pd.DataFrame,
    mp_df: pd.DataFrame,
    pairwise_path: Path,
    similarity_metric: str,
    scores: pd.DataFrame,
    explain: pd.DataFrame,
    config: dict,
) -> None:
    outdir.mkdir(parents=True, exist_ok=True)

    hpo_membership = hpo_df[[
        c for c in [
            "hpo_id", "hpo_label", "normalized_phenotype", "category", "centrality",
            "mapping_relation", "confidence", "manual_review", "layer_core",
            "layer_extended", "layer_full"
        ] if c in hpo_df.columns
    ]].copy()
    hpo_membership.to_csv(outdir / "01_hpo_layer_membership.tsv", sep="\t", index=False)

    mp_membership = mp_df[[
        c for c in [
            "genotype_id", "matched_sfari_genes", "mp_id", "mp_term", "mp_definition",
            "is_generic_mp", "layer_core", "layer_extended", "layer_full"
        ] if c in mp_df.columns
    ]].copy()
    mp_membership.to_csv(outdir / "02_mp_layer_membership.tsv", sep="\t", index=False)

    pd.DataFrame([{"pairwise_similarity_tsv": str(pairwise_path), "metric_used": similarity_metric}]).to_csv(
        outdir / "03_pairwise_similarity_source.tsv", sep="\t", index=False
    )

    scores.to_csv(outdir / "04_genotype_similarity_scores.tsv", sep="\t", index=False)
    explain.to_csv(outdir / "05_top_explanatory_pairs.tsv", sep="\t", index=False)

    top3 = (
        scores.groupby(["human_layer", "mouse_layer"], as_index=False)
        .head(3)
        .reset_index(drop=True)
    )
    top3.to_csv(outdir / "06_top3_per_layer_pair.tsv", sep="\t", index=False)

    if "matched_sfari_genes" in scores.columns:
        gene_rows = []
        for (gene, human_layer, mouse_layer), g in scores.groupby(["matched_sfari_genes", "human_layer", "mouse_layer"], dropna=False):
            g2 = g.sort_values("bma_score", ascending=False)
            gene_rows.append({
                "matched_sfari_genes": gene,
                "human_layer": human_layer,
                "mouse_layer": mouse_layer,
                "n_genotypes": g2["genotype_id"].nunique(),
                "mean_bma_score": g2["bma_score"].mean(),
                "best_genotype_id": g2.iloc[0]["genotype_id"],
                "best_genotype_bma_score": g2.iloc[0]["bma_score"],
            })
        pd.DataFrame(gene_rows).sort_values(
            ["human_layer", "mouse_layer", "mean_bma_score"], ascending=[True, True, False]
        ).to_csv(outdir / "07_gene_level_summary.tsv", sep="\t", index=False)

    (outdir / "run_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Layered ASD mouse-model face-validity scoring with HPO/MP semantic similarity.")
    p.add_argument("--hpo_tsv", type=str, default="07_final_resolved_hpo_terms.tsv")
    p.add_argument("--mp_csv", type=str, default="00_all_matching_autism_genotype_phenotypes_long.csv")
    p.add_argument("--outdir", type=str, default="asd_face_validity_results")

    p.add_argument("--pairwise_similarity_tsv", type=str, default=None,
                   help="Optional precomputed HP<->MP pairwise similarity TSV.")
    p.add_argument("--phenio_db", type=str, default=None,
                   help="Path to phenio-monarch.db for OAK/SemSimian generation.")
    p.add_argument("--ic_file", type=str, default=None,
                   help="Path to merged HP/MP information-content TSV for OAK/SemSimian generation.")
    p.add_argument("--min_jaccard_similarity", type=float, default=0.0,
                   help="Threshold passed to runoak similarity when generating pairwise similarities.")
    p.add_argument("--predicates", type=str, default="i",
                   help="Predicate string passed to OAK, e.g. 'i' or 'i,p,UPHENO:0000001'.")

    p.add_argument("--metric", type=str, default="phenodigm",
                   choices=["phenodigm", "ancestor_ic", "jaccard"],
                   help="Metric used to aggregate pairwise matches into genotype-level scores.")
    p.add_argument("--min_hpo_confidence", type=float, default=0.0)
    p.add_argument("--exclude_hpo_ids", type=str, nargs="*", default=[])
    p.add_argument("--exclude_hpo_ids_file", type=str, default=None,
                   help="Optional text file with one HPO ID per line to exclude.")
    p.add_argument("--all_layer_pairs", action="store_true",
                   help="If set, compute all 3x3 human-layer vs mouse-layer combinations. Default is diagonal only.")
    p.add_argument("--top_pairs_per_result", type=int, default=10)
    return p.parse_args()


def load_exclude_hpo_ids(args: argparse.Namespace) -> Set[str]:
    exclude = set(x.strip() for x in args.exclude_hpo_ids if x and x.strip())
    if args.exclude_hpo_ids_file:
        p = Path(args.exclude_hpo_ids_file)
        if not p.exists():
            raise FileNotFoundError(f"Exclude HPO ID file not found: {p}")
        exclude.update(
            line.strip() for line in p.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
    return exclude


def main() -> None:
    args = parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    exclude_hpo_ids = load_exclude_hpo_ids(args)

    hpo_df = load_human_profile(
        path=Path(args.hpo_tsv),
        min_confidence=args.min_hpo_confidence,
        exclude_hpo_ids=exclude_hpo_ids,
    )
    mp_df = load_mouse_profiles(Path(args.mp_csv))

    all_hpo_terms = hpo_df["hpo_id"].dropna().astype(str).tolist()
    all_mp_terms = mp_df["mp_id"].dropna().astype(str).tolist()

    pairwise_path = maybe_generate_pairwise_similarity(
        pairwise_similarity_tsv=Path(args.pairwise_similarity_tsv) if args.pairwise_similarity_tsv else None,
        phenio_db=Path(args.phenio_db) if args.phenio_db else None,
        ic_file=Path(args.ic_file) if args.ic_file else None,
        hp_terms=all_hpo_terms,
        mp_terms=all_mp_terms,
        workdir=outdir,
        min_jaccard_similarity=args.min_jaccard_similarity,
        predicates=args.predicates,
    )

    sim_df, detected_cols = load_similarity_table(pairwise_path)
    metric_col = choose_metric_column(sim_df, args.metric)
    lookup = build_pair_lookup(sim_df, metric_col=metric_col)

    scores, explain = compute_scores(
        hpo_df=hpo_df,
        mp_df=mp_df,
        sim_lookup=lookup,
        all_layer_pairs=args.all_layer_pairs,
        top_pairs_per_result=args.top_pairs_per_result,
    )

    write_summary_files(
        outdir=outdir,
        hpo_df=hpo_df,
        mp_df=mp_df,
        pairwise_path=pairwise_path,
        similarity_metric=metric_col,
        scores=scores,
        explain=explain,
        config={
            "hpo_tsv": str(Path(args.hpo_tsv).resolve()),
            "mp_csv": str(Path(args.mp_csv).resolve()),
            "pairwise_similarity_tsv": str(pairwise_path.resolve()),
            "metric_requested": args.metric,
            "metric_used": metric_col,
            "phenio_db": args.phenio_db,
            "ic_file": args.ic_file,
            "min_jaccard_similarity": args.min_jaccard_similarity,
            "predicates": args.predicates,
            "min_hpo_confidence": args.min_hpo_confidence,
            "exclude_hpo_ids": sorted(exclude_hpo_ids),
            "all_layer_pairs": args.all_layer_pairs,
            "detected_similarity_columns": detected_cols.__dict__,
        },
    )

    print("Done.")
    print(f"Human HPO terms retained: {hpo_df.shape[0]}")
    print(f"Mouse genotype-MP rows retained: {mp_df.shape[0]}")
    print(f"Pairwise similarity rows loaded: {sim_df.shape[0]}")
    print(f"Metric used: {metric_col}")
    print(f"Results written to: {outdir.resolve()}")


if __name__ == "__main__":
    main()
