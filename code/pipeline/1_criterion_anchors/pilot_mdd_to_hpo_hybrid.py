#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import pilot_asd_to_hpo_hybrid_rev as P


MDD_DOMAINS: List[str] = [
    "depressed_mood",
    "anhedonia",
    "weight_appetite_change",
    "sleep_disturbance",
    "psychomotor_change",
    "fatigue",
    "worthlessness_guilt",
    "concentration_indecisiveness",
    "suicidality",
    "other",
]

BIDIRECTIONAL_DOMAINS: List[str] = [
    "weight_appetite_change",
    "sleep_disturbance",
    "psychomotor_change",
]

MDD_SEED_TERMS: Dict[str, List[str]] = {
    "depressed_mood": [
        "depressed mood", "persistent sadness", "tearfulness",
        "hopelessness", "irritable mood",
    ],
    "anhedonia": [
        "anhedonia", "loss of interest", "loss of pleasure",
        "diminished hedonic response", "reduced reward responsiveness",
    ],
    "weight_appetite_change": [
        "weight loss", "weight gain", "decreased appetite",
        "increased appetite", "altered eating behavior",
    ],
    "sleep_disturbance": [
        "insomnia", "hypersomnia", "early morning awakening",
        "fragmented sleep", "altered sleep architecture",
        "decreased REM latency", "abnormal circadian rhythm",
    ],
    "psychomotor_change": [
        "psychomotor agitation", "psychomotor retardation",
        "slowed movement", "restlessness", "fidgeting",
    ],
    "fatigue": [
        "fatigue", "loss of energy", "lethargy", "decreased activity",
    ],
    "worthlessness_guilt": [
        "feelings of worthlessness", "excessive guilt", "low self-esteem",
        "self-reproach",
    ],
    "concentration_indecisiveness": [
        "diminished concentration", "indecisiveness",
        "impaired cognition", "memory complaints",
        "executive dysfunction",
    ],
    "suicidality": [
        "suicidal ideation", "suicide attempt", "death ideation",
        "self-harm",
    ],
}


MDD_EXTRACTION_SCHEMA: Dict[str, Any] = {
    "name": "phenotype_extraction",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "disorder_name": {"type": "string"},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "source_fragment": {"type": "string"},
                        "normalized_phenotype": {"type": "string"},
                        "category": {
                            "type": "string",
                            "enum": MDD_DOMAINS,
                        },
                        "centrality": {
                            "type": "string",
                            "enum": ["core", "supporting", "context_only"],
                        },
                        "polarity": {
                            "type": "string",
                            "enum": ["present", "absent", "negated",
                                     "uncertain", "bidirectional"],
                        },
                        "temporality": {
                            "type": "string",
                            "enum": ["current", "history", "developmental",
                                     "unspecified"],
                        },
                        "notes": {"type": "string"},
                    },
                    "required": [
                        "source_fragment", "normalized_phenotype", "category",
                        "centrality", "polarity", "temporality", "notes",
                    ],
                },
            },
        },
        "required": ["disorder_name", "items"],
    },
}


