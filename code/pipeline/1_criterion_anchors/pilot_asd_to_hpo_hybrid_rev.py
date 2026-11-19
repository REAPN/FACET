#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd
from openai import OpenAI
from rapidfuzz import fuzz


EXTRACTION_SCHEMA = {
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
                            "enum": [
                                "social_communication",
                                "restricted_repetitive_behavior",
                                "sensory",
                                "language",
                                "developmental_course",
                                "motor",
                                "other",
                            ],
                        },
                        "centrality": {
                            "type": "string",
                            "enum": ["core", "supporting", "context_only"],
                        },
                        "polarity": {
                            "type": "string",
                            "enum": ["present", "absent", "negated", "uncertain"],
                        },
                        "temporality": {
                            "type": "string",
                            "enum": ["current", "history", "developmental", "unspecified"],
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


def make_resolution_schema(valid_hpo_ids: List[str]) -> Dict[str, Any]:
    valid_choices = list(dict.fromkeys(valid_hpo_ids + ["NONE"]))
    return {
        "name": "hpo_resolution",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "decision_status": {
                    "type": "string",
                    "enum": ["resolved", "unresolved", "skip_not_phenotype"],
                },
                "selected_hpo_id": {
                    "type": "string",
                    "enum": valid_choices,
                },
                "mapping_relation": {
                    "type": "string",
                    "enum": [
                        "exact",
                        "broader_than_source",
                        "narrower_than_source",
                        "proxy_related",
                        "no_match",
                    ],
                },
                "confidence": {"type": "number"},
                "manual_review": {"type": "boolean"},
                "rationale": {"type": "string"},
            },
            "required": [
                "decision_status",
                "selected_hpo_id",
                "mapping_relation",
                "confidence",
                "manual_review",
                "rationale",
            ],
        },
    }


STOP = {
    "abnormal",
    "impaired",
    "reduced",
    "difficulty",
    "deficit",
    "deficits",
    "current",
    "history",
    "used",
    "ability",
    "abilities",
    "pattern",
    "patterns",
}


def get_client() -> OpenAI:
    return OpenAI()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def clean_phrase(x: str) -> str:
    x = (x or "").strip()
    x = re.sub(r"\s+", " ", x)
    return x


def normalize_hpo_id(term_id: str) -> str | None:
    if not term_id:
        return None
    if term_id.startswith("HP:"):
        return term_id
    if "HP_" in term_id:
        tail = term_id.split("HP_")[-1]
        if tail.isdigit():
            return f"HP:{tail}"
    if term_id.startswith("obo:HP_"):
        tail = term_id.split("HP_")[-1]
        if tail.isdigit():
            return f"HP:{tail}"
    return None


def content_tokens(s: str) -> set[str]:
    toks = re.findall(r"[a-z]+", (s or "").lower())
    return {t for t in toks if len(t) > 2 and t not in STOP}


def load_hpo_json(path: Path) -> pd.DataFrame:
    data = json.loads(path.read_text(encoding="utf-8"))

    if "graphs" in data and data["graphs"]:
        nodes = data["graphs"][0].get("nodes", [])
    elif "nodes" in data:
        nodes = data["nodes"]
    else:
        raise ValueError("Could not find nodes in HPO JSON.")

    rows = []
    for node in nodes:
        raw_id = node.get("id", "")
        term_id = normalize_hpo_id(raw_id)
        if term_id is None:
            continue

        label = node.get("lbl", "") or node.get("label", "") or ""
        meta = node.get("meta", {}) or {}

        deprecated = meta.get("deprecated", False) or node.get("deprecated", False)
        if deprecated:
            continue

        definition = ""
        if isinstance(meta.get("definition"), dict):
            definition = meta["definition"].get("val", "") or ""
        elif isinstance(meta.get("definition"), str):
            definition = meta.get("definition", "") or ""

        synonyms = []
        for syn in meta.get("synonyms", []) or []:
            if isinstance(syn, dict):
                val = syn.get("val", "")
                if val:
                    synonyms.append(val)
            elif isinstance(syn, str):
                synonyms.append(syn)

        rows.append(
            {
                "hpo_id": term_id,
                "label": label,
                "definition": definition,
                "synonyms": synonyms,
            }
        )

    df = pd.DataFrame(rows).drop_duplicates(subset=["hpo_id"]).reset_index(drop=True)
    if df.empty:
        raise ValueError("No HPO terms were loaded from the JSON.")

    df["synonyms"] = df["synonyms"].apply(lambda x: x if isinstance(x, list) else [])
    df["synonyms_text"] = df["synonyms"].apply(lambda x: " | ".join(x))
    df["index_text"] = df.apply(format_hpo_index_text, axis=1)
    return df


