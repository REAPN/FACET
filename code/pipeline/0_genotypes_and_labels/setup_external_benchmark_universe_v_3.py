#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd


def clean_names(x: str) -> str:
    x = x.lower()
    x = re.sub(r"[^a-z0-9]+", "_", x)
    x = re.sub(r"^_|_$", "", x)
    return x


def find_gene_symbol_col(cols: Iterable[str]) -> str:
    cols = list(cols)
    clean = [clean_names(c) for c in cols]
    exact_hits = {"gene_symbol", "gene_symbols", "symbol", "gene"}
    for raw, cln in zip(cols, clean):
        if cln in exact_hits:
            return raw
    for raw, cln in zip(cols, clean):
        if re.search(r"gene.*symbol|symbol.*gene|gene_symbol", cln):
            return raw
    raise ValueError("Could not identify the gene-symbol column in the SFARI CSV.")


def collapse_unique(vals: Iterable[object], sep: str = " | ") -> str | float:
    out = []
    seen = set()
    for v in vals:
        if pd.isna(v):
            continue
        s = str(v).strip()
        if not s:
            continue
        if s not in seen:
            seen.add(s)
            out.append(s)
    if not out:
        return np.nan
    return sep.join(sorted(out))


def read_tabular_auto(path: Path, header: Optional[bool] = None) -> pd.DataFrame:
    path = Path(path)
    compression = "gzip" if path.suffix == ".gz" else None
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, compression=compression)
    hdr = 0 if header else None
    return pd.read_csv(
        path,
        sep="	",
        header=hdr,
        compression=compression,
        dtype=str,
        keep_default_na=False,
        na_values=["", "NA", "N/A"],
        quoting=3,
        engine="python",
    )


def parse_bool_override(val) -> Optional[bool]:
    if pd.isna(val):
        return None
    s = str(val).strip().lower()
    if s == "":
        return None
    if s in {"1", "true", "t", "yes", "y"}:
        return True
    if s in {"0", "false", "f", "no", "n"}:
        return False
    raise ValueError(f"Could not parse override boolean value: {val}")


def derive_benchmark_group(
    is_asd: bool,
    is_neurodevelopmental: bool,
    is_psychiatric: bool,
    is_language_social_confound: bool,
    is_mixed_asd: Optional[bool] = None,
) -> str:
    if is_mixed_asd is None:
        is_mixed_asd = bool(
            is_asd and (is_neurodevelopmental or is_psychiatric or is_language_social_confound)
        )

    if is_asd and not is_mixed_asd:
        return "ASD_primary"
    if is_mixed_asd:
        return "ASD_mixed"
    if is_language_social_confound:
        return "language_social_confound_non_ASD"
    if is_neurodevelopmental:
        return "NDD_non_ASD"
    if is_psychiatric:
        return "psychiatric_non_NDD_non_ASD"
    return "broad_other"


def read_sfari(sfari_file: Path) -> tuple[pd.DataFrame, np.ndarray]:
    sfari = pd.read_csv(sfari_file)
    gene_col = find_gene_symbol_col(sfari.columns)
    sfari = sfari.copy()
    sfari["sfari_gene_symbol_raw"] = sfari[gene_col]
    sfari["sfari_gene_symbol"] = sfari["sfari_gene_symbol_raw"].astype(str).str.strip().str.upper()
    sfari = sfari[sfari["sfari_gene_symbol"].notna() & (sfari["sfari_gene_symbol"] != "")]
    sfari = sfari.drop_duplicates(subset=["sfari_gene_symbol"]).reset_index(drop=True)
    return sfari, sfari["sfari_gene_symbol"].unique()


def read_marker_map(marker_file: Path) -> pd.DataFrame:
    mrk = read_tabular_auto(marker_file, header=False)
    if mrk.shape[1] < 9:
        raise ValueError("MRK_List2 appears to have fewer than 9 columns than expected.")
    mrk = mrk.iloc[:, [0, 6, 8]].copy()
    mrk.columns = ["marker_id", "mouse_symbol", "marker_name"]
    mrk["marker_id"] = mrk["marker_id"].astype(str).str.strip()
    mrk["mouse_symbol"] = mrk["mouse_symbol"].astype(str).str.strip().str.upper()
    mrk["marker_name"] = mrk["marker_name"].astype(str).str.strip()
    mrk = mrk[
        mrk["marker_id"].notna() & (mrk["marker_id"] != "") &
        mrk["mouse_symbol"].notna() & (mrk["mouse_symbol"] != "")
    ].drop_duplicates().reset_index(drop=True)
    return mrk


