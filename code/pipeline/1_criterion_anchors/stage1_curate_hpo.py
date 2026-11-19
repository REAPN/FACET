#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd


from safe_write_util import safe_write_csv
import pilot_asd_to_hpo_hybrid_rev as P


def load_config(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_extraction_schema(stage1_cfg: Dict[str, Any]) -> Dict[str, Any]:
    ext = stage1_cfg["extraction_schema"]
    return {
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
                                "enum": ext["categories_enum"],
                            },
                            "centrality": {
                                "type": "string",
                                "enum": ext["centrality_enum"],
                            },
                            "polarity": {
                                "type": "string",
                                "enum": ext["polarity_enum"],
                            },
                            "temporality": {
                                "type": "string",
                                "enum": ext["temporality_enum"],
                            },
                            "notes": {"type": "string"},
                        },
                        "required": [
                            "source_fragment",
                            "normalized_phenotype",
                            "category",
                            "centrality",
                            "polarity",
                            "temporality",
                            "notes",
                        ],
                    },
                },
            },
            "required": ["disorder_name", "items"],
        },
    }


BASE_EXTRACTION_PROMPT = """
You are extracting machine-readable phenotype statements from DSM-style text
about {disorder_name}.

Goal:
Convert the input into a compact list of phenotype statements that can later
be matched to HPO. Each statement should be a granular feature, not a
diagnostic label.

Rules:
1. Extract phenotype FEATURES, not diagnoses or DSM labels.
2. Keep short normalized phrases (e.g., "anhedonia", "insomnia",
   "reduced eye contact", "sensory hyperreactivity").
3. Do NOT output disorder names, prevalence statements, risk factors,
   treatments, coding instructions, or comparisons to other disorders.
4. Do NOT force one input sentence into one output item. Split into
   granular features.
5. Keep negated/context-only material as polarity = "negated" or
   centrality = "context_only".
6. If a statement is about developmental timing, keep it as a phenotype-
   like item under whatever developmental_course-like category is in the
   schema.
7. Prefer descriptive, ontology-friendly phrasing over DSM prose.
8. Be conservative. If a phrase is not really a phenotype, exclude it.

{addendum}
""".strip()


def build_extraction_prompts(
    disorder_name: str, addendum: str | None, text: str
) -> Tuple[str, str]:
    dev = BASE_EXTRACTION_PROMPT.format(
        disorder_name=disorder_name,
        addendum=(addendum or "").strip(),
    ).strip()
    user = f"""
Extract phenotype statements from the following {disorder_name} core text.

TEXT:
{text}
""".strip()
    return dev, user


