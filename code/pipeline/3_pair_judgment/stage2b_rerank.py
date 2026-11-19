#!/usr/bin/env python3
"""stage2b_rerank.py
=================

Usage
-----
    python3 stage2b_rerank.py --config asd.disorder.json
    python3 stage2b_rerank.py --config mdd.disorder.json
    python3 stage2b_rerank.py --config asd.disorder.json \\
        --outdir asd_pair_rerank_refactor_test/ \\
        --reuse_llm_responses_from _parity_baseline_v0/asd_pair_rerank_v3_broad_v3/
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

import rerank_ambiguous_pairs_api_v3 as R


def load_config(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


_ORIG_CALL_LLM_BUNDLE = R.call_llm_bundle


def install_prompt_addendum(addendum: str) -> None:

    import re
    src = R.call_llm_bundle.__doc__ or ""

    BASE_DEV_PROMPT = """
You are reranking ambiguous cross-species phenotype candidate pairs for an
ASD/MDD/psychiatric face-validity pipeline aligned to DSM-5-TR.

Important constraints:
- You are not the primary scorer.
- Transparent non-LLM signals have already identified a small ambiguous bundle.
- Your job is only to promote, keep, demote, or abstain on those candidates.
- Ignore any hidden prior about disease genes or disorder labels; you are not given them.
- Do not use any hand-built tier or relevance hierarchy; judge only behavioral/sensory/developmental analog quality.

Definitions:
- comparable_observable=true only if the mouse term is an organism-level or developmentally interpretable observable that could plausibly support the human target.
- evidence_scope=cellular_or_circuit_only if the term is primarily mechanistic physiology or cellular/circuit description rather than a behavioral/sensory/developmental organism-level phenotype.
- strict_eligible=true only for high-quality organism-level analogs suitable for strict-domain support.
- broad_eligible=true for weaker but still meaningful support.
- abstain if none of the candidates are suitable organism-level analogs.

Do not invent new candidates. Evaluate only the listed bundle.
""".strip()

    full_prompt = BASE_DEV_PROMPT
    if addendum:
        full_prompt = full_prompt + "\n\n" + addendum.strip()


    def _patched(client, model, target_id, hpo_label, target_text, domain, bundle, seed):
        return _ORIG_CALL_LLM_BUNDLE(
            client, model, target_id, hpo_label, target_text, domain,
            bundle, seed,
        )

    R.call_llm_bundle = _patched


def configure_module_from_config(cfg: Dict[str, Any]) -> None:
    s2r = cfg.get("stage2_rerank", {}) or {}
    addendum = s2r.get("developer_prompt_addendum") or ""
    if addendum:
        try:
            from rerank_ambiguous_pairs_api_v3_mdd import mdd_call_llm_bundle
            R.call_llm_bundle = mdd_call_llm_bundle
        except ImportError:
            install_prompt_addendum(addendum)


def pre_populate_raw_jsonl(baseline_dir: Path, outdir: Path) -> int:
    src = baseline_dir / "02_rerank_raw.jsonl"
    if not src.exists():
        raise FileNotFoundError(f"{src} not found in baseline")
    outdir.mkdir(parents=True, exist_ok=True)
    dst = outdir / "02_rerank_raw.jsonl"
    shutil.copy2(src, dst)
    with dst.open("r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def build_passthrough_argv(cfg: Dict[str, Any], overrides: Dict[str, Any]) -> List[str]:
    s2c = cfg.get("stage2_candidate_features", {})
    s2r = cfg.get("stage2_rerank", {})
    s2a_outdir = s2c.get("outdir", "asd_candidate_features_broad_v3/").rstrip("/")
    cand_tsv = overrides.get("candidate_feature_tsv") or (
        f"{s2a_outdir}/04_candidate_feature_table.tsv"
    )
    outdir = overrides.get("outdir") or s2r["outdir"]

    weights = s2r.get("weights", {})
    argv = [
        "rerank_ambiguous_pairs_api_v3.py",
        "--candidate_feature_tsv", cand_tsv,
        "--outdir", outdir,
        "--seed", str(s2r.get("llm_seed", 1)),
        "--top_n_bundle", str(s2r.get("top_n_bundle", 5)),
        "--ambiguity_margin", str(s2r.get("ambiguity_margin", 0.08)),
        "--gray_low", str(s2r.get("gray_low", 0.35)),
        "--gray_high", str(s2r.get("gray_high", 0.70)),
        "--w_embed", str(weights.get("embed", 0.45)),
        "--w_lexical", str(weights.get("lexical", 0.25)),
        "--w_resnik", str(weights.get("resnik", 0.20)),
        "--w_jaccard", str(weights.get("jaccard", 0.10)),
        "--w_owl", str(weights.get("owl", 0.0)),
        "--lexical_factor_when_structural_missing",
        str(s2r.get("lexical_factor_when_structural_missing", 1.0)),
        "--promote_bonus", str(s2r.get("promote_bonus", 0.10)),
        "--demote_penalty", str(s2r.get("demote_penalty", 0.10)),
    ]
    model = overrides.get("model") or s2r.get("llm_model")
    if model:
        argv += ["--model", model]
    if overrides.get("resume"):
        argv.append("--resume")
    return argv


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=str, required=True)
    ap.add_argument("--outdir", type=str, default=None)
    ap.add_argument("--candidate_feature_tsv", type=str, default=None)
    ap.add_argument("--reuse_llm_responses_from", type=str, default=None)
    ap.add_argument("--model", type=str, default=None)
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    disorder_id = cfg["disorder"]["id"]
    configure_module_from_config(cfg)

    outdir = Path(args.outdir or cfg["stage2_rerank"]["outdir"])
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"=== stage2b_rerank: disorder={disorder_id} ===")
    print(f"  outdir: {outdir.resolve()}")

    overrides: Dict[str, Any] = {
        "outdir": str(outdir),
        "candidate_feature_tsv": args.candidate_feature_tsv,
        "model": args.model,
    }

    if args.reuse_llm_responses_from:
        baseline_dir = Path(args.reuse_llm_responses_from)
        n = pre_populate_raw_jsonl(baseline_dir, outdir)
        print(f"  reuse: pre-populated 02_rerank_raw.jsonl ({n} cached LLM responses)")
        overrides["resume"] = True
        if not args.candidate_feature_tsv:
            baseline_s2a = Path("_parity_baseline_v0/asd_candidate_features_broad_v3/04_candidate_feature_table.tsv")
            if baseline_s2a.exists():
                s2c_outdir = cfg["stage2_candidate_features"]["outdir"].rstrip("/")
                canonical = Path(f"{s2c_outdir}/04_candidate_feature_table.tsv")
                if not canonical.exists():
                    canonical.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(baseline_s2a, canonical)
                overrides["candidate_feature_tsv"] = str(canonical)

    new_argv = build_passthrough_argv(cfg, overrides)
    print(f"  passthrough argv tail: {' '.join(new_argv[-10:])}")
    sys.argv = new_argv
    R.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