def read_phenogeno(phenogeno_file: Path, marker_map: pd.DataFrame):
    pg = read_tabular_auto(phenogeno_file, header=False)
    if pg.shape[1] < 7:
        raise ValueError("MGI_PhenoGenoMP.rpt appears to have fewer than 7 columns than expected.")
    pg = pg.iloc[:, :7].copy()
    pg.columns = [
        "allelic_composition",
        "allele_symbols",
        "genetic_background",
        "mp_id",
        "pubmed_ids",
        "marker_ids",
        "genotype_id",
    ]
    pg = pg[
        pg["genotype_id"].notna() & (pg["genotype_id"] != "") &
        pg["mp_id"].notna() & (pg["mp_id"] != "") &
        pg["marker_ids"].notna() & (pg["marker_ids"] != "")
    ].copy()

    rows = []
    for _, row in pg.iterrows():
        markers = [m.strip() for m in str(row["marker_ids"]).split("|") if str(m).strip()]
        for marker_id in markers:
            rows.append({
                "genotype_id": row["genotype_id"],
                "allelic_composition": row["allelic_composition"],
                "allele_symbols": row["allele_symbols"],
                "genetic_background": row["genetic_background"],
                "mp_id": row["mp_id"],
                "pubmed_ids": row["pubmed_ids"],
                "marker_ids": row["marker_ids"],
                "marker_id": marker_id,
            })
    pg_long = pd.DataFrame(rows)
    pg_long = pg_long.merge(marker_map, on="marker_id", how="left")
    genotype_gene_map = pg_long[["genotype_id", "marker_id", "mouse_symbol", "marker_name"]].drop_duplicates().reset_index(drop=True)
    return pg, pg_long, genotype_gene_map


def read_mp_vocab(mp_vocab_file: Path) -> pd.DataFrame:
    mp = read_tabular_auto(mp_vocab_file, header=False)
    if mp.shape[1] < 2:
        raise ValueError("VOC_MammalianPhenotype.rpt appears to have fewer than 2 columns than expected.")
    if mp.shape[1] >= 3:
        mp = mp.iloc[:, :3].copy()
        mp.columns = ["mp_id", "mp_term", "mp_definition"]
    else:
        mp = mp.iloc[:, :2].copy()
        mp.columns = ["mp_id", "mp_term"]
        mp["mp_definition"] = np.nan
    mp["mp_id"] = mp["mp_id"].astype(str).str.strip()
    mp["mp_term"] = mp["mp_term"].astype(str).str.strip()
    mp["mp_definition"] = mp["mp_definition"].astype(str).replace({"nan": ""}).str.strip()
    return mp[mp["mp_id"].str.startswith("MP:", na=False)].drop_duplicates(subset=["mp_id"]).reset_index(drop=True)


def read_disease_tables(geno_disease_file: Path, mgi_do_file: Path):
    gd = read_tabular_auto(geno_disease_file, header=False)
    if gd.shape[1] < 10:
        raise ValueError("MGI_Geno_DiseaseDO.rpt appears to have fewer than 10 columns than expected.")
    gd = gd.iloc[:, :10].copy()
    gd.columns = [
        "allelic_composition",
        "allele_symbols",
        "allele_ids",
        "genetic_background",
        "mp_id",
        "pubmed_ids",
        "marker_ids",
        "do_ids",
        "mim_ids",
        "genotype_id",
    ]
    gd = gd[
        gd["genotype_id"].notna() & (gd["genotype_id"] != "") &
        gd["do_ids"].notna() & (gd["do_ids"] != "")
    ].copy()

    rows = []
    for _, row in gd.iterrows():
        do_ids = [x.strip() for x in str(row["do_ids"]).split("|") if str(x).strip()]
        for do_id in do_ids:
            rows.append({
                "genotype_id": row["genotype_id"],
                "do_id": do_id,
                "allelic_composition": row["allelic_composition"],
                "allele_symbols": row["allele_symbols"],
            })
    gd_long = pd.DataFrame(rows)

    do_map = read_tabular_auto(mgi_do_file, header=False)
    if do_map.shape[1] < 2:
        raise ValueError("MGI_DO.rpt appears to have fewer than 2 columns than expected.")
    do_map = do_map.iloc[:, :2].copy()
    do_map.columns = ["do_id", "do_name"]
    do_map["do_id"] = do_map["do_id"].astype(str).str.strip()
    do_map["do_name"] = do_map["do_name"].astype(str).str.strip()
    gd_long = gd_long.merge(do_map.drop_duplicates(subset=["do_id"]), on="do_id", how="left")
    return gd_long


def summarize_genotype_genes(genotype_gene_map: pd.DataFrame, sfari_genes: np.ndarray) -> pd.DataFrame:
    sfari_set = set(sfari_genes.tolist())
    g = genotype_gene_map.copy()
    g["is_sfari_gene"] = g["mouse_symbol"].isin(sfari_set)

    def _agg(df: pd.DataFrame) -> pd.Series:
        matched = df.loc[df["is_sfari_gene"], "mouse_symbol"].dropna().astype(str).tolist()
        matched_ids = df.loc[df["is_sfari_gene"], "marker_id"].dropna().astype(str).tolist()
        matched_names = df.loc[df["is_sfari_gene"], "marker_name"].dropna().astype(str).tolist()
        all_genes = df["mouse_symbol"].dropna().astype(str).tolist()
        return pd.Series({
            "matched_sfari_genes": collapse_unique(matched),
            "matched_marker_ids": collapse_unique(matched_ids),
            "matched_marker_names": collapse_unique(matched_names),
            "n_matched_sfari_genes": len(sorted(set(matched))),
            "contains_sfari_gene": len(matched) > 0,
            "all_genes_in_genotype": collapse_unique(all_genes),
            "n_total_genes_in_genotype": len(sorted(set(all_genes))),
        })

    return g.groupby("genotype_id", dropna=False).apply(_agg).reset_index()