def mdd_extract(text: str, model: str) -> Dict[str, Any]:
    client = P.get_client()

    developer_prompt = """
You are extracting machine-readable phenotype statements from DSM-5-TR
Major Depressive Disorder text.

Goal:
Convert the input into a compact list of phenotype statements that can later
be matched to HPO. Each statement should be a granular feature, not a
diagnostic label.

Rules:
1. Extract phenotype FEATURES, not diagnoses or DSM labels.
2. Keep short normalized phrases like:
   - depressed mood
   - anhedonia
   - insomnia
   - hypersomnia
   - psychomotor retardation
   - psychomotor agitation
   - significant weight loss
   - significant weight gain
   - fatigue
   - worthlessness
   - excessive guilt
   - diminished concentration
   - suicidal ideation
3. Three MDD Criterion A symptoms are BIDIRECTIONAL: weight change (loss OR
   gain), sleep disturbance (insomnia OR hypersomnia), psychomotor change
   (agitation OR retardation). When the criterion text gives both directions in
   one criterion, emit TWO separate items (one per direction) and set
   polarity = "bidirectional" on each. Do NOT mark either as anti-MDD.
4. The 9 valid categories correspond to DSM-5-TR Criterion A.1-A.9:
   depressed_mood, anhedonia, weight_appetite_change, sleep_disturbance,
   psychomotor_change, fatigue, worthlessness_guilt,
   concentration_indecisiveness, suicidality. Use "other" only for items
   that genuinely fall outside Criterion A.
5. Do NOT output prevalence statements, risk factors, treatment notes,
   coding instructions, or comparisons to other depressive disorders.
6. Do NOT force one input sentence into one output item. Split into granular
   features.
7. Keep negated/context-only material as polarity = "negated" or
   centrality = "context_only".
8. Be conservative. If a phrase is not really a phenotype, exclude it.
9. DO NOT extract from "Note:" blocks UNLESS the Note directly qualifies a
   specific Criterion item (e.g., the A.1 note that in children and adolescents the mood can be
   irritable instead qualifies Criterion A.1 directly and should
   produce an item). Differential-diagnosis Notes (e.g., the bereavement
   Note that appears after Criterion C) describe context for clinical
   judgment, NOT new MDD phenotypes — if you extract anything from those,
   tag centrality = "context_only".
10. TEMPORALITY tagging:
    - "irritable mood" from the A.1 children/adolescents Note ->
      temporality = "developmental" (it is a developmental-population-
      specific manifestation, not adult depressed mood).
    - Symptoms described as concurrent during the depressive episode ->
      "current".
    - History-only or past-episode references -> "history".
    - When unspecified -> "unspecified".
""".strip()

    user_prompt = f"""
Extract phenotype statements from the following MDD core text.

TEXT:
{text}
""".strip()

    response = client.chat.completions.create(
        model=model,
        temperature=0,
        seed=1,
        messages=[
            {"role": "developer", "content": developer_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_schema",
                         "json_schema": MDD_EXTRACTION_SCHEMA},
    )

    print("OPENAI RESPONSE ID:", response.id)
    print("OPENAI MODEL:", response.model)
    print("OPENAI USAGE:", response.usage)
    print("SYSTEM FINGERPRINT:", getattr(response, "system_fingerprint", None))

    return json.loads(response.choices[0].message.content)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mdd_text",
        type=str,
        default="DSM5_MDD_preprocessed/MDD_core_phenotype_only.txt",
    )
    parser.add_argument("--hpo_json", type=str, required=True)
    parser.add_argument("--outdir", type=str, default="pilot_hpo_run_mdd_v1")
    parser.add_argument("--embedding_cache", type=str, default=None)
    parser.add_argument("--embedding_batch_size", type=int, default=128)
    parser.add_argument("--fuzzy_top_k", type=int, default=8)
    parser.add_argument("--semantic_top_k", type=int, default=12)
    parser.add_argument("--merged_top_k", type=int, default=12)
    parser.add_argument("--llm_seed", type=int, default=1)
    parser.add_argument(
        "--allow_proxy_in_final", action="store_true",
        help="Include proxy_related matches in final resolved HPO term set.",
    )
    parser.add_argument(
        "--force_rebuild_embeddings", action="store_true",
        help="Recompute the HPO embedding cache even if a matching cache exists.",
    )
    args = parser.parse_args()

    P.EXTRACTION_SCHEMA = MDD_EXTRACTION_SCHEMA
    P.call_openai_extract = mdd_extract

    import sys
    new_argv = [
        "pilot_asd_to_hpo_hybrid_rev.py",
        "--asd_text", args.mdd_text,
        "--hpo_json", args.hpo_json,
        "--outdir", args.outdir,
        "--embedding_batch_size", str(args.embedding_batch_size),
        "--fuzzy_top_k", str(args.fuzzy_top_k),
        "--semantic_top_k", str(args.semantic_top_k),
        "--merged_top_k", str(args.merged_top_k),
        "--llm_seed", str(args.llm_seed),
    ]
    if args.embedding_cache:
        new_argv += ["--embedding_cache", args.embedding_cache]
    if args.allow_proxy_in_final:
        new_argv.append("--allow_proxy_in_final")
    if args.force_rebuild_embeddings:
        new_argv.append("--force_rebuild_embeddings")
    sys.argv = new_argv

    print(f"=== MDD Stage 1 run ===")
    print(f"  input:  {args.mdd_text}")
    print(f"  hpo:    {args.hpo_json}")
    print(f"  outdir: {args.outdir}")
    print(f"  domains: {len(MDD_DOMAINS) - 1} Criterion A symptoms + 'other'")
    print(f"  bidirectional: {BIDIRECTIONAL_DOMAINS}")
    print()

    P.main()

    try:
        import pandas as pd
        extracted_path = Path(args.outdir) / "02_extracted_phenotypes.csv"
        if extracted_path.exists():
            df = pd.read_csv(extracted_path)
            other = df[df["category"] == "other"]
            print()
            print(f"=== 'other'-category audit ({len(other)} item(s)) ===")
            if len(other) == 0:
                print("  No items tagged 'other'. Clean run.")
            else:
                print("  Review each for re-categorization into one of the 9 Criterion A domains")
                print("  or discard as extraction noise:")
                for _, r in other.iterrows():
                    src = str(r.get("source_fragment", ""))[:80]
                    norm = str(r.get("normalized_phenotype", ""))[:60]
                    pol = r.get("polarity", "?")
                    cent = r.get("centrality", "?")
                    print(f"    [{cent}/{pol}] {norm!r}")
                    print(f"      <- {src!r}")
    except Exception as exc:
        print(f"  (Post-run 'other'-audit skipped: {exc})")


if __name__ == "__main__":
    main()
