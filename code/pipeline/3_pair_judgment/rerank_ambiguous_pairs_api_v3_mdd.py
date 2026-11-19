#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from typing import Dict

import pandas as pd

import rerank_ambiguous_pairs_api_v3 as R


def mdd_call_llm_bundle(client, model: str, target_id: str, hpo_label: str,
                       target_text: str, domain: str, bundle: pd.DataFrame,
                       seed: int) -> Dict:
    developer_prompt = """
You are reranking ambiguous cross-species phenotype candidate pairs for a
Major Depressive Disorder (MDD) face-validity pipeline aligned to DSM-5-TR.

Important constraints:
- You are not the primary scorer.
- Transparent non-LLM signals have already identified a small ambiguous bundle.
- Your job is only to promote, keep, demote, or abstain on those candidates.
- Ignore any hidden prior about disease genes or depression labels; you are not given them.
- Do not use any hand-built tier or relevance hierarchy; judge only behavioral/sensory/developmental analog quality.

The 9 MDD Criterion A domains for context:
  depressed_mood, anhedonia, weight_appetite_change, sleep_disturbance,
  psychomotor_change, fatigue, worthlessness_guilt,
  concentration_indecisiveness, suicidality.

Bidirectional-domain rule (CRITICAL — MDD-specific):
- Three MDD Criterion A symptoms are INTRINSICALLY BIDIRECTIONAL per
  DSM-5-TR: A.3 weight_appetite_change (gain OR loss), A.4 sleep_disturbance
  (insomnia OR hypersomnia), A.5 psychomotor_change (agitation OR
  retardation). For HPO targets in these three domains, each target encodes
  ONE direction of the axis (e.g., HP:0000713 Agitation is the agitation
  direction of A.5; HP:0031843 Slow thought process is the retardation
  direction).
- When judging analog quality:
    * Same-direction mouse phenotype -> direct_analog or close_support
      (full credit).
    * Opposite-direction mouse phenotype that maps to the SISTER directional
      target on the same axis -> NOT a mismatch. The opposite-direction
      phenotype is the sister target's evidence, not this target's. Use
      weak_support if the phenotype loosely supports either direction; use
      mismatch only if the mouse phenotype is genuinely incompatible with
      the MDD axis (e.g., a metabolic phenotype unrelated to the
      psychomotor / sleep / weight axis).

Definitions:
- comparable_observable=true only if the mouse term is an organism-level or
  developmentally interpretable observable that could plausibly support the
  human target.
- evidence_scope=cellular_or_circuit_only if the term is primarily
  mechanistic physiology or cellular/circuit description rather than a
  behavioral/sensory/developmental organism-level phenotype.
- strict_eligible=true only for high-quality organism-level analogs suitable
  for strict MDD-domain support.
- broad_eligible=true for weaker but still meaningful support.
- abstain if none of the candidates are suitable organism-level analogs.

Do not invent new candidates. Evaluate only the listed bundle.
""".strip()

    cand_lines = []
    for i, (_, r) in enumerate(bundle.iterrows(), start=1):
        pieces = [
            f"[{i}] mp_id={r['mp_id']}",
            f"mp_term={r['mp_term']}",
            f"mp_definition={R.clean(r.get('mp_definition', ''))}",
            f"mouse_domain={r['mouse_domain']}",
            f"transparent_score={float(r['transparent_score']):.3f}",
            f"embed={R.fmt_opt(r.get('embed_norm'))}",
            f"lexical={R.fmt_opt(r.get('lexical_norm'))}",
            f"resnik={R.fmt_opt(r.get('resnik_norm'))}",
            f"jaccard={R.fmt_opt(r.get('jaccard_norm'))}",
            f"available_channels={int(r.get('n_available_channels', 0))}",
            f"structural_missing={bool(r.get('structural_missing', False))}",
        ]
        cand_lines.append(" | ".join(pieces))

    user_prompt = f"""
Target ID: {target_id}
Human target label: {hpo_label}
Human target text: {target_text}
Domain: {domain}

Ambiguous candidate bundle:
{chr(10).join(cand_lines)}

Return evaluations for the listed candidates only. Use candidate_index values 1..{len(bundle)}.
""".strip()

    response = client.chat.completions.create(
        model=model,
        temperature=0,
        seed=seed,
        messages=[
            {"role": "developer", "content": developer_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_schema", "json_schema": R.RERANK_SCHEMA},
    )
    return json.loads(response.choices[0].message.content)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--candidate_feature_tsv",
        type=str,
        default="mdd_candidate_features_v1/04_candidate_feature_table.tsv",
    )
    parser.add_argument("--outdir", type=str, default="mdd_pair_rerank_v1")
    parser.add_argument(
        "--model", type=str, default=None,
        help="Override OPENAI_MODEL env var (default gpt-5.4).",
    )
    parser.add_argument(
        "--ambiguity_margin", type=float, default=0.08,
        help="Score-gap below which a target's top candidates are sent to LLM.",
    )
    parser.add_argument(
        "--top_n_bundle", type=int, default=5,
        help="Max candidates per ambiguous-target bundle sent to the LLM.",
    )
    parser.add_argument("--gray_low", type=float, default=0.35)
    parser.add_argument("--gray_high", type=float, default=0.70)
    parser.add_argument("--w_embed", type=float, default=0.45)
    parser.add_argument("--w_lexical", type=float, default=0.25)
    parser.add_argument("--w_resnik", type=float, default=0.20)
    parser.add_argument("--w_jaccard", type=float, default=0.10)
    parser.add_argument("--w_owl", type=float, default=0.0)
    parser.add_argument("--promote_bonus", type=float, default=0.10)
    parser.add_argument("--demote_penalty", type=float, default=0.10)
    parser.add_argument("--require_multiple_channels", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    R.call_llm_bundle = mdd_call_llm_bundle

    print("=== MDD Stage 2b: LLM rerank of ambiguous candidate bundles ===")
    print(f"  candidate table: {args.candidate_feature_tsv}")
    print(f"  outdir:          {args.outdir}")
    print(f"  bidirectional handling: enabled for weight_appetite_change, "
          f"sleep_disturbance, psychomotor_change")
    print()

    new_argv = [
        "rerank_ambiguous_pairs_api_v3.py",
        "--candidate_feature_tsv", args.candidate_feature_tsv,
        "--outdir", args.outdir,
        "--ambiguity_margin", str(args.ambiguity_margin),
        "--top_n_bundle", str(args.top_n_bundle),
        "--seed", str(args.seed),
        "--gray_low", str(args.gray_low),
        "--gray_high", str(args.gray_high),
        "--w_embed", str(args.w_embed),
        "--w_lexical", str(args.w_lexical),
        "--w_resnik", str(args.w_resnik),
        "--w_jaccard", str(args.w_jaccard),
        "--w_owl", str(args.w_owl),
        "--promote_bonus", str(args.promote_bonus),
        "--demote_penalty", str(args.demote_penalty),
    ]
    if args.model:
        new_argv += ["--model", args.model]
    if args.require_multiple_channels:
        new_argv.append("--require_multiple_channels")
    if args.resume:
        new_argv.append("--resume")
    sys.argv = new_argv

    R.main()


if __name__ == "__main__":
    main()