def format_hpo_index_text(row: pd.Series) -> str:
    label = clean_phrase(str(row.get("label", "")))
    synonyms = row.get("synonyms", []) or []
    definition = clean_phrase(str(row.get("definition", "")))

    parts = [f"HPO label: {label}"]
    if synonyms:
        parts.append("Synonyms: " + "; ".join(clean_phrase(s) for s in synonyms if clean_phrase(s)))
    if definition:
        parts.append(f"Definition: {definition}")
    return "\n".join(parts)


def build_alias_table(hpo_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in hpo_df.iterrows():
        synonyms = r["synonyms"] if isinstance(r["synonyms"], list) else []
        rows.append(
            {
                "hpo_id": r["hpo_id"],
                "label": r["label"],
                "alias": r["label"],
                "alias_type": "label",
                "definition": r["definition"],
                "synonyms": synonyms,
                "synonyms_text": " | ".join(synonyms),
            }
        )
        for s in synonyms:
            rows.append(
                {
                    "hpo_id": r["hpo_id"],
                    "label": r["label"],
                    "alias": s,
                    "alias_type": "synonym",
                    "definition": r["definition"],
                    "synonyms": synonyms,
                    "synonyms_text": " | ".join(synonyms),
                }
            )
    alias_df = pd.DataFrame(rows)
    alias_df = alias_df.drop_duplicates(
        subset=["hpo_id", "label", "alias", "alias_type", "definition", "synonyms_text"]
    ).reset_index(drop=True)
    alias_df["alias_norm"] = alias_df["alias"].fillna("").str.lower().str.strip()
    return alias_df


def fuzzy_candidates(phrase: str, alias_df: pd.DataFrame, top_k: int = 10) -> pd.DataFrame:
    q = phrase.lower().strip()
    qtok = content_tokens(q)

    scores = []
    for _, row in alias_df.iterrows():
        alias = row["alias_norm"]
        atok = content_tokens(alias)
        overlap = qtok & atok

        if len(qtok) >= 2 and len(overlap) == 0:
            scores.append(0.0)
            continue

        wr = float(fuzz.WRatio(q, alias))
        ts = float(fuzz.token_set_ratio(q, alias))
        score = 0.6 * ts + 0.4 * wr
        scores.append(score)

    tmp = alias_df.copy()
    tmp["fuzzy_score"] = scores
    tmp = tmp.sort_values(["fuzzy_score", "alias_type"], ascending=[False, True])
    tmp = tmp.drop_duplicates(subset=["hpo_id"], keep="first")
    cols = [
        "hpo_id",
        "label",
        "alias",
        "alias_type",
        "definition",
        "synonyms",
        "fuzzy_score",
    ]
    return tmp[cols].head(top_k).reset_index(drop=True)


def corpus_signature(hpo_df: pd.DataFrame) -> str:
    payload = "\n".join(
        f"{r.hpo_id}\t{r.index_text}" for r in hpo_df[["hpo_id", "index_text"]].itertuples(index=False)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def batched(items: List[str], batch_size: int) -> Iterable[List[str]]:
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]


def embed_texts(
    client: OpenAI,
    texts: List[str],
    model: str,
    batch_size: int = 128,
) -> np.ndarray:
    vectors: List[List[float]] = []
    for chunk in batched(texts, batch_size):
        resp = client.embeddings.create(model=model, input=chunk)
        vectors.extend(d.embedding for d in resp.data)
    arr = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms


def build_or_load_embedding_index(
    hpo_df: pd.DataFrame,
    cache_path: Path,
    embedding_model: str,
    batch_size: int = 128,
    force_rebuild: bool = False,
) -> Dict[str, Any]:
    sig = corpus_signature(hpo_df)
    if cache_path.exists() and not force_rebuild:
        with cache_path.open("rb") as f:
            cache = pickle.load(f)
        if (
            cache.get("embedding_model") == embedding_model
            and cache.get("corpus_signature") == sig
            and len(cache.get("hpo_ids", [])) == len(hpo_df)
        ):
            return cache

    client = get_client()
    matrix = embed_texts(
        client=client,
        texts=hpo_df["index_text"].tolist(),
        model=embedding_model,
        batch_size=batch_size,
    )
    cache = {
        "embedding_model": embedding_model,
        "corpus_signature": sig,
        "hpo_ids": hpo_df["hpo_id"].tolist(),
        "labels": hpo_df["label"].tolist(),
        "definitions": hpo_df["definition"].tolist(),
        "synonyms": hpo_df["synonyms"].tolist(),
        "index_text": hpo_df["index_text"].tolist(),
        "matrix": matrix,
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("wb") as f:
        pickle.dump(cache, f)
    return cache


def semantic_candidates(
    phrase: str,
    embedding_index: Dict[str, Any],
    embedding_model: str,
    top_k: int = 10,
) -> pd.DataFrame:
    client = get_client()
    resp = client.embeddings.create(model=embedding_model, input=[phrase])
    q = np.asarray(resp.data[0].embedding, dtype=np.float32)
    qn = np.linalg.norm(q)
    if qn == 0:
        qn = 1.0
    q = q / qn

    matrix = embedding_index["matrix"]
    sims = matrix @ q
    top_idx = np.argsort(-sims)[:top_k]

    rows = []
    for rank, idx in enumerate(top_idx, start=1):
        rows.append(
            {
                "semantic_rank": rank,
                "hpo_id": embedding_index["hpo_ids"][idx],
                "label": embedding_index["labels"][idx],
                "definition": embedding_index["definitions"][idx],
                "synonyms": embedding_index["synonyms"][idx],
                "semantic_score": float(sims[idx]),
            }
        )
    return pd.DataFrame(rows)


def merge_candidate_lists(
    fuzzy_df: pd.DataFrame,
    semantic_df: pd.DataFrame,
    merged_top_k: int = 12,
) -> pd.DataFrame:
    fuzzy_cols = [
        "hpo_id",
        "label",
        "definition",
        "synonyms",
        "alias",
        "alias_type",
        "fuzzy_score",
    ]
    semantic_cols = [
        "hpo_id",
        "label",
        "definition",
        "synonyms",
        "semantic_score",
        "semantic_rank",
    ]

    fuzzy_sub = fuzzy_df[fuzzy_cols].copy() if not fuzzy_df.empty else pd.DataFrame(columns=fuzzy_cols)
    semantic_sub = (
        semantic_df[semantic_cols].copy() if not semantic_df.empty else pd.DataFrame(columns=semantic_cols)
    )

    merged = pd.merge(fuzzy_sub, semantic_sub, on="hpo_id", how="outer", suffixes=("_fuzzy", "_semantic"))

    if merged.empty:
        return merged

    merged["label"] = merged["label_fuzzy"].combine_first(merged["label_semantic"])
    merged["definition"] = merged["definition_fuzzy"].combine_first(merged["definition_semantic"])
    merged["synonyms"] = merged["synonyms_fuzzy"].combine_first(merged["synonyms_semantic"])
    merged = merged.drop(columns=[
        c for c in [
            "label_fuzzy", "label_semantic", "definition_fuzzy", "definition_semantic",
            "synonyms_fuzzy", "synonyms_semantic"
        ] if c in merged.columns
    ])

    merged["from_fuzzy"] = merged["fuzzy_score"].notna()
    merged["from_semantic"] = merged["semantic_score"].notna()
    merged["alias"] = merged["alias"].fillna("")
    merged["alias_type"] = merged["alias_type"].fillna("")
    merged["fuzzy_score"] = merged["fuzzy_score"].fillna(0.0)
    merged["semantic_score"] = merged["semantic_score"].fillna(-1.0)

    merged["semantic_score_norm"] = (merged["semantic_score"] + 1.0) / 2.0
    merged["fuzzy_score_norm"] = merged["fuzzy_score"] / 100.0
    merged["combined_score"] = (
        0.65 * merged["semantic_score_norm"]
        + 0.35 * merged["fuzzy_score_norm"]
        + 0.05 * (merged["from_fuzzy"].astype(float) + merged["from_semantic"].astype(float) - 1.0)
    )

    merged = merged.sort_values(
        ["combined_score", "semantic_score", "fuzzy_score"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    merged["candidate_rank"] = np.arange(1, len(merged) + 1)
    return merged.head(merged_top_k).copy()


def call_openai_extract(text: str, model: str) -> Dict[str, Any]:
    client = get_client()

    developer_prompt = """
You are extracting machine-readable phenotype statements from DSM-style text.

Goal:
Convert the input into a compact list of phenotype statements that can later be matched to HPO.

Rules:
1. Extract phenotype FEATURES, not diagnoses.
2. Keep short normalized phrases like:
   - impaired social-emotional reciprocity
   - reduced eye contact
   - restricted interests
   - insistence on sameness
   - sensory hyperreactivity
3. Do NOT output disorder names, prevalence statements, risk factors, treatments,
   coding instructions, or comparisons to other disorders.
4. Do NOT force one input sentence into one output item. Split into granular features.
5. Keep negated/context-only material as polarity=negated or centrality=context_only.
6. If a statement is about developmental timing (e.g. early developmental onset,
   developmental regression), keep it as a phenotype-like item under developmental_course.
7. Prefer descriptive, ontology-friendly phrasing over DSM prose.
8. Be conservative. If a phrase is not really a phenotype, exclude it.
""".strip()

    user_prompt = f"""
Extract phenotype statements from the following ASD core text.

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
        response_format={"type": "json_schema", "json_schema": EXTRACTION_SCHEMA},
    )

    print("OPENAI RESPONSE ID:", response.id)
    print("OPENAI MODEL:", response.model)
    print("OPENAI USAGE:", response.usage)
    print("SYSTEM FINGERPRINT:", getattr(response, "system_fingerprint", None))

    content = response.choices[0].message.content
    return json.loads(content)


def llm_resolve_to_hpo(
    item: Dict[str, Any],
    merged_candidates: pd.DataFrame,
    model: str,
    seed: int = 1,
) -> Dict[str, Any]:
    if merged_candidates.empty:
        return {
            "decision_status": "unresolved",
            "selected_hpo_id": "NONE",
            "mapping_relation": "no_match",
            "confidence": 0.0,
            "manual_review": False,
            "rationale": "No candidates were retrieved.",
        }

    client = get_client()

    candidate_payload = []
    valid_ids: List[str] = []
    for _, row in merged_candidates.iterrows():
        hpo_id = str(row["hpo_id"])
        valid_ids.append(hpo_id)
        candidate_payload.append(
            {
                "candidate_rank": int(row["candidate_rank"]),
                "hpo_id": hpo_id,
                "label": row["label"],
                "synonyms": row.get("synonyms", []) or [],
                "definition": row.get("definition", "") or "",
                "retrieval": {
                    "from_fuzzy": bool(row.get("from_fuzzy", False)),
                    "from_semantic": bool(row.get("from_semantic", False)),
                    "fuzzy_score": float(row.get("fuzzy_score", 0.0)),
                    "semantic_score": float(row.get("semantic_score", -1.0)),
                    "combined_score": float(row.get("combined_score", 0.0)),
                    "matched_alias": row.get("alias", "") or "",
                    "matched_alias_type": row.get("alias_type", "") or "",
                },
            }
        )

    developer_prompt = """
You adjudicate mappings from DSM-derived phenotype phrases to a bounded shortlist of HPO candidates.

You MUST choose from the provided shortlist only. Do not invent HPO IDs.
It is acceptable to abstain and return selected_hpo_id = NONE.

Decision guidance:
- Prefer semantically faithful phenotype matches over lexical similarity.
- If the candidate matches the source well, use mapping_relation = exact.
- If the candidate is broader than the source phrase, use broader_than_source.
- If the candidate is narrower/more specific than the source phrase, use narrower_than_source.
- If the candidate is only an approximate behavioral or conceptual proxy, use proxy_related.
- If no candidate is good enough, use no_match and selected_hpo_id = NONE.
- Use skip_not_phenotype only when the extracted item should not be mapped as a phenotype at all.
- Be conservative for psychiatry language and avoid forced mappings.

Confidence must be between 0 and 1.
Rationale should be concise and mention why the chosen candidate beats the top alternatives, or why abstention is warranted.
""".strip()

    user_payload = {
        "phenotype_item": {
            "source_fragment": item.get("source_fragment", ""),
            "normalized_phenotype": item.get("normalized_phenotype", ""),
            "category": item.get("category", ""),
            "centrality": item.get("centrality", ""),
            "polarity": item.get("polarity", ""),
            "temporality": item.get("temporality", ""),
            "notes": item.get("notes", ""),
        },
        "candidate_hpo_terms": candidate_payload,
    }

    response = client.chat.completions.create(
        model=model,
        temperature=0,
        seed=seed,
        messages=[
            {"role": "developer", "content": developer_prompt},
            {
                "role": "user",
                "content": json.dumps(user_payload, ensure_ascii=False, indent=2),
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": make_resolution_schema(valid_ids),
        },
    )

    content = response.choices[0].message.content
    parsed = json.loads(content)

    selected = parsed.get("selected_hpo_id", "NONE")
    if selected not in set(valid_ids) | {"NONE"}:
        parsed["decision_status"] = "unresolved"
        parsed["selected_hpo_id"] = "NONE"
        parsed["mapping_relation"] = "no_match"
        parsed["manual_review"] = True
        parsed["confidence"] = 0.0
        parsed["rationale"] = "Model returned an invalid HPO ID outside the shortlist."

    if parsed.get("selected_hpo_id") == "NONE":
        parsed["mapping_relation"] = "no_match"
        if parsed.get("decision_status") == "resolved":
            parsed["decision_status"] = "unresolved"

    return parsed


def resolve_with_hybrid_retrieval(
    extracted_items: List[Dict[str, Any]],
    alias_df: pd.DataFrame,
    embedding_index: Dict[str, Any],
    chat_model: str,
    embedding_model: str,
    fuzzy_top_k: int,
    semantic_top_k: int,
    merged_top_k: int,
    llm_seed: int,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    fuzzy_rows: List[Dict[str, Any]] = []
    semantic_rows: List[Dict[str, Any]] = []
    merged_rows: List[Dict[str, Any]] = []
    resolution_rows: List[Dict[str, Any]] = []

    for i, item in enumerate(extracted_items, start=1):
        phrase = clean_phrase(item.get("normalized_phenotype", ""))
        if not phrase:
            continue

        fuzzy_df = fuzzy_candidates(phrase, alias_df, top_k=fuzzy_top_k)
        semantic_df = semantic_candidates(
            phrase,
            embedding_index=embedding_index,
            embedding_model=embedding_model,
            top_k=semantic_top_k,
        )
        merged_df = merge_candidate_lists(fuzzy_df, semantic_df, merged_top_k=merged_top_k)
        decision = llm_resolve_to_hpo(item, merged_df, model=chat_model, seed=llm_seed)

        for rank, (_, row) in enumerate(fuzzy_df.iterrows(), start=1):
            fuzzy_rows.append(
                {
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
                }
            )

        for _, row in semantic_df.iterrows():
            semantic_rows.append(
                {
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
                }
            )

        merged_df = merged_df.copy()
        merged_df["phenotype_index"] = i
        merged_df["normalized_phenotype"] = phrase
        merged_df["source_fragment"] = item.get("source_fragment", "")
        merged_df["category"] = item.get("category", "")
        merged_df["centrality"] = item.get("centrality", "")
        merged_df["polarity"] = item.get("polarity", "")
        merged_df["temporality"] = item.get("temporality", "")
        merged_rows.extend(merged_df.to_dict(orient="records"))

        selected_id = decision.get("selected_hpo_id", "NONE")
        selected_rank = None
        selected_label = None
        if selected_id != "NONE":
            hit = merged_df[merged_df["hpo_id"] == selected_id]
            if not hit.empty:
                selected_rank = int(hit.iloc[0]["candidate_rank"])
                selected_label = str(hit.iloc[0]["label"])

        resolution_rows.append(
            {
                "phenotype_index": i,
                "normalized_phenotype": phrase,
                "source_fragment": item.get("source_fragment", ""),
                "category": item.get("category", ""),
                "centrality": item.get("centrality", ""),
                "polarity": item.get("polarity", ""),
                "temporality": item.get("temporality", ""),
                "decision_status": decision["decision_status"],
                "selected_hpo_id": selected_id,
                "selected_label": selected_label,
                "selected_candidate_rank": selected_rank,
                "mapping_relation": decision["mapping_relation"],
                "confidence": decision["confidence"],
                "manual_review": decision["manual_review"],
                "rationale": decision["rationale"],
            }
        )

    return (
        pd.DataFrame(fuzzy_rows),
        pd.DataFrame(semantic_rows),
        pd.DataFrame(merged_rows),
        pd.DataFrame(resolution_rows),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--asd_text",
        type=str,
        default="DSM5_ASD_preprocessed/ASD_core_phenotype_only.txt",
    )
    parser.add_argument("--hpo_json", type=str, required=True)
    parser.add_argument("--outdir", type=str, default="pilot_hpo_run_hybrid")
    parser.add_argument("--embedding_cache", type=str, default=None)
    parser.add_argument("--embedding_batch_size", type=int, default=128)
    parser.add_argument("--fuzzy_top_k", type=int, default=8)
    parser.add_argument("--semantic_top_k", type=int, default=12)
    parser.add_argument("--merged_top_k", type=int, default=12)
    parser.add_argument("--llm_seed", type=int, default=1)
    parser.add_argument(
        "--allow_proxy_in_final",
        action="store_true",
        help="Include proxy_related matches in final resolved HPO term set.",
    )
    parser.add_argument(
        "--force_rebuild_embeddings",
        action="store_true",
        help="Recompute the HPO embedding cache even if a matching cache exists.",
    )
    args = parser.parse_args()

    chat_model = os.environ.get("OPENAI_MODEL", "gpt-5.4")

    embedding_model = os.environ.get("OPENAI_EMBED_MODEL", "text-embedding-3-large")

    asd_text_path = Path(args.asd_text)
    hpo_json_path = Path(args.hpo_json)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    embedding_cache = (
        Path(args.embedding_cache)
        if args.embedding_cache
        else outdir / "hpo_embedding_cache.pkl"
    )

    text = read_text(asd_text_path)
    raw = call_openai_extract(text=text, model=chat_model)
    (outdir / "01_raw_llm_output.json").write_text(
        json.dumps(raw, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    extracted = pd.DataFrame(raw["items"])
    if extracted.empty:
        raise RuntimeError("LLM returned no phenotype items.")

    extracted["normalized_phenotype"] = (
        extracted["normalized_phenotype"].map(clean_phrase).str.strip().str.lower()
    )
    extracted = extracted[
        extracted["normalized_phenotype"].notna()
        & (extracted["normalized_phenotype"] != "")
    ].copy()
    extracted = extracted.drop_duplicates(
        subset=["normalized_phenotype", "polarity", "centrality"]
    ).reset_index(drop=True)
    extracted.to_csv(outdir / "02_extracted_phenotypes.csv", index=False)

    print(
        extracted[
            [
                "normalized_phenotype",
                "category",
                "centrality",
                "polarity",
                "temporality",
            ]
        ].head(40).to_string(index=False)
    )

    hpo_df = load_hpo_json(hpo_json_path)
    alias_df = build_alias_table(hpo_df)
    embedding_index = build_or_load_embedding_index(
        hpo_df=hpo_df,
        cache_path=embedding_cache,
        embedding_model=embedding_model,
        batch_size=args.embedding_batch_size,
        force_rebuild=args.force_rebuild_embeddings,
    )

    fuzzy_df, semantic_df, merged_df, resolution_df = resolve_with_hybrid_retrieval(
        extracted_items=extracted.to_dict(orient="records"),
        alias_df=alias_df,
        embedding_index=embedding_index,
        chat_model=chat_model,
        embedding_model=embedding_model,
        fuzzy_top_k=args.fuzzy_top_k,
        semantic_top_k=args.semantic_top_k,
        merged_top_k=args.merged_top_k,
        llm_seed=args.llm_seed,
    )

    fuzzy_df.to_csv(outdir / "03_fuzzy_hpo_candidates.csv", index=False)
    semantic_df.to_csv(outdir / "04_semantic_hpo_candidates.csv", index=False)
    merged_df.to_csv(outdir / "05_merged_hpo_candidates.csv", index=False)

    with (outdir / "06_llm_hpo_resolutions.jsonl").open("w", encoding="utf-8") as f:
        for row in resolution_df.to_dict(orient="records"):
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    resolution_df.to_csv(outdir / "06b_llm_hpo_resolutions.csv", index=False)

    allowed_relations = {
        "exact",
        "broader_than_source",
        "narrower_than_source",
    }
    if args.allow_proxy_in_final:
        allowed_relations.add("proxy_related")

    resolved = resolution_df[
        (resolution_df["decision_status"] == "resolved")
        & (resolution_df["selected_hpo_id"] != "NONE")
        & (resolution_df["polarity"].isin(["present", "bidirectional"]))
        & (resolution_df["centrality"].isin(["core", "supporting"]))
        & (resolution_df["mapping_relation"].isin(allowed_relations))
    ].copy()

    resolved = resolved.sort_values(
        ["manual_review", "confidence"],
        ascending=[True, False],
    ).drop_duplicates(subset=["selected_hpo_id"], keep="first")

    resolved = resolved.rename(
        columns={
            "selected_hpo_id": "hpo_id",
            "selected_label": "hpo_label",
        }
    )

    resolved[
        [
            "hpo_id",
            "hpo_label",
            "normalized_phenotype",
            "category",
            "centrality",
            "temporality",
            "mapping_relation",
            "confidence",
            "manual_review",
            "rationale",
        ]
    ].to_csv(outdir / "07_final_resolved_hpo_terms.tsv", sep="\t", index=False)

    unresolved = resolution_df[
        (resolution_df["decision_status"] != "resolved")
        | (~resolution_df["mapping_relation"].isin(allowed_relations))
        | (resolution_df["selected_hpo_id"] == "NONE")
    ].copy()
    unresolved.to_csv(outdir / "08_unresolved_phenotypes.csv", index=False)

    print(f"Done. Outputs written to: {outdir.resolve()}")
    print(f"Extracted items: {len(extracted)}")
    print(f"Fuzzy candidates: {len(fuzzy_df)}")
    print(f"Semantic candidates: {len(semantic_df)}")
    print(f"Merged candidates: {len(merged_df)}")
    print(f"Resolved HPO terms: {resolved.shape[0]}")
    print(f"Unresolved items: {unresolved.shape[0]}")


if __name__ == "__main__":
    main()
