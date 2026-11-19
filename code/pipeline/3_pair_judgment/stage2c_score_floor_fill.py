#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd


from safe_write_util import safe_write_csv
def load_config(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".tsv", ".txt"}:
        return pd.read_csv(path, sep="\t")
    return pd.read_csv(path)


def clean(x: str) -> str:
    import re
    return re.sub(r"\s+", " ", str(x or "")).strip()


def parse_fill_records_from_cache(
    raw_jsonl: Path, fill: pd.DataFrame, chunk_size: int = 5,
) -> List[Dict[str, Any]]:
    cached_objs: List[Dict[str, Any]] = []
    with raw_jsonl.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cached_objs.append(json.loads(line))

    fill_records: List[Dict[str, Any]] = []
    cache_idx = 0
    grp = fill.groupby("target_id", dropna=False, sort=False)
    for target_id, g in grp:
        if pd.isna(target_id):
            continue
        g = g.reset_index(drop=True)
        n = len(g)
        for start in range(0, n, chunk_size):
            chunk = g.iloc[start: start + chunk_size]
            if cache_idx >= len(cached_objs):
                break
            obj = cached_objs[cache_idx]
            cache_idx += 1
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
    return fill_records


def merge_and_write(
    rer: pd.DataFrame,
    fill_records: List[Dict[str, Any]],
    outdir: Path,
    score_floor: float,
    cfg_runtime: Dict[str, Any],
) -> None:
    fill_df = pd.DataFrame(fill_records)
    merged = rer.copy()
    action_delta = {"promote": 0.10, "keep": 0.0, "demote": -0.10, "abstain": -0.25}
    if not fill_df.empty:
        key = ["target_id", "mp_id", "mp_term"]
        n_before = len(fill_df)
        fill_df = fill_df.drop_duplicates(subset=key, keep="last")
        if len(fill_df) != n_before:
            print(f"  [B1] fill verdicts deduplicated on {key}: {n_before} -> {len(fill_df)}")
        n_pre = len(merged)
        merged = merged.merge(fill_df, on=key, how="left", suffixes=("", "_fill"))
        if len(merged) != n_pre:
            raise AssertionError(f"B1 regression in the reuse path: row count {n_pre} -> "
                                 f"{len(merged)}.")
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
                f"B1 NOT SATISFIED in the reuse path: {len(merged)} rows over {n_unique} unique "
                f"{tuple(kcols)} keys. Refusing to write a substrate that over-counts evidence.")
    safe_write_csv(merged, outdir / "03_reranked_pairs_filled.tsv", sep="\t", index=False)

    n_total = len(merged)
    n_orig_llm = int(rer["rerank_action"].notna().sum()) if "rerank_action" in rer.columns else 0
    n_filled = int(len(fill_df))
    n_llm_post = int(merged["rerank_action"].notna().sum()) if "rerank_action" in merged.columns else 0
    summary = {
        "n_total_pairs": int(n_total),
        "score_floor": float(score_floor),
        "fill_candidate_pool": int(cfg_runtime.get("fill_candidate_pool", 0)),
        "n_llm_calls_in_fill_pass": int(cfg_runtime.get("n_llm_calls", 0)),
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
    safe_write_csv(pd.DataFrame([summary]), outdir / "04_rerank_fill_summary.tsv", sep="\t", index=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=str, required=True)
    ap.add_argument("--rerank_dir", type=str, default=None)
    ap.add_argument("--candidate_feature_tsv", type=str, default=None)
    ap.add_argument("--outdir", type=str, default=None)
    ap.add_argument("--reuse_llm_responses_from", type=str, default=None)
    ap.add_argument("--model", type=str, default=None)
    ap.add_argument("--score_floor", type=float, default=None)
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    disorder_id = cfg["disorder"]["id"]
    s2r = cfg["stage2_rerank"]
    raw_sf = s2r.get("score_floor", 0.57)
    if isinstance(raw_sf, dict):
        cfg_score_floor = float(raw_sf.get("value", 0.57))
    else:
        cfg_score_floor = float(raw_sf)
    score_floor = args.score_floor if args.score_floor is not None else cfg_score_floor

    rerank_dir = Path(args.rerank_dir or s2r["outdir"])
    outdir = Path(args.outdir or rerank_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    cand_default = (
        cfg.get("stage2_candidate_features", {}).get("outdir", "").rstrip("/")
        + "/04_candidate_feature_table.tsv"
    )
    cand_tsv = Path(args.candidate_feature_tsv or cand_default)

    print(f"=== stage2c_score_floor_fill: disorder={disorder_id} ===")
    print(f"  rerank_dir:  {rerank_dir}")
    print(f"  outdir:      {outdir.resolve()}")
    print(f"  score_floor: {score_floor}")

    if args.reuse_llm_responses_from:
        baseline_dir = Path(args.reuse_llm_responses_from)
        baseline_raw = baseline_dir / "02_rerank_fill_raw.jsonl"
        if not baseline_raw.exists():
            print(f"ERROR: {baseline_raw} not found", file=sys.stderr)
            return 2
        shutil.copy2(baseline_raw, outdir / "02_rerank_fill_raw.jsonl")

        p_rer = baseline_dir / "03_reranked_pairs.tsv"
        if not p_rer.exists():
            print(f"ERROR: {p_rer} not found", file=sys.stderr)
            return 2
        rer = read_table(p_rer)

        score_col = "transparent_score" if "transparent_score" in rer.columns else "final_pair_score"
        has_action = rer["rerank_action"].notna() if "rerank_action" in rer.columns else pd.Series([False]*len(rer))
        score = pd.to_numeric(rer[score_col], errors="coerce")
        fill_mask = (~has_action) & (score >= score_floor)
        fill = rer[fill_mask].copy()
        print(f"  reuse: fill pool = {len(fill)}; cached responses = "
              f"{sum(1 for _ in open(baseline_raw))}")

        fill_records = parse_fill_records_from_cache(
            baseline_raw, fill, chunk_size=5,
        )

        cfg_runtime = {
            "fill_candidate_pool": len(fill),
            "n_llm_calls": sum(1 for _ in open(baseline_raw)),
        }
        merge_and_write(rer, fill_records, outdir, score_floor, cfg_runtime)

        fill_cfg = {
            "rerank_dir": str(rerank_dir),
            "candidate_feature_tsv": str(cand_tsv),
            "score_floor": score_floor,
            "chunk_size": 5,
            "model": args.model or s2r.get("llm_model", "gpt-5.4"),
            "seed": s2r.get("llm_seed", 1),
            "elapsed_seconds": 0.0,
            "note": (
                "Strategy E (LLM-fill): re-runs the same prompt + schema as "
                "rerank_ambiguous_pairs_api_v3 on every non-LLM-judged pair "
                "above the score floor. The output 03_reranked_pairs_filled.tsv "
                "supersedes 03_reranked_pairs.tsv for downstream aggregation."
            ),
        }
        (outdir / "09_fill_run_config.json").write_text(
            json.dumps(fill_cfg, indent=2), encoding="utf-8",
        )
        print(f"  Done (reuse mode). Outputs at {outdir.resolve()}")
        return 0

    s2r_addendum = s2r.get("developer_prompt_addendum") or ""
    if s2r_addendum:
        import rerank_ambiguous_pairs_api_v3 as R
        try:
            from rerank_ambiguous_pairs_api_v3_mdd import mdd_call_llm_bundle
            R.call_llm_bundle = mdd_call_llm_bundle
        except ImportError:
            pass

    import rerank_score_floor_fill as F
    if s2r_addendum:
        try:
            from rerank_ambiguous_pairs_api_v3_mdd import mdd_call_llm_bundle
            F.call_llm_bundle = mdd_call_llm_bundle
        except ImportError:
            pass

    new_argv = [
        "rerank_score_floor_fill.py",
        "--rerank_dir", str(rerank_dir),
        "--candidate_feature_tsv", str(cand_tsv),
        "--outdir", str(outdir),
        "--score_floor", str(score_floor),
        "--chunk_size", str(s2r.get("chunk_size", 5)),
        "--seed", str(s2r.get("llm_seed", 1)),
    ]
    if args.model or s2r.get("llm_model"):
        new_argv += ["--model", args.model or s2r["llm_model"]]
    sys.argv = new_argv
    return F.main()


if __name__ == "__main__":
    raise SystemExit(main())