def call_extract_with_config(
    text: str,
    model: str,
    schema: Dict[str, Any],
    developer_prompt: str,
    user_prompt: str,
) -> Dict[str, Any]:
    client = P.get_client()
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        seed=1,
        messages=[
            {"role": "developer", "content": developer_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_schema", "json_schema": schema},
    )
    print("OPENAI RESPONSE ID:", response.id)
    print("OPENAI MODEL:", response.model)
    print("OPENAI USAGE:", response.usage)
    print("SYSTEM FINGERPRINT:", getattr(response, "system_fingerprint", None))
    return json.loads(response.choices[0].message.content)


def load_cached_raw_extract(baseline_dir: Path) -> Dict[str, Any]:
    p = baseline_dir / "01_raw_llm_output.json"
    if not p.exists():
        raise FileNotFoundError(
            f"--reuse_llm_responses_from given but {p} not found"
        )
    return json.loads(p.read_text(encoding="utf-8"))


def load_cached_resolutions(baseline_dir: Path) -> pd.DataFrame:
    p = baseline_dir / "06_llm_hpo_resolutions.jsonl"
    if not p.exists():
        raise FileNotFoundError(
            f"--reuse_llm_responses_from given but {p} not found"
        )
    rows: List[Dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return pd.DataFrame(rows)


def replay_retrieval_for_cache_reuse(
    extracted: pd.DataFrame,
    alias_df: pd.DataFrame,
    embedding_index: Dict[str, Any],
    embedding_model: str,
    fuzzy_top_k: int,
    semantic_top_k: int,
    merged_top_k: int,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    fuzzy_rows: List[Dict[str, Any]] = []
    semantic_rows: List[Dict[str, Any]] = []
    merged_rows: List[Dict[str, Any]] = []
    items = extracted.to_dict(orient="records")
    for i, item in enumerate(items, start=1):
        phrase = P.clean_phrase(item.get("normalized_phenotype", ""))
        if not phrase:
            continue
        fuzzy_df = P.fuzzy_candidates(phrase, alias_df, top_k=fuzzy_top_k)
        semantic_df = P.semantic_candidates(
            phrase, embedding_index=embedding_index,
            embedding_model=embedding_model, top_k=semantic_top_k,
        )
        merged_df = P.merge_candidate_lists(
            fuzzy_df, semantic_df, merged_top_k=merged_top_k,
        )
        for rank, (_, row) in enumerate(fuzzy_df.iterrows(), start=1):
            fuzzy_rows.append({
                "phenotype_index": i,
                "normalized_phenotype": phrase,
                "source_fragment": item.get("source_fragment", ""),
                "category": item.get("category", ""),
                "centrality": item.get("centrality", ""),
                "polarity": item.get("polarity", ""),
                "temporality": item.get("temporality", ""),
                "candidate_rank": rank,
                "candidate_hpo_id": row["hpo_id"],
                "candidate_label": row["label"],
                "matched_alias": row["alias"],
                "matched_alias_type": row["alias_type"],
                "fuzzy_score": row["fuzzy_score"],
                "definition": row["definition"],
                "synonyms": row["synonyms"],
            })
        for _, row in semantic_df.iterrows():
            semantic_rows.append({
                "phenotype_index": i,
                "normalized_phenotype": phrase,
                "source_fragment": item.get("source_fragment", ""),
                "category": item.get("category", ""),
                "centrality": item.get("centrality", ""),
                "polarity": item.get("polarity", ""),
                "temporality": item.get("temporality", ""),
                "candidate_rank": int(row["semantic_rank"]),
                "candidate_hpo_id": row["hpo_id"],
                "candidate_label": row["label"],
                "semantic_score": row["semantic_score"],
                "definition": row["definition"],
                "synonyms": row["synonyms"],
            })
        merged_df = merged_df.copy()
        merged_df["phenotype_index"] = i
        merged_df["normalized_phenotype"] = phrase
        merged_df["source_fragment"] = item.get("source_fragment", "")
        merged_df["category"] = item.get("category", "")
        merged_df["centrality"] = item.get("centrality", "")
        merged_df["polarity"] = item.get("polarity", "")
        merged_df["temporality"] = item.get("temporality", "")
        merged_rows.extend(merged_df.to_dict(orient="records"))
    return (
        pd.DataFrame(fuzzy_rows),
        pd.DataFrame(semantic_rows),
        pd.DataFrame(merged_rows),
    )


def apply_final_filter(
    resolution_df: pd.DataFrame,
    final_filter_cfg: Dict[str, Any],
    allow_proxy: bool = False,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    allowed_relations = set(final_filter_cfg["allowed_relations"])
    if allow_proxy:
        allowed_relations.add("proxy_related")

    allowed_centrality = list(final_filter_cfg["allowed_centrality"])
    allowed_polarity = list(final_filter_cfg["allowed_polarity"])

    resolved = resolution_df[
        (resolution_df["decision_status"] == "resolved")
        & (resolution_df["selected_hpo_id"] != "NONE")
        & (resolution_df["polarity"].isin(allowed_polarity))
        & (resolution_df["centrality"].isin(allowed_centrality))
        & (resolution_df["mapping_relation"].isin(allowed_relations))
    ].copy()

    resolved = resolved.sort_values(
        ["manual_review", "confidence"],
        ascending=[True, False],
    ).drop_duplicates(subset=["selected_hpo_id"], keep="first")

    resolved = resolved.rename(columns={
        "selected_hpo_id": "hpo_id",
        "selected_label": "hpo_label",
    })

    unresolved = resolution_df[
        (resolution_df["decision_status"] != "resolved")
        | (~resolution_df["mapping_relation"].isin(allowed_relations))
        | (resolution_df["selected_hpo_id"] == "NONE")
    ].copy()

    return resolved, unresolved


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=str, required=True,
                    help="Path to disorder_config.json")
    ap.add_argument("--hpo_json", type=str, default=None,
                    help="Override hpo_json_input from config")
    ap.add_argument("--core_text", type=str, default=None,
                    help="Override core_text_input from config")
    ap.add_argument("--outdir", type=str, default=None,
                    help="Override outdir from config")
    ap.add_argument("--reuse_llm_responses_from", type=str, default=None,
                    help="Load 01_raw_llm_output.json + 06_llm_hpo_resolutions.jsonl "
                         "from this baseline dir instead of calling the LLM.")
    ap.add_argument("--embedding_cache", type=str, default=None,
                    help="Override embedding cache path")
    ap.add_argument("--embedding_batch_size", type=int, default=128)
    ap.add_argument("--fuzzy_top_k", type=int, default=8)
    ap.add_argument("--semantic_top_k", type=int, default=12)
    ap.add_argument("--merged_top_k", type=int, default=12)
    ap.add_argument("--llm_seed", type=int, default=None)
    ap.add_argument("--allow_proxy_in_final", action="store_true")
    ap.add_argument("--force_rebuild_embeddings", action="store_true")
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    disorder_id = cfg["disorder"]["id"]
    disorder_name = cfg["disorder"].get("name", disorder_id)
    s1 = cfg["stage1_hpo_curation"]

    core_text_path = Path(args.core_text or s1["core_text_input"])
    hpo_json_path = Path(args.hpo_json or s1["hpo_json_input"])
    outdir = Path(args.outdir or s1["outdir"])
    outdir.mkdir(parents=True, exist_ok=True)

    chat_model = os.environ.get("OPENAI_MODEL", s1.get("llm_model", "gpt-5.4"))
    embedding_model = os.environ.get(
        "OPENAI_EMBED_MODEL", s1.get("embedding_model", "text-embedding-3-large")
    )
    llm_seed = args.llm_seed if args.llm_seed is not None else s1.get("llm_seed", 1)

    embedding_cache = (
        Path(args.embedding_cache) if args.embedding_cache
        else outdir / "hpo_embedding_cache.pkl"
    )

    print(f"=== stage1_curate_hpo: disorder={disorder_id} ===")
    print(f"  core text:  {core_text_path}")
    print(f"  hpo json:   {hpo_json_path}")
    print(f"  outdir:     {outdir.resolve()}")
    if args.reuse_llm_responses_from:
        print(f"  LLM reuse:  {args.reuse_llm_responses_from}")
    print()

    if args.reuse_llm_responses_from:
        baseline_dir = Path(args.reuse_llm_responses_from)
        raw = load_cached_raw_extract(baseline_dir)
    else:
        schema = build_extraction_schema(s1)
        text = P.read_text(core_text_path)
        dev_prompt, user_prompt = build_extraction_prompts(
            disorder_name=disorder_name,
            addendum=s1.get("extraction_prompt_addendum"),
            text=text,
        )
        raw = call_extract_with_config(
            text=text, model=chat_model, schema=schema,
            developer_prompt=dev_prompt, user_prompt=user_prompt,
        )

    (outdir / "01_raw_llm_output.json").write_text(
        json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8",
    )

    extracted = pd.DataFrame(raw["items"])
    if extracted.empty:
        raise RuntimeError("LLM returned no phenotype items.")
    extracted["normalized_phenotype"] = (
        extracted["normalized_phenotype"].map(P.clean_phrase).str.strip().str.lower()
    )
    extracted = extracted[
        extracted["normalized_phenotype"].notna()
        & (extracted["normalized_phenotype"] != "")
    ].copy()
    extracted = extracted.drop_duplicates(
        subset=["normalized_phenotype", "polarity", "centrality"]
    ).reset_index(drop=True)
    safe_write_csv(extracted, outdir / "02_extracted_phenotypes.csv", index=False)

    print(
        extracted[[
            "normalized_phenotype", "category", "centrality", "polarity", "temporality",
        ]].head(40).to_string(index=False)
    )

    hpo_df = P.load_hpo_json(hpo_json_path)
    alias_df = P.build_alias_table(hpo_df)
    embedding_index = P.build_or_load_embedding_index(
        hpo_df=hpo_df,
        cache_path=embedding_cache,
        embedding_model=embedding_model,
        batch_size=args.embedding_batch_size,
        force_rebuild=args.force_rebuild_embeddings,
    )

    if args.reuse_llm_responses_from:
        import shutil
        baseline_dir = Path(args.reuse_llm_responses_from)
        for fname in [
            "03_fuzzy_hpo_candidates.csv",
            "04_semantic_hpo_candidates.csv",
            "05_merged_hpo_candidates.csv",
        ]:
            src = baseline_dir / fname
            if src.exists():
                shutil.copy2(src, outdir / fname)
        resolution_df = load_cached_resolutions(baseline_dir)
    else:
        fuzzy_df, semantic_df, merged_df, resolution_df = (
            P.resolve_with_hybrid_retrieval(
                extracted_items=extracted.to_dict(orient="records"),
                alias_df=alias_df,
                embedding_index=embedding_index,
                chat_model=chat_model,
                embedding_model=embedding_model,
                fuzzy_top_k=args.fuzzy_top_k,
                semantic_top_k=args.semantic_top_k,
                merged_top_k=args.merged_top_k,
                llm_seed=llm_seed,
            )
        )
        safe_write_csv(fuzzy_df, outdir / "03_fuzzy_hpo_candidates.csv", index=False)
        safe_write_csv(semantic_df, outdir / "04_semantic_hpo_candidates.csv", index=False)
        safe_write_csv(merged_df, outdir / "05_merged_hpo_candidates.csv", index=False)

    with (outdir / "06_llm_hpo_resolutions.jsonl").open("w", encoding="utf-8") as f:
        for row in resolution_df.to_dict(orient="records"):
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    safe_write_csv(resolution_df, outdir / "06b_llm_hpo_resolutions.csv", index=False)

    resolved, unresolved = apply_final_filter(
        resolution_df=resolution_df,
        final_filter_cfg=s1["final_filter"],
        allow_proxy=args.allow_proxy_in_final,
    )

    final_cols = [
        "hpo_id", "hpo_label", "normalized_phenotype", "category",
        "centrality", "temporality", "mapping_relation",
        "confidence", "manual_review", "rationale",
    ]
    safe_write_csv(resolved[final_cols], outdir / "07_final_resolved_hpo_terms.tsv", sep="\t", index=False)
    safe_write_csv(unresolved, outdir / "08_unresolved_phenotypes.csv", index=False)

    try:
        other = extracted[extracted["category"] == "other"]
        print()
        print(f"=== 'other'-category audit ({len(other)} item(s)) ===")
        if len(other) == 0:
            print("  No items tagged 'other'. Clean run.")
        else:
            print("  Review each for re-categorization or discard as noise:")
            for _, r in other.iterrows():
                src = str(r.get("source_fragment", ""))[:80]
                norm = str(r.get("normalized_phenotype", ""))[:60]
                pol = r.get("polarity", "?")
                cent = r.get("centrality", "?")
                print(f"    [{cent}/{pol}] {norm!r}")
                print(f"      <- {src!r}")
    except Exception as exc:
        print(f"  (Post-run audit skipped: {exc})")

    print()
    print(f"Done. Outputs written to: {outdir.resolve()}")
    print(f"  Extracted items: {len(extracted)}")
    print(f"  Resolved HPO terms: {resolved.shape[0]}")
    print(f"  Unresolved items: {unresolved.shape[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