def build_disease_flags(
    disease_terms: str,
    disease_ids: str,
    autism_regex,
    neurodevelopmental_regex,
    psychiatric_regex,
    language_social_confound_regex,
    intellectual_disability_regex,
):
    text = " ".join([
        str(disease_terms) if not pd.isna(disease_terms) else "",
        str(disease_ids) if not pd.isna(disease_ids) else "",
    ])

    is_asd = bool(autism_regex.search(text))
    is_neurodevelopmental = bool(neurodevelopmental_regex.search(text))
    is_psychiatric = bool(psychiatric_regex.search(text))
    is_language_social_confound = bool(language_social_confound_regex.search(text))
    is_intellectual_disability = bool(intellectual_disability_regex.search(text))
    is_mixed_asd = bool(
        is_asd and (is_neurodevelopmental or is_psychiatric or is_language_social_confound)
    )

    benchmark_group = derive_benchmark_group(
        is_asd=is_asd,
        is_neurodevelopmental=is_neurodevelopmental,
        is_psychiatric=is_psychiatric,
        is_language_social_confound=is_language_social_confound,
        is_mixed_asd=is_mixed_asd,
    )

    return {
        "is_asd_model": is_asd,
        "is_neurodevelopmental_model": is_neurodevelopmental,
        "is_psychiatric_model": is_psychiatric,
        "is_language_social_confound": is_language_social_confound,
        "is_intellectual_disability_model": is_intellectual_disability,
        "is_mixed_asd_model": is_mixed_asd,
        "benchmark_group": benchmark_group,
    }


def load_override_table(path: Optional[str]) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Override file not found: {p}")
    df = pd.read_csv(p, dtype=str, keep_default_na=False)
    if "genotype_id" not in df.columns:
        raise ValueError("Override CSV must contain genotype_id.")
    return df


