#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import sys
from typing import Set

import build_candidate_feature_table as B


MDD_STRICT_DOMAINS = [
    "depressed_mood",
    "anhedonia",
    "weight_appetite_change",
    "sleep_disturbance",
    "psychomotor_change",
    "fatigue",
    "worthlessness_guilt",
    "concentration_indecisiveness",
    "suicidality",
]

MDD_ADJACENCY = {
    "depressed_mood": {"anhedonia", "worthlessness_guilt", "suicidality"},
    "anhedonia": {"depressed_mood", "fatigue", "concentration_indecisiveness"},
    "weight_appetite_change": {"fatigue", "sleep_disturbance", "psychomotor_change"},
    "sleep_disturbance": {"fatigue", "weight_appetite_change", "psychomotor_change"},
    "psychomotor_change": {"fatigue", "weight_appetite_change", "sleep_disturbance"},
    "fatigue": {"anhedonia", "weight_appetite_change", "sleep_disturbance",
                "psychomotor_change", "concentration_indecisiveness"},
    "worthlessness_guilt": {"depressed_mood", "suicidality"},
    "concentration_indecisiveness": {"anhedonia", "fatigue"},
    "suicidality": {"depressed_mood", "worthlessness_guilt"},
}

MDD_PATS = {
    "suicidality": re.compile(r"suicid|death.*ideation|self-harm|self-injur"),
    "anhedonia": re.compile(r"anhedonia|apathy|libido|loss of pleasure|loss of interest|hedonic"),
    "sleep_disturbance": re.compile(r"sleep|insomnia|hypersomnia|wake|awak|nocturnal|REM|circadian"),
    "weight_appetite_change": re.compile(r"weight|appetite|polyphagia|anorexia|hyperphagia|food crav|failure to thrive"),
    "psychomotor_change": re.compile(r"psychomot|agitation|restless|mutism|stereotypy|hand wringing|slow.*thought|locomotor|catatoni"),
    "fatigue": re.compile(r"fatigue|tired|asthenia|lethargy|exhaust|low energy"),
    "worthlessness_guilt": re.compile(r"worthless|guilt|self-esteem|self-deprecat|inadequacy|self-blame"),
    "concentration_indecisiveness": re.compile(r"concentrat|attention|indecis|distractib|memory|cognit|executive"),
    "depressed_mood": re.compile(r"depress|sad|tearful|hopeless|irritable|dysphori|melanchol"),
}


def mdd_infer_hpo_domain(category: str, label: str, phenotype_text: str) -> str:
    cat = B.clean_text(category).lower()
    if cat in MDD_STRICT_DOMAINS:
        return cat
    text = f"{B.clean_text(label)} {B.clean_text(phenotype_text)}".lower()
    for dom in ["suicidality", "anhedonia", "sleep_disturbance",
                "weight_appetite_change", "psychomotor_change", "fatigue",
                "worthlessness_guilt", "concentration_indecisiveness",
                "depressed_mood"]:
        if MDD_PATS[dom].search(text):
            return dom
    return "other"


def mdd_compatible_domains(h_domain: str, use_spillover: bool) -> Set[str]:
    return {h_domain, "mdd_pool"}


def mdd_normalize_mouse_domain(primary: str, secondary: str, mp_text: str) -> str:
    return "mdd_pool"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hpo_tsv", type=str,
                        default="pilot_hpo_run_mdd_v1/07_final_resolved_hpo_terms.tsv")
    parser.add_argument("--mouse_mp_csv", type=str,
                        default="broad_benchmark_setup/08_all_genotype_phenotypes_long_blinded.csv")
    parser.add_argument("--taxonomy_tsv", type=str,
                        default="mp_term_taxonomy_broad_v3/03_mp_term_taxonomy.tsv")
    parser.add_argument("--pairwise_similarity_tsv", type=str,
                        default="phenio-monarch-hp-mp.0.4.semsimian.tsv")
    parser.add_argument("--outdir", type=str, default="mdd_candidate_features_v1")
    parser.add_argument("--include_supporting_hpo", action="store_true", default=True)
    parser.add_argument("--include_tier2_mouse", action="store_true", default=True)
    parser.add_argument("--mode", choices=["exhaustive", "union"], default="union")
    parser.add_argument("--use_embedding_retrieval", action="store_true", default=True)
    parser.add_argument("--use_lexical_retrieval", action="store_true", default=True)
    parser.add_argument(
        "--use_spillover", action="store_true", default=False,
        help="Default False for MDD v1: see mdd_compatible_domains docstring.",
    )
    parser.add_argument("--top_k_embedding", type=int, default=20)
    parser.add_argument("--top_k_lexical", type=int, default=20)
    parser.add_argument("--embedding_model", type=str, default=None)
    args = parser.parse_args()

    B.STRICT_DOMAINS = MDD_STRICT_DOMAINS
    B.ADJACENCY = MDD_ADJACENCY
    B.infer_hpo_domain = mdd_infer_hpo_domain
    B.compatible_domains = mdd_compatible_domains
    B.normalize_mouse_domain = mdd_normalize_mouse_domain

    print("=== MDD Stage 2a: candidate-pair retrieval + transparent features ===")
    print(f"  hpo targets: {args.hpo_tsv}")
    print(f"  mouse mp:    {args.mouse_mp_csv}")
    print(f"  taxonomy:    {args.taxonomy_tsv}")
    print(f"  outdir:      {args.outdir}")
    print(f"  retrieval:   embedding={args.use_embedding_retrieval}  "
          f"lexical={args.use_lexical_retrieval}  spillover={args.use_spillover}")
    print(f"  mode:        {args.mode}")
    print(f"  domains:     {len(MDD_STRICT_DOMAINS)} MDD Criterion A symptoms")
    print(f"  pooling:     all MPs routed through 'mdd_pool' (v1 workaround)")
    print()

    new_argv = [
        "build_candidate_feature_table.py",
        "--hpo_tsv", args.hpo_tsv,
        "--mouse_mp_csv", args.mouse_mp_csv,
        "--taxonomy_tsv", args.taxonomy_tsv,
        "--outdir", args.outdir,
        "--mode", args.mode,
        "--top_k_embedding", str(args.top_k_embedding),
        "--top_k_lexical", str(args.top_k_lexical),
    ]
    if args.pairwise_similarity_tsv:
        new_argv += ["--pairwise_similarity_tsv", args.pairwise_similarity_tsv]
    if args.include_supporting_hpo:
        new_argv.append("--include_supporting_hpo")
    if args.include_tier2_mouse:
        new_argv.append("--include_tier2_mouse")
    if args.use_embedding_retrieval:
        new_argv.append("--use_embedding_retrieval")
    if args.use_lexical_retrieval:
        new_argv.append("--use_lexical_retrieval")
    if args.use_spillover:
        new_argv.append("--use_spillover")
    if args.embedding_model:
        new_argv += ["--embedding_model", args.embedding_model]
    sys.argv = new_argv

    B.main()


if __name__ == "__main__":
    main()
