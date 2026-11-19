#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd


def read_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() in {".tsv", ".txt"}:
        return pd.read_csv(path, sep="\t")
    return pd.read_csv(path)


def detect_rank_col(df: pd.DataFrame) -> str:
    candidates = [
        "recommended_rank", "strict_focused_rank", "strict_tolerant_rank",
        "strict_rank", "broad_rank", "rank"
    ]
    for c in candidates:
        if c in df.columns:
            return c
    raise KeyError(f"Could not find rank column among: {candidates}")


def detect_score_col(df: pd.DataFrame) -> str:
    candidates = [
        "rank_score", "recommended_score", "strict_specificity_score",
        "broad_specificity_score", "overall_support_score_mean"
    ]
    for c in candidates:
        if c in df.columns:
            return c
    raise KeyError(f"Could not find score column among: {candidates}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest_tsv", type=str, required=True)
    ap.add_argument("--outdir", type=str, default="run_stability_eval")
    ap.add_argument("--top_k_list", type=str, default="5,10,20")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    manifest = read_table(args.manifest_tsv).copy()
    top_k_list = [int(x.strip()) for x in args.top_k_list.split(",") if x.strip()]

    runs = []
    for _, row in manifest.iterrows():
        run_name = row["run_name"]
        df = read_table(row["ranking_tsv"]).copy()
        rank_col = detect_rank_col(df)
        score_col = detect_score_col(df)
        tmp = df[["genotype_id", rank_col, score_col]].copy()
        tmp["run_name"] = run_name
        runs.append(tmp.rename(columns={rank_col: "rank", score_col: "score"}))

    allr = pd.concat(runs, axis=0, ignore_index=True)
    allr.to_csv(outdir / "01_all_run_ranks.tsv", sep="\t", index=False)

    rows = []
    run_names = manifest["run_name"].tolist()
    for i in range(len(run_names)):
        for j in range(i + 1, len(run_names)):
            a = allr[allr["run_name"] == run_names[i]].copy()
            b = allr[allr["run_name"] == run_names[j]].copy()
            for k in top_k_list:
                ta = set(a.sort_values("rank").head(k)["genotype_id"])
                tb = set(b.sort_values("rank").head(k)["genotype_id"])
                overlap = len(ta & tb)
                rows.append({
                    "run_a": run_names[i],
                    "run_b": run_names[j],
                    "k": k,
                    "overlap_n": overlap,
                    "overlap_frac": overlap / k,
                })
    pd.DataFrame(rows).to_csv(outdir / "02_pairwise_topk_overlap.tsv", sep="\t", index=False)

    agg = (
        allr.groupby("genotype_id", dropna=False)
        .agg(
            n_runs=("run_name", "nunique"),
            rank_mean=("rank", "mean"),
            rank_sd=("rank", "std"),
            score_mean=("score", "mean"),
            score_sd=("score", "std"),
        )
        .reset_index()
        .sort_values(["rank_mean", "score_mean"], ascending=[True, False])
    )
    agg.to_csv(outdir / "03_genotype_rank_score_variance.tsv", sep="\t", index=False)

    config = {
        "top_k_list": top_k_list,
    }
    (outdir / "04_run_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    print(f"Done. Outputs written to: {outdir.resolve()}")