def apply_genotype_overrides(label_frame: pd.DataFrame, override_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if override_df.empty:
        return label_frame.copy(), pd.DataFrame(), pd.DataFrame()

    out = label_frame.copy()
    applied_rows = []
    unmatched_rows = []

    bool_map = {
        "override_is_asd_model": "is_asd_model",
        "override_is_neurodevelopmental_model": "is_neurodevelopmental_model",
        "override_is_psychiatric_model": "is_psychiatric_model",
        "override_is_language_social_confound": "is_language_social_confound",
        "override_is_intellectual_disability_model": "is_intellectual_disability_model",
        "override_is_mixed_asd_model": "is_mixed_asd_model",
    }

    for _, row in override_df.iterrows():
        genotype_id = str(row.get("genotype_id", "")).strip()
        if not genotype_id:
            continue

        mask = out["genotype_id"].astype(str) == genotype_id
        if not mask.any():
            unmatched_rows.append({
                "genotype_id": genotype_id,
                "status": "unmatched_genotype_id",
                "override_reason": row.get("override_reason", ""),
            })
            continue

        current = out.loc[mask].iloc[0].copy()
        updated = current.copy()
        changed_fields = []

        for override_col, base_col in bool_map.items():
            if override_col in row.index:
                parsed = parse_bool_override(row[override_col])
                if parsed is not None and bool(updated[base_col]) != bool(parsed):
                    updated[base_col] = bool(parsed)
                    changed_fields.append(base_col)

        if "override_disease_terms" in row.index and str(row["override_disease_terms"]).strip() != "":
            updated["disease_terms"] = str(row["override_disease_terms"]).strip()
            changed_fields.append("disease_terms")

        if "override_disease_ids" in row.index and str(row["override_disease_ids"]).strip() != "":
            updated["disease_ids"] = str(row["override_disease_ids"]).strip()
            changed_fields.append("disease_ids")

        if "override_is_mixed_asd_model" not in row.index or str(row.get("override_is_mixed_asd_model", "")).strip() == "":
            updated["is_mixed_asd_model"] = bool(
                updated["is_asd_model"] and (
                    updated["is_neurodevelopmental_model"]
                    or updated["is_psychiatric_model"]
                    or updated["is_language_social_confound"]
                )
            )

        recomputed_group = derive_benchmark_group(
            is_asd=bool(updated["is_asd_model"]),
            is_neurodevelopmental=bool(updated["is_neurodevelopmental_model"]),
            is_psychiatric=bool(updated["is_psychiatric_model"]),
            is_language_social_confound=bool(updated["is_language_social_confound"]),
            is_mixed_asd=bool(updated["is_mixed_asd_model"]),
        )
        updated["benchmark_group"] = recomputed_group

        if "override_benchmark_group" in row.index and str(row["override_benchmark_group"]).strip() != "":
            updated["benchmark_group"] = str(row["override_benchmark_group"]).strip()
            changed_fields.append("benchmark_group")

        out.loc[mask, updated.index.tolist()] = updated.values

        applied_rows.append({
            "genotype_id": genotype_id,
            "changed_fields": " | ".join(sorted(set(changed_fields))) if changed_fields else "no_change",
            "old_is_asd_model": current["is_asd_model"],
            "new_is_asd_model": updated["is_asd_model"],
            "old_is_neurodevelopmental_model": current["is_neurodevelopmental_model"],
            "new_is_neurodevelopmental_model": updated["is_neurodevelopmental_model"],
            "old_is_psychiatric_model": current["is_psychiatric_model"],
            "new_is_psychiatric_model": updated["is_psychiatric_model"],
            "old_is_language_social_confound": current["is_language_social_confound"],
            "new_is_language_social_confound": updated["is_language_social_confound"],
            "old_is_intellectual_disability_model": current["is_intellectual_disability_model"],
            "new_is_intellectual_disability_model": updated["is_intellectual_disability_model"],
            "old_is_mixed_asd_model": current["is_mixed_asd_model"],
            "new_is_mixed_asd_model": updated["is_mixed_asd_model"],
            "old_benchmark_group": current["benchmark_group"],
            "new_benchmark_group": updated["benchmark_group"],
            "override_reason": row.get("override_reason", ""),
        })

    return out, pd.DataFrame(applied_rows), pd.DataFrame(unmatched_rows)


def build_genotype_manifest(genotype_summary: pd.DataFrame) -> pd.DataFrame:
    manifest_cols = [
        "genotype_id",
        "matched_sfari_genes",
        "contains_sfari_gene",
        "is_single_gene_model",
        "is_polygenic_model",
        "disease_terms",
        "disease_ids",
        "is_asd_model",
        "is_neurodevelopmental_model",
        "is_psychiatric_model",
        "is_language_social_confound",
        "is_intellectual_disability_model",
        "is_mixed_asd_model",
        "benchmark_group",
        "n_mp_terms",
    ]
    present_cols = [c for c in manifest_cols if c in genotype_summary.columns]
    manifest = genotype_summary[present_cols].copy()
    manifest = manifest.sort_values("genotype_id").reset_index(drop=True)
    manifest["blinded_genotype_id"] = [f"G{i:05d}" for i in range(1, len(manifest) + 1)]
    cols = ["blinded_genotype_id", "genotype_id"] + [c for c in present_cols if c != "genotype_id"]
    return manifest[cols]


def build_override_template(review_table: pd.DataFrame) -> pd.DataFrame:
    template = review_table[[
        "genotype_id",
        "disease_terms",
        "disease_ids",
        "is_asd_model",
        "is_neurodevelopmental_model",
        "is_psychiatric_model",
        "is_language_social_confound",
        "is_intellectual_disability_model",
        "is_mixed_asd_model",
        "benchmark_group",
    ]].copy()

    template = template.rename(columns={
        "is_asd_model": "current_is_asd_model",
        "is_neurodevelopmental_model": "current_is_neurodevelopmental_model",
        "is_psychiatric_model": "current_is_psychiatric_model",
        "is_language_social_confound": "current_is_language_social_confound",
        "is_intellectual_disability_model": "current_is_intellectual_disability_model",
        "is_mixed_asd_model": "current_is_mixed_asd_model",
        "benchmark_group": "current_benchmark_group",
        "disease_terms": "current_disease_terms",
        "disease_ids": "current_disease_ids",
    })

    template["override_is_asd_model"] = ""
    template["override_is_neurodevelopmental_model"] = ""
    template["override_is_psychiatric_model"] = ""
    template["override_is_language_social_confound"] = ""
    template["override_is_intellectual_disability_model"] = ""
    template["override_is_mixed_asd_model"] = ""
    template["override_benchmark_group"] = ""
    template["override_disease_terms"] = ""
    template["override_disease_ids"] = ""
    template["override_reason"] = ""
    return template


def main():
    ap = argparse.ArgumentParser(
        description="Prepare a broad genotype universe and disease-blind MP term table for external ASD benchmarking."
    )
    ap.add_argument("--sfari_file", type=str, default="SFARI-Gene_animal-genes_03-22-2026.csv")
    ap.add_argument("--phenogeno_file", type=str, default="MGI_PhenoGenoMP.rpt")
    ap.add_argument("--mp_vocab_file", type=str, default="VOC_MammalianPhenotype.rpt")
    ap.add_argument("--marker_file", type=str, default="MRK_List2.rpt.gz")
    ap.add_argument("--geno_disease_file", type=str, default="MGI_Geno_DiseaseDO.rpt")
    ap.add_argument("--mgi_do_file", type=str, default="MGI_DO.rpt")
    ap.add_argument("--override_csv", type=str, default=None)
    ap.add_argument("--outdir", type=str, default="broad_benchmark_setup")

    ap.add_argument(
        "--autism_regex",
        type=str,
        default=r"autism spectrum disorder|autistic disorder|autism|autistic features",
    )
    ap.add_argument(
        "--neurodevelopmental_regex",
        type=str,
        default=(
            r"attention deficit hyperactivity disorder|attention-deficit/hyperactivity disorder|adhd|"
            r"neurodevelopmental disorder|developmental delay|global developmental delay|"
            r"intellectual disability|intellectual developmental disorder|"
            r"specific language impairment|developmental language disorder|language delay|speech delay|"
            r"social communication disorder|pragmatic communication disorder|"
            r"developmental coordination disorder|learning disorder|dyslexia"
        ),
    )
    ap.add_argument(
        "--psychiatric_regex",
        type=str,
        default=(
            r"anxiety|social anxiety|anxiety disorder|generalized anxiety disorder|panic disorder|"
            r"phobia|specific phobia|social phobia|selective mutism|"
            r"obsessive-compulsive|obsessive compulsive|ocd|"
            r"obsessive-compulsive disorder|obsessive compulsive disorder|"
            r"tourette|tourette syndrome|tic disorder|"
            r"depression|depressive disorder|major depressive disorder|"
            r"bipolar|bipolar disorder|mania|manic|"
            r"schizophrenia|psychosis|psychotic disorder|"
            r"anorexia|anorexia nervosa|bulimia|bulimia nervosa|eating disorder"
        ),
    )
    ap.add_argument(
        "--language_social_confound_regex",
        type=str,
        default=(
            r"specific language impairment|developmental language disorder|language delay|speech delay|"
            r"social communication disorder|pragmatic communication disorder|"
            r"selective mutism|social anxiety|anxiety disorder|"
            r"receptive language|expressive language"
        ),
    )
    ap.add_argument(
        "--intellectual_disability_regex",
        type=str,
        default=r"intellectual disability|intellectual developmental disorder|mental retardation|global developmental delay",
    )

    ap.add_argument(
        "--model_scope",
        type=str,
        choices=["all", "single_gene_only", "polygenic_only"],
        default="all",
        help="Which genotype complexity class to keep. Default keeps both single-gene and polygenic models.",
    )
    ap.add_argument("--sample_n_genotypes", type=int, default=0)
    ap.add_argument("--sample_seed", type=int, default=1)
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    autism_regex = re.compile(args.autism_regex, flags=re.I)
    neurodevelopmental_regex = re.compile(args.neurodevelopmental_regex, flags=re.I)
    psychiatric_regex = re.compile(args.psychiatric_regex, flags=re.I)
    language_social_confound_regex = re.compile(args.language_social_confound_regex, flags=re.I)
    intellectual_disability_regex = re.compile(args.intellectual_disability_regex, flags=re.I)

    sfari, sfari_genes = read_sfari(Path(args.sfari_file))
    marker_map = read_marker_map(Path(args.marker_file))
    pg, pg_long, genotype_gene_map = read_phenogeno(Path(args.phenogeno_file), marker_map)
    mp = read_mp_vocab(Path(args.mp_vocab_file))
    gd_long = read_disease_tables(Path(args.geno_disease_file), Path(args.mgi_do_file))
    gene_summary = summarize_genotype_genes(genotype_gene_map, sfari_genes)
    gene_summary["is_single_gene_model"] = gene_summary["n_total_genes_in_genotype"].fillna(0).astype(int) == 1
    gene_summary["is_polygenic_model"] = gene_summary["n_total_genes_in_genotype"].fillna(0).astype(int) > 1

    if args.model_scope == "single_gene_only":
        keep_genotype_ids = set(
            gene_summary.loc[gene_summary["is_single_gene_model"], "genotype_id"].astype(str)
        )
        pg = pg[pg["genotype_id"].astype(str).isin(keep_genotype_ids)].copy()
        gene_summary = gene_summary[gene_summary["genotype_id"].astype(str).isin(keep_genotype_ids)].copy()
    elif args.model_scope == "polygenic_only":
        keep_genotype_ids = set(
            gene_summary.loc[gene_summary["is_polygenic_model"], "genotype_id"].astype(str)
        )
        pg = pg[pg["genotype_id"].astype(str).isin(keep_genotype_ids)].copy()
        gene_summary = gene_summary[gene_summary["genotype_id"].astype(str).isin(keep_genotype_ids)].copy()

    disease_summary = (
        gd_long.groupby("genotype_id", dropna=False)
        .agg(
            disease_terms=("do_name", lambda x: collapse_unique(x)),
            disease_ids=("do_id", lambda x: collapse_unique(x)),
            n_disease_terms=(
                "do_name",
                lambda x: len(sorted(set([str(v).strip() for v in x if str(v).strip()])))
            ),
        )
        .reset_index()
    )

    flag_rows = []
    for _, row in disease_summary.iterrows():
        flags = build_disease_flags(
            row["disease_terms"],
            row["disease_ids"],
            autism_regex,
            neurodevelopmental_regex,
            psychiatric_regex,
            language_social_confound_regex,
            intellectual_disability_regex,
        )
        flags["genotype_id"] = row["genotype_id"]
        flag_rows.append(flags)
    disease_summary = disease_summary.merge(pd.DataFrame(flag_rows), on="genotype_id", how="left")

    all_genotype_ids = pd.DataFrame({"genotype_id": sorted(pg["genotype_id"].astype(str).unique())})
    label_frame = all_genotype_ids.merge(disease_summary, on="genotype_id", how="left")

    for col in [
        "is_asd_model",
        "is_neurodevelopmental_model",
        "is_psychiatric_model",
        "is_language_social_confound",
        "is_intellectual_disability_model",
        "is_mixed_asd_model",
    ]:
        label_frame[col] = label_frame[col].fillna(False)
    label_frame["benchmark_group"] = label_frame["benchmark_group"].fillna("broad_other")
    label_frame["disease_terms"] = label_frame["disease_terms"].fillna("")
    label_frame["disease_ids"] = label_frame["disease_ids"].fillna("")
    label_frame["n_disease_terms"] = label_frame["n_disease_terms"].fillna(0).astype(int)

    override_df = load_override_table(args.override_csv)
    label_frame, applied_overrides, unmatched_overrides = apply_genotype_overrides(label_frame, override_df)

    res = pg.merge(mp, on="mp_id", how="left")
    res = res.merge(gene_summary, on="genotype_id", how="left")
    res = res.merge(
        label_frame[[
            "genotype_id",
            "disease_terms",
            "disease_ids",
            "n_disease_terms",
            "is_asd_model",
            "is_neurodevelopmental_model",
            "is_psychiatric_model",
            "is_language_social_confound",
            "is_intellectual_disability_model",
            "is_mixed_asd_model",
            "benchmark_group",
        ]],
        on="genotype_id",
        how="left",
    )

    keep_cols = [
        "genotype_id",
        "allelic_composition",
        "allele_symbols",
        "genetic_background",
        "matched_sfari_genes",
        "n_matched_sfari_genes",
        "contains_sfari_gene",
        "is_single_gene_model",
        "is_polygenic_model",
        "matched_marker_ids",
        "matched_marker_names",
        "all_genes_in_genotype",
        "n_total_genes_in_genotype",
        "disease_terms",
        "disease_ids",
        "n_disease_terms",
        "is_asd_model",
        "is_neurodevelopmental_model",
        "is_psychiatric_model",
        "is_language_social_confound",
        "is_intellectual_disability_model",
        "is_mixed_asd_model",
        "benchmark_group",
        "mp_id",
        "mp_term",
        "mp_definition",
        "pubmed_ids",
    ]
    res = res[keep_cols].drop_duplicates().reset_index(drop=True)
    res.to_csv(outdir / "00_all_genotype_phenotypes_long.csv", index=False)

    genotype_summary = (
        res.groupby("genotype_id", dropna=False)
        .agg(
            allelic_composition=("allelic_composition", lambda x: collapse_unique(x)),
            allele_symbols=("allele_symbols", lambda x: collapse_unique(x)),
            genetic_background=("genetic_background", lambda x: collapse_unique(x)),
            matched_sfari_genes=("matched_sfari_genes", lambda x: collapse_unique(x)),
            n_matched_sfari_genes=("n_matched_sfari_genes", "max"),
            contains_sfari_gene=("contains_sfari_gene", "max"),
            all_genes_in_genotype=("all_genes_in_genotype", lambda x: collapse_unique(x)),
            n_total_genes_in_genotype=("n_total_genes_in_genotype", "max"),
            is_single_gene_model=("is_single_gene_model", "max"),
            is_polygenic_model=("is_polygenic_model", "max"),
            disease_terms=("disease_terms", lambda x: collapse_unique(x)),
            disease_ids=("disease_ids", lambda x: collapse_unique(x)),
            n_disease_terms=("n_disease_terms", "max"),
            is_asd_model=("is_asd_model", "max"),
            is_neurodevelopmental_model=("is_neurodevelopmental_model", "max"),
            is_psychiatric_model=("is_psychiatric_model", "max"),
            is_language_social_confound=("is_language_social_confound", "max"),
            is_intellectual_disability_model=("is_intellectual_disability_model", "max"),
            is_mixed_asd_model=("is_mixed_asd_model", "max"),
            benchmark_group=("benchmark_group", lambda x: collapse_unique(x)),
            n_mp_terms=("mp_id", pd.Series.nunique),
            mp_ids=("mp_id", lambda x: collapse_unique(x)),
            mp_terms=("mp_term", lambda x: collapse_unique(x)),
            pubmed_ids=("pubmed_ids", lambda x: collapse_unique(x)),
        )
        .reset_index()
        .sort_values(["n_mp_terms", "genotype_id"], ascending=[False, True])
    )
    genotype_summary.to_csv(outdir / "01_all_genotype_summary.csv", index=False)

    label_frame.sort_values(["benchmark_group", "genotype_id"]).to_csv(
        outdir / "02_genotype_disease_labels.csv", index=False
    )

    mp_term_blind = (
        res[["mp_id", "mp_term", "mp_definition"]]
        .drop_duplicates(subset=["mp_id"])
        .sort_values("mp_id")
        .reset_index(drop=True)
    )
    mp_term_blind.to_csv(outdir / "03_unique_mp_terms_for_taxonomy_blinded.csv", index=False)

    mp_term_counts = (
        res.groupby(["mp_id", "mp_term", "mp_definition"], dropna=False)
        .agg(
            n_genotypes_total=("genotype_id", pd.Series.nunique),
            n_pubmed_ids=(
                "pubmed_ids",
                lambda x: len(sorted(set([str(v).strip() for v in x if str(v).strip()])))
            ),
            contains_any_sfari_gene=("contains_sfari_gene", "max"),
        )
        .reset_index()
        .sort_values(["n_genotypes_total", "mp_id"], ascending=[False, True])
    )
    mp_term_counts.to_csv(outdir / "04_unique_mp_terms_with_count_context.csv", index=False)

    group_counts = (
        res.groupby(["mp_id", "benchmark_group"], dropna=False)["genotype_id"]
        .nunique().reset_index()
        .pivot(index="mp_id", columns="benchmark_group", values="genotype_id")
        .reset_index().fillna(0)
    )
    mp_with_context = mp_term_counts.merge(group_counts, on="mp_id", how="left")
    mp_with_context.to_csv(outdir / "05_unique_mp_terms_with_group_context.csv", index=False)

    benchmark_group_table = genotype_summary[[
        "genotype_id",
        "matched_sfari_genes",
        "contains_sfari_gene",
        "is_single_gene_model",
        "is_polygenic_model",
        "disease_terms",
        "disease_ids",
        "is_asd_model",
        "is_neurodevelopmental_model",
        "is_psychiatric_model",
        "is_language_social_confound",
        "is_intellectual_disability_model",
        "is_mixed_asd_model",
        "benchmark_group",
        "n_mp_terms",
    ]].copy().sort_values(["benchmark_group", "n_mp_terms", "genotype_id"], ascending=[True, False, True])
    benchmark_group_table.to_csv(outdir / "06_benchmark_group_table.csv", index=False)

    genotype_manifest = build_genotype_manifest(genotype_summary)
    genotype_manifest.to_csv(outdir / "07_genotype_manifest.tsv", sep="	", index=False)

    res_blinded = res.merge(
        genotype_manifest[["genotype_id", "blinded_genotype_id"]],
        on="genotype_id",
        how="left",
    )
    cols = ["blinded_genotype_id"] + [c for c in res_blinded.columns if c != "blinded_genotype_id"]
    res_blinded = res_blinded[cols]
    res_blinded.to_csv(outdir / "08_all_genotype_phenotypes_long_blinded.csv", index=False)

    sfari.to_csv(outdir / "09_sfari_metadata_unique.csv", index=False)

    review_table = genotype_summary[
        (genotype_summary["is_mixed_asd_model"].fillna(False)) |
        (genotype_summary["is_language_social_confound"].fillna(False)) |
        (genotype_summary["is_intellectual_disability_model"].fillna(False))
    ].copy()
    review_table.to_csv(outdir / "10_mixed_or_confound_review_table.csv", index=False)

    override_template = build_override_template(review_table)
    override_template.to_csv(outdir / "11_genotype_override_template.csv", index=False)

    applied_overrides.to_csv(outdir / "12_applied_overrides.csv", index=False)
    unmatched_overrides.to_csv(outdir / "13_unmatched_overrides.csv", index=False)

    if args.sample_n_genotypes and args.sample_n_genotypes > 0:
        n = min(args.sample_n_genotypes, len(genotype_summary))
        sampled = genotype_summary.sample(n=n, random_state=args.sample_seed).copy()
        sampled.to_csv(outdir / f"14_sampled_genotype_ids_seed_{args.sample_seed}_n_{n}.csv", index=False)
        sampled_ids = set(sampled["genotype_id"].tolist())

        sampled_long = res[res["genotype_id"].isin(sampled_ids)].copy()
        sampled_long.to_csv(outdir / f"15_sampled_genotype_phenotypes_long_seed_{args.sample_seed}_n_{n}.csv", index=False)

        sampled_mp = (
            sampled_long[["mp_id", "mp_term", "mp_definition"]]
            .drop_duplicates(subset=["mp_id"])
            .sort_values("mp_id")
            .reset_index(drop=True)
        )
        sampled_mp.to_csv(outdir / f"16_sampled_unique_mp_terms_for_taxonomy_seed_{args.sample_seed}_n_{n}.csv", index=False)

    config = {
        "sfari_file": args.sfari_file,
        "phenogeno_file": args.phenogeno_file,
        "mp_vocab_file": args.mp_vocab_file,
        "marker_file": args.marker_file,
        "geno_disease_file": args.geno_disease_file,
        "mgi_do_file": args.mgi_do_file,
        "override_csv": args.override_csv,
        "autism_regex": args.autism_regex,
        "neurodevelopmental_regex": args.neurodevelopmental_regex,
        "psychiatric_regex": args.psychiatric_regex,
        "language_social_confound_regex": args.language_social_confound_regex,
        "intellectual_disability_regex": args.intellectual_disability_regex,
        "model_scope": args.model_scope,
        "sample_n_genotypes": args.sample_n_genotypes,
        "sample_seed": args.sample_seed,
        "n_sfari_genes": int(len(sfari_genes)),
        "n_universal_genotypes": int(genotype_summary["genotype_id"].nunique()),
        "n_universal_unique_mp_terms": int(mp_term_blind["mp_id"].nunique()),
        "n_asd_models_flagged": int((genotype_summary["is_asd_model"].fillna(False)).sum()),
        "n_ndd_models_flagged": int((genotype_summary["is_neurodevelopmental_model"].fillna(False)).sum()),
        "n_psychiatric_models_flagged": int((genotype_summary["is_psychiatric_model"].fillna(False)).sum()),
        "n_language_social_confounds_flagged": int((genotype_summary["is_language_social_confound"].fillna(False)).sum()),
        "n_intellectual_disability_models_flagged": int((genotype_summary["is_intellectual_disability_model"].fillna(False)).sum()),
        "n_mixed_asd_models_flagged": int((genotype_summary["is_mixed_asd_model"].fillna(False)).sum()),
        "n_overrides_applied": int(applied_overrides.shape[0]),
        "n_overrides_unmatched": int(unmatched_overrides.shape[0]),
    }
    (outdir / "99_run_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    readme = '''
This setup expands the old autism-gated extraction workflow into a broad genotype universe.

Key outputs:
- 00_all_genotype_phenotypes_long.csv
- 01_all_genotype_summary.csv
- 02_genotype_disease_labels.csv
- 03_unique_mp_terms_for_taxonomy_blinded.csv
- 04_unique_mp_terms_with_count_context.csv
- 05_unique_mp_terms_with_group_context.csv
- 06_benchmark_group_table.csv
- 07_genotype_manifest.tsv
- 08_all_genotype_phenotypes_long_blinded.csv
- 09_sfari_metadata_unique.csv
- 10_mixed_or_confound_review_table.csv
- 11_genotype_override_template.csv
- 12_applied_overrides.csv
- 13_unmatched_overrides.csv

Recommended override workflow:
1. Inspect 10_mixed_or_confound_review_table.csv
2. Copy or edit 11_genotype_override_template.csv
3. Fill only the override_* columns you want to change
4. Re-run this script with --override_csv your_file.csv

Suggested next step:
Use 03_unique_mp_terms_for_taxonomy_blinded.csv as the input to disease-blind MP-term
domain/tier assignment. Keep 02_genotype_disease_labels.csv,
05_unique_mp_terms_with_group_context.csv, 06_benchmark_group_table.csv, and
10_mixed_or_confound_review_table.csv for benchmark evaluation and manual review only.

Recommended command:
python3 setup_external_benchmark_universe_v3.py --outdir broad_benchmark_setup

Optional model-scope filters:
python3 setup_external_benchmark_universe_v3.py --outdir broad_benchmark_setup --model_scope all
python3 setup_external_benchmark_universe_v3.py --outdir broad_benchmark_setup --model_scope single_gene_only
python3 setup_external_benchmark_universe_v3.py --outdir broad_benchmark_setup --model_scope polygenic_only
'''.strip()
    (outdir / "README_benchmark_setup.md").write_text(readme, encoding="utf-8")

    print(f"Done. Outputs written to: {outdir.resolve()}")
    print(f"Universal genotypes: {genotype_summary['genotype_id'].nunique()}")
    print(f"Unique MP terms (strictly blinded): {mp_term_blind['mp_id'].nunique()}")
    print(f"Flagged ASD models: {int((genotype_summary['is_asd_model'].fillna(False)).sum())}")
    print(f"Single-gene models retained: {int((genotype_summary['is_single_gene_model'].fillna(False)).sum())}")
    print(f"Polygenic models retained: {int((genotype_summary['is_polygenic_model'].fillna(False)).sum())}")
    print(f"Flagged NDD models: {int((genotype_summary['is_neurodevelopmental_model'].fillna(False)).sum())}")
    print(f"Flagged language/social confounds: {int((genotype_summary['is_language_social_confound'].fillna(False)).sum())}")
    print(f"Flagged intellectual disability models: {int((genotype_summary['is_intellectual_disability_model'].fillna(False)).sum())}")
    print(f"Overrides applied: {int(applied_overrides.shape[0])}")
    print(f"Overrides unmatched: {int(unmatched_overrides.shape[0])}")


if __name__ == "__main__":
    main()
