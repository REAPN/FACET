#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

import build_candidate_feature_table as B


def load_config(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def apply_strict_domains(cfg: Dict[str, Any]) -> None:
    strict_raw = cfg["domains"]["strict"]
    strict = [d["name"] if isinstance(d, dict) else d for d in strict_raw]
    B.STRICT_DOMAINS = strict


def apply_adjacency(cfg: Dict[str, Any]) -> None:
    adj = cfg.get("adjacency", {})
    B.ADJACENCY = {k: set(v) for k, v in adj.items()}


def build_regex_fallback(domain_regex_map: Dict[str, str]) -> Dict[str, re.Pattern]:
    return {k: re.compile(v, re.IGNORECASE) for k, v in domain_regex_map.items()}


def install_mdd_style_hpo_domain_inference(
    strict_domains: List[str],
    fallback_regex: Dict[str, re.Pattern],
) -> None:
    domain_set = set(strict_domains)

    def _infer(category: str, label: str, phenotype_text: str) -> str:
        cat = B.clean_text(category).lower()
        if cat in domain_set:
            return cat
        text = f"{B.clean_text(label)} {B.clean_text(phenotype_text)}".lower()
        for dom in strict_domains:
            pat = fallback_regex.get(dom)
            if pat is not None and pat.search(text):
                return dom
        return "other"

    B.infer_hpo_domain = _infer


def install_single_bucket_mouse_routing(bucket_label: str) -> None:

    def _norm_mouse(primary: str, secondary: str, mp_text: str) -> str:
        return bucket_label

    def _compat(h_domain: str, use_spillover: bool) -> Set[str]:
        return {h_domain, bucket_label}

    B.normalize_mouse_domain = _norm_mouse
    B.compatible_domains = _compat


def configure_module_from_config(cfg: Dict[str, Any]) -> None:
    apply_strict_domains(cfg)
    apply_adjacency(cfg)

    s2 = cfg["stage2_candidate_features"]
    routing = s2.get("mouse_domain_routing", {}) or {}

    if routing.get("mode") == "single_bucket":
        bucket = routing.get("single_bucket_label", "pool")
        install_single_bucket_mouse_routing(bucket)

    domain_regex_fallback = s2.get("hpo_domain_regex_fallback")
    if domain_regex_fallback:
        fallback = build_regex_fallback(domain_regex_fallback)
        strict_raw = cfg["domains"]["strict"]
        strict = [d["name"] if isinstance(d, dict) else d for d in strict_raw]
        install_mdd_style_hpo_domain_inference(strict, fallback)


def build_passthrough_argv(cfg: Dict[str, Any], overrides: Dict[str, Any]) -> List[str]:
    s2 = cfg["stage2_candidate_features"]
    outdir = overrides.get("outdir") or s2["outdir"]
    argv = [
        "build_candidate_feature_table.py",
        "--hpo_tsv", overrides.get("hpo_tsv") or s2["hpo_targets_input"],
        "--mouse_mp_csv", overrides.get("mouse_mp_csv") or s2["mouse_mp_csv"],
        "--taxonomy_tsv", overrides.get("taxonomy_tsv") or s2["taxonomy_tsv"],
        "--outdir", outdir,
        "--mode", s2.get("mode", "union"),
        "--top_k_embedding", str(s2.get("top_k_embedding", 20)),
        "--top_k_lexical", str(s2.get("top_k_lexical", 20)),
    ]
    pairwise = overrides.get("pairwise_similarity_tsv") or s2.get("pairwise_similarity_tsv")
    if pairwise:
        argv += ["--pairwise_similarity_tsv", pairwise]
    if s2.get("include_supporting_hpo", False):
        argv.append("--include_supporting_hpo")
    if s2.get("include_tier2_mouse", False):
        argv.append("--include_tier2_mouse")
    if s2.get("inject_descendants", False):
        argv.append("--inject_descendants")
        if s2.get("mp_obo"):
            argv += ["--mp_obo", s2["mp_obo"]]
        if s2.get("carriage_csv"):
            argv += ["--carriage_csv", s2["carriage_csv"]]
    if s2.get("use_embedding_retrieval", False):
        argv.append("--use_embedding_retrieval")
    if s2.get("use_lexical_retrieval", False):
        argv.append("--use_lexical_retrieval")
    if s2.get("use_spillover_default", False) and not overrides.get("disable_spillover"):
        argv.append("--use_spillover")
    embed_model = overrides.get("embedding_model")
    if embed_model:
        argv += ["--embedding_model", embed_model]
    return argv


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=str, required=True,
                    help="Path to disorder_config.json")
    ap.add_argument("--outdir", type=str, default=None,
                    help="Override stage2_candidate_features.outdir from config")
    ap.add_argument("--hpo_tsv", type=str, default=None,
                    help="Override hpo_targets_input from config")
    ap.add_argument("--mouse_mp_csv", type=str, default=None)
    ap.add_argument("--taxonomy_tsv", type=str, default=None)
    ap.add_argument("--pairwise_similarity_tsv", type=str, default=None)
    ap.add_argument("--embedding_model", type=str, default=None)
    ap.add_argument("--disable_spillover", action="store_true",
                    help="Force spillover off regardless of config default")
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    disorder_id = cfg["disorder"]["id"]

    configure_module_from_config(cfg)

    overrides = {
        "outdir": args.outdir,
        "hpo_tsv": args.hpo_tsv,
        "mouse_mp_csv": args.mouse_mp_csv,
        "taxonomy_tsv": args.taxonomy_tsv,
        "pairwise_similarity_tsv": args.pairwise_similarity_tsv,
        "embedding_model": args.embedding_model,
        "disable_spillover": args.disable_spillover,
    }
    new_argv = build_passthrough_argv(cfg, overrides)
    print(f"=== stage2a_candidate_features: disorder={disorder_id} ===")
    print(f"  passthrough argv: {' '.join(new_argv)}")
    sys.argv = new_argv
    B.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
