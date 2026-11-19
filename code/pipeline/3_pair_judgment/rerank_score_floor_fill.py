#!/usr/bin/env python3
"""rerank_score_floor_fill.py
==========================

Usage
-----
    python rerank_score_floor_fill.py         --rerank_dir asd_pair_rerank_v3_broad_v3         --candidate_feature_tsv asd_candidate_features_broad_v3/04_candidate_feature_table.tsv         --score_floor 0.57         --chunk_size 5         --model gpt-5.4
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rerank_ambiguous_pairs_api_v3 import (
    RERANK_SCHEMA,
    call_llm_bundle,
    clean,
    fmt_opt,
)

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("rerank_fill")


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".tsv", ".txt"}:
        return pd.read_csv(path, sep="\t")
    return pd.read_csv(path)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--rerank_dir", type=str, required=True,
        help="Directory containing the original 03_reranked_pairs.tsv.",
    )
    ap.add_argument(
        "--candidate_feature_tsv", type=str, required=True,
        help="Stage 1 candidate feature table (for full per-pair feature columns).",
    )
    ap.add_argument(
        "--score_floor", type=float, default=0.57,
        help=(
            "transparent_score floor for fill candidates. Default 0.57 = data-"
            "derived broad-eligibility threshold from balanced-accuracy max "
            "(BA=0.736, precision=0.83, recall=0.70 on the original 180 "
            "LLM-judged pairs)."
        ),
    )
    ap.add_argument("--chunk_size", type=int, default=5,
                    help="Max candidates per LLM call.")
    ap.add_argument("--model", type=str,
                    default=os.environ.get("OPENAI_MODEL", "gpt-5.4"))
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument(
        "--outdir", type=str, default=None,
        help="Output dir. Defaults to --rerank_dir.",
    )
    args = ap.parse_args()

    rerank_dir = Path(args.rerank_dir)
    outdir = Path(args.outdir) if args.outdir else rerank_dir
    outdir.mkdir(parents=True, exist_ok=True)

    p_rer = rerank_dir / "03_reranked_pairs.tsv"
    if not p_rer.exists():
        log.error("Cannot find %s", p_rer)
        return 2
    rer = read_table(p_rer)
    log.info("Loaded reranked pairs: %d rows from %s", len(rer), p_rer)

    has_action = rer["rerank_action"].notna() if "rerank_action" in rer.columns else pd.Series([False] * len(rer))
    score_col = "transparent_score" if "transparent_score" in rer.columns else "final_pair_score"
    if score_col not in rer.columns:
        log.error("Missing transparent_score / final_pair_score column.")
        return 2
    score = pd.to_numeric(rer[score_col], errors="coerce")
    if "retrieval_channels" in rer.columns:
        _chan = rer["retrieval_channels"].astype(str).str.contains("inject", case=False, na=False)
    else:
        _chan = pd.Series([False] * len(rer), index=rer.index)
    if "matched_domain" in rer.columns:
        _md = rer["matched_domain"].astype(str).str.strip().eq("injected")
    else:
        _md = pd.Series([False] * len(rer), index=rer.index)
    injected_mask = _chan | _md
    fill_mask = (~has_action) & ((score >= args.score_floor) | injected_mask)
    _n_inj_forced = int((fill_mask & injected_mask & (score < args.score_floor)).sum())
    log.info("Force-admitted %d below-floor injected descendants to adjudication.", _n_inj_forced)
    fill = rer[fill_mask].copy()
    log.info(
        "Fill-candidate pool: %d non-LLM-judged pairs at score >= %.2f",
        len(fill), args.score_floor,
    )
    if fill.empty:
        log.info("Nothing to fill. Exiting.")
        return 0

    if OpenAI is None:
        log.error("openai package not importable. Install or set up env.")
        return 2
    client = OpenAI()

    raw_jsonl_path = outdir / "02_rerank_fill_raw.jsonl"
    raw_jsonl_path.write_text("")
    fill_records: List[Dict] = []
    grp = fill.groupby("target_id", dropna=False, sort=False)
    n_targets = grp.ngroups
    n_calls = 0
    t0 = time.time()
    for ti, (target_id, g) in enumerate(grp, 1):
        if pd.isna(target_id):
            continue
        target_text = clean(g["target_text"].iloc[0])
        hpo_label = clean(g["hpo_label"].iloc[0])
        domain = clean(g["human_domain"].iloc[0])

        g = g.reset_index(drop=True)
        n = len(g)
        for start in range(0, n, args.chunk_size):
            chunk = g.iloc[start: start + args.chunk_size]
            log.info(
                "[%d/%d] target=%s | chunk %d-%d (n=%d)",
                ti, n_targets, target_id,
                start + 1, start + len(chunk), len(chunk),
            )
            try:
                obj = call_llm_bundle(
                    client=client, model=args.model,
                    target_id=str(target_id), hpo_label=hpo_label,
                    target_text=target_text, domain=domain,
                    bundle=chunk, seed=args.seed,
                )
            except Exception as e:
                log.warning("LLM call failed for target %s chunk %d: %s",
                            target_id, start, e)
                continue
            n_calls += 1
            with open(raw_jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(obj) + "\n")
            for rec in obj.get("selected_candidates", []):
                ci = int(rec.get("candidate_index", 0))
                if ci < 1 or ci > len(chunk):
                    continue
                row = chunk.iloc[ci - 1]
                fill_records.append({
                    "target_id": str(target_id),
                    "mp_id": str(row["mp_id"]),
                    "mp_term": str(row.get("mp_term", "")),
                    **{k: rec.get(k) for k in (
                        "rerank_action", "comparable_observable", "evidence_scope",
                        "behavioral_analog_type", "strict_eligible", "broad_eligible",
                        "reason",
                    )},
                })

    fill_df = pd.DataFrame(fill_records)
    log.info(
        "LLM fill done: %d calls, %d candidate-decisions, %.1fs",
        n_calls, len(fill_df), time.time() - t0,
    )

    merged = rer.copy()
    if not fill_df.empty:
        key = ["target_id", "mp_id", "mp_term"]
        n_before_dedup = len(fill_df)
        fill_df = fill_df.drop_duplicates(subset=key, keep="last")
        if len(fill_df) != n_before_dedup:
            log.warning("fill verdicts deduplicated on %s: %d -> %d",
                        key, n_before_dedup, len(fill_df))
        n_pre_merge = len(merged)
        merged = merged.merge(
            fill_df, on=key, how="left", suffixes=("", "_fill"),
        )
        if len(merged) != n_pre_merge:
            raise AssertionError(
                f"B1 regression: the fill merge changed the row count, {n_pre_merge} -> "
                f"{len(merged)}. The merge key {key} is still not unique in fill_df.")
        action_delta = {"promote": 0.10, "keep": 0.0, "demote": -0.10, "abstain": -0.25}
        cols_to_overlay = [
            "rerank_action", "comparable_observable", "evidence_scope",
            "behavioral_analog_type", "strict_eligible", "broad_eligible",
            "reason",
        ]
        for c in cols_to_overlay:
            fc = c + "_fill"
            if fc in merged.columns:
                fill_present = merged[fc].notna()
                if c not in merged.columns:
                    merged[c] = np.nan
                merged.loc[fill_present, c] = merged.loc[fill_present, fc]
                merged.drop(columns=[fc], inplace=True)
        if "transparent_score" in merged.columns and "final_pair_score" in merged.columns:
            need_recompute = merged["rerank_action"].isin(action_delta.keys()) & \
                             merged.index.isin(merged.index)
            deltas = merged["rerank_action"].map(action_delta).fillna(0.0)
            merged["rerank_delta"] = deltas
            merged["final_pair_score"] = (
                pd.to_numeric(merged["transparent_score"], errors="coerce")
                + deltas
            ).clip(lower=0.0, upper=1.0)

    kcols = [c for c in ("target_id", "hpo_id", "mp_id") if c in merged.columns]
    if kcols:
        n_unique = len(merged.drop_duplicates(subset=kcols))
        if n_unique != len(merged):
            raise AssertionError(
                f"B1 NOT SATISFIED: {len(merged)} rows over {n_unique} unique {tuple(kcols)} keys, "
                f"{len(merged) - n_unique} duplicates. Refusing to write a substrate that "
                f"over-counts evidence.")
        log.info("B1 check passed: %d rows, %d unique %s keys", len(merged), n_unique, tuple(kcols))

    p_filled = outdir / "03_reranked_pairs_filled.tsv"
    merged.to_csv(p_filled, sep="\t", index=False)
    log.info("Wrote filled reranked pairs: %s (%d rows)", p_filled, len(merged))

    n_total = len(merged)
    n_orig_llm = int((rer["rerank_action"].notna()).sum()) if "rerank_action" in rer.columns else 0
    n_filled = int(len(fill_df))
    n_llm_post = int((merged["rerank_action"].notna()).sum()) if "rerank_action" in merged.columns else 0
    summary = {
        "n_total_pairs": int(n_total),
        "score_floor": float(args.score_floor),
        "fill_candidate_pool": int(len(fill)),
        "n_llm_calls_in_fill_pass": int(n_calls),
        "n_fill_decisions": int(n_filled),
        "n_llm_judged_originally": int(n_orig_llm),
        "n_llm_judged_after_fill": int(n_llm_post),
        "post_fill_strict_eligible": int(
            pd.to_numeric(merged["strict_eligible"], errors="coerce").fillna(0).sum()
        ) if "strict_eligible" in merged.columns else 0,
        "post_fill_broad_eligible": int(
            pd.to_numeric(merged["broad_eligible"], errors="coerce").fillna(0).sum()
        ) if "broad_eligible" in merged.columns else 0,
    }
    pd.DataFrame([summary]).to_csv(outdir / "04_rerank_fill_summary.tsv",
                                   sep="\t", index=False)
    log.info("Summary: %s", summary)

    cfg = {
        "rerank_dir": str(rerank_dir),
        "candidate_feature_tsv": args.candidate_feature_tsv,
        "score_floor": args.score_floor,
        "chunk_size": args.chunk_size,
        "model": args.model,
        "seed": args.seed,
        "elapsed_seconds": round(time.time() - t0, 1),
        "note": (
            "Strategy E (LLM-fill): re-runs the same prompt + schema as "
            "rerank_ambiguous_pairs_api_v3 on every non-LLM-judged pair "
            "above the score floor. The output 03_reranked_pairs_filled.tsv "
            "supersedes 03_reranked_pairs.tsv for downstream aggregation."
        ),
    }
    (outdir / "09_fill_run_config.json").write_text(json.dumps(cfg, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
