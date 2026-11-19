#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rerank_dir",
        type=str,
        default="mdd_pair_rerank_v1",
        help="Directory containing 03_reranked_pairs.tsv from Stage 2b.",
    )
    parser.add_argument(
        "--candidate_feature_tsv",
        type=str,
        default="mdd_candidate_features_v1/04_candidate_feature_table.tsv",
    )
    parser.add_argument(
        "--outdir",
        type=str,
        default="mdd_pair_rerank_v1",
        help="Output directory (default same as --rerank_dir; overwrites in place).",
    )
    parser.add_argument(
        "--score_floor", type=float, default=0.57,
        help="transparent_score floor for non-LLM pairs to be sent to fill. "
             "Default 0.57 is the ASD-derived BA-optimal broad-eligibility "
             "threshold; for MDD v1 this is reused as a starting point and "
             "may need MDD-specific re-derivation in v2.",
    )
    parser.add_argument(
        "--chunk_size", type=int, default=5,
        help="Max candidates per LLM call (passed through to the ASD floor-fill).",
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="Override OPENAI_MODEL env var (default gpt-5.4).",
    )
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    import rerank_ambiguous_pairs_api_v3 as R
    from rerank_ambiguous_pairs_api_v3_mdd import mdd_call_llm_bundle
    R.call_llm_bundle = mdd_call_llm_bundle

    import rerank_score_floor_fill as F
    F.call_llm_bundle = mdd_call_llm_bundle

    print("=== MDD Stage 2c: Strategy E LLM-fill for non-LLM-judged pairs ===")
    print(f"  rerank_dir:    {args.rerank_dir}")
    print(f"  candidate:     {args.candidate_feature_tsv}")
    print(f"  outdir:        {args.outdir}")
    print(f"  score_floor:   {args.score_floor}")
    print(f"  bidirectional handling: inherited from rerank_ambiguous_pairs_api_v3_mdd")
    print()

    new_argv = [
        "rerank_score_floor_fill.py",
        "--rerank_dir", args.rerank_dir,
        "--candidate_feature_tsv", args.candidate_feature_tsv,
        "--outdir", args.outdir,
        "--score_floor", str(args.score_floor),
        "--chunk_size", str(args.chunk_size),        "--seed", str(args.seed),
    ]
    if args.model:
        new_argv += ["--model", args.model]
    sys.argv = new_argv

    F.main()


if __name__ == "__main__":
    main()
