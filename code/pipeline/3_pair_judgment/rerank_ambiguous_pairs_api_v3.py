#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

RERANK_SCHEMA = {
    "name": "pair_rerank_bundle",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "target_id": {"type": "string"},
            "selected_candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "candidate_index": {"type": "integer"},
                        "rerank_action": {
                            "type": "string",
                            "enum": ["promote", "keep", "demote", "abstain"]
                        },
                        "comparable_observable": {"type": "boolean"},
                        "evidence_scope": {
                            "type": "string",
                            "enum": [
                                "organism_behavior",
                                "organism_sensory",
                                "developmental_behavior",
                                "cellular_or_circuit_only",
                                "unclear",
                            ]
                        },
                        "behavioral_analog_type": {
                            "type": "string",
                            "enum": ["direct_analog", "close_support", "weak_support", "mechanistic_only", "mismatch"]
                        },
                        "strict_eligible": {"type": "boolean"},
                        "broad_eligible": {"type": "boolean"},
                        "reason": {"type": "string"},
                    },
                    "required": [
                        "candidate_index",
                        "rerank_action",
                        "comparable_observable",
                        "evidence_scope",
                        "behavioral_analog_type",
                        "strict_eligible",
                        "broad_eligible",
                        "reason",
                    ]
                }
            }
        },
        "required": ["target_id", "selected_candidates"]
    }
}

FEATURE_SPECS = [
    ("text_embed_cosine", "embed", True),
    ("lexical_score", "lexical", True),
    ("ancestor_information_content", "resnik", False),
    ("jaccard_similarity", "jaccard", False),
    ("owl_embed_score", "owl", False),
]


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".tsv", ".txt"}:
        return pd.read_csv(path, sep="\t")
    return pd.read_csv(path)


def normalize_present(col: pd.Series) -> pd.Series:
    raw = pd.to_numeric(col, errors="coerce")
    present = raw.notna()
    out = pd.Series(np.nan, index=raw.index, dtype=float)
    if present.any():
        vals = raw[present].astype(float)
        if float(vals.max()) == float(vals.min()):
            out.loc[present] = 0.0
        else:
            out.loc[present] = (vals - vals.min()) / (vals.max() - vals.min())
    return out


def compute_transparent_score(
    df: pd.DataFrame,
    weights: Dict[str, float],
    lexical_factor_when_structural_missing: float = 1.0,
) -> pd.DataFrame:
    out = df.copy()
    for raw_col, short, _ in FEATURE_SPECS:
        if raw_col not in out.columns:
            out[raw_col] = np.nan
        out[f"{short}_norm"] = normalize_present(out[raw_col])
        out[f"has_{short}"] = out[raw_col].notna()

    scores = []
    weight_sums = []
    n_channels = []
    structural_only_missing = []
    for _, r in out.iterrows():
        num = 0.0
        den = 0.0
        present_count = 0
        row_structural_missing = bool(
            pd.isna(r.get("resnik_norm")) and pd.isna(r.get("jaccard_norm"))
        )
        for raw_col, short, _always_expected in FEATURE_SPECS:
            norm_val = r.get(f"{short}_norm", np.nan)
            if pd.notna(norm_val):
                w = float(weights.get(short, 0.0))
                if short == "lexical" and row_structural_missing and lexical_factor_when_structural_missing != 1.0:
                    w *= float(lexical_factor_when_structural_missing)
                num += w * float(norm_val)
                den += w
                present_count += 1
        scores.append(num / den if den > 0 else 0.0)
        weight_sums.append(den)
        n_channels.append(present_count)
        structural_only_missing.append(row_structural_missing)
    out["transparent_score"] = scores
    out["transparent_weight_sum"] = weight_sums
    out["n_available_channels"] = n_channels
    out["structural_missing"] = structural_only_missing
    return out


def identify_ambiguous_bundles(
    feat: pd.DataFrame,
    top_n: int,
    ambiguity_margin: float,
    gray_low: float,
    gray_high: float,
    require_multiple_channels: bool,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    keep_tables = []
    sort_cols = ["transparent_score", "embed_norm", "lexical_norm", "resnik_norm", "jaccard_norm"]
    for target_id, g in feat.groupby("target_id", dropna=False):
        g = g.copy().sort_values(sort_cols, ascending=[False, False, False, False, False], na_position="last")
        g["transparent_rank"] = np.arange(1, len(g) + 1)
        top = g.head(top_n).copy()
        keep_tables.append(g)
        if len(top) == 0:
            continue
        top_score = float(top.iloc[0]["transparent_score"])
        second = float(top.iloc[1]["transparent_score"]) if len(top) > 1 else -1.0
        margin = top_score - second if second >= 0 else 1.0
        top_channels = int(top.iloc[0].get("n_available_channels", 0))
        top_struct_missing = bool(top.iloc[0].get("structural_missing", False))
        ambiguous = (margin <= ambiguity_margin) or (gray_low <= top_score <= gray_high)
        if require_multiple_channels and top_channels < 2:
            ambiguous = True
        rows.append({
            "target_id": target_id,
            "hpo_id": top.iloc[0].get("hpo_id", ""),
            "hpo_label": top.iloc[0].get("hpo_label", ""),
            "human_domain": top.iloc[0].get("human_domain", ""),
            "top_transparent_score": top_score,
            "second_transparent_score": second,
            "top_margin": margin,
            "n_candidates_top_bundle": len(top),
            "top_available_channels": top_channels,
            "top_structural_missing": top_struct_missing,
            "ambiguous": bool(ambiguous),
        })
    bundles = pd.DataFrame(rows)
    all_ranked = pd.concat(keep_tables, ignore_index=True) if keep_tables else feat.copy()
    return bundles, all_ranked


def call_llm_bundle(client: OpenAI, model: str, target_id: str, hpo_label: str, target_text: str, domain: str, bundle: pd.DataFrame, seed: int) -> Dict:
    developer_prompt = """
You are reranking ambiguous cross-species phenotype candidate pairs.

Important constraints:
- You are not the primary scorer.
- Transparent non-LLM signals have already identified a small ambiguous bundle.
- Your job is only to promote, keep, demote, or abstain on those candidates.
- Ignore any hidden prior about disease genes or disorder labels; you are not given them.
- Do not use any hand-built tier or relevance hierarchy; judge only behavioral/sensory/developmental analog quality.

Definitions:
- comparable_observable=true only if the mouse term is an organism-level or developmentally interpretable observable that could plausibly support the human target.
- evidence_scope=cellular_or_circuit_only if the term is primarily mechanistic physiology or cellular/circuit description rather than a behavioral/sensory/developmental organism-level phenotype.
- strict_eligible=true only for high-quality organism-level analogs suitable for strict domain support; the disorder-specific construct-validity criteria are appended by the wrapper as a developer_prompt_addendum.
- broad_eligible=true for weaker but still meaningful support.
- abstain if none of the candidates are suitable organism-level analogs.

Do not invent new candidates. Evaluate only the listed bundle.
""".strip()

    cand_lines = []
    for i, (_, r) in enumerate(bundle.iterrows(), start=1):
        pieces = [
            f"[{i}] mp_id={r['mp_id']}",
            f"mp_term={r['mp_term']}",
            f"mp_definition={clean(r.get('mp_definition',''))}",
            f"mouse_domain={r['mouse_domain']}",
            f"transparent_score={float(r['transparent_score']):.3f}",
            f"embed={fmt_opt(r.get('embed_norm'))}",
            f"lexical={fmt_opt(r.get('lexical_norm'))}",
            f"resnik={fmt_opt(r.get('resnik_norm'))}",
            f"jaccard={fmt_opt(r.get('jaccard_norm'))}",
            f"available_channels={int(r.get('n_available_channels',0))}",
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
        response_format={"type": "json_schema", "json_schema": RERANK_SCHEMA},
    )
    content = response.choices[0].message.content
    return json.loads(content)


def fmt_opt(x) -> str:
    return f"{float(x):.3f}" if pd.notna(x) else "NA"


def clean(x: str) -> str:
    return re.sub(r"\s+", " ", str(x or "")).strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate_feature_tsv", type=str, default="04_candidate_feature_table.tsv")
    ap.add_argument("--model", type=str, default=os.environ.get("OPENAI_MODEL", "gpt-5.4"))
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--top_n_bundle", type=int, default=5)
    ap.add_argument("--ambiguity_margin", type=float, default=0.08)
    ap.add_argument("--gray_low", type=float, default=0.35)
    ap.add_argument("--gray_high", type=float, default=0.70)
    ap.add_argument("--w_embed", type=float, default=0.45)
    ap.add_argument("--w_lexical", type=float, default=0.25)
    ap.add_argument("--w_resnik", type=float, default=0.20)
    ap.add_argument("--w_jaccard", type=float, default=0.10)
    ap.add_argument("--w_owl", type=float, default=0.0)
    ap.add_argument("--promote_bonus", type=float, default=0.10)
    ap.add_argument("--demote_penalty", type=float, default=0.10)
    ap.add_argument("--require_multiple_channels", action="store_true")
    ap.add_argument(
        "--lexical_factor_when_structural_missing",
        type=float,
        default=1.0,
        help=(
            "Multiply lexical weight by this factor when both Resnik IC and Jaccard channels are "
            "absent (structural_missing=True). Default 1.0 = backwards-compatible no-op. "
            "Values <1.0 reduce lexical's effective contribution in the structural-missing case "
            "where it would otherwise inflate via redistribution. See compute_transparent_score "
            "docstring for rationale and recommended values."
        ),
    )
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--outdir", type=str, default="asd_pair_rerank_v3")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    feat = read_table(Path(args.candidate_feature_tsv)).copy()
    weights = {
        "embed": args.w_embed,
        "lexical": args.w_lexical,
        "resnik": args.w_resnik,
        "jaccard": args.w_jaccard,
        "owl": args.w_owl,
    }
    feat = compute_transparent_score(
        feat, weights,
        lexical_factor_when_structural_missing=args.lexical_factor_when_structural_missing,
    )

    avail = []
    for (hd, md), g in feat.groupby(["human_domain", "matched_domain"], dropna=False):
        row = {
            "human_domain": hd,
            "matched_domain": md,
            "n_pairs": len(g),
            "mean_lexical": pd.to_numeric(g.get("lexical_score"), errors="coerce").mean(),
            "mean_embed": pd.to_numeric(g.get("text_embed_cosine"), errors="coerce").mean(),
            "mean_jaccard": pd.to_numeric(g.get("jaccard_similarity"), errors="coerce").mean(),
            "mean_ic": pd.to_numeric(g.get("ancestor_information_content"), errors="coerce").mean(),
            "present_embed_frac": float(g["has_embed"].mean()) if "has_embed" in g else np.nan,
            "present_lexical_frac": float(g["has_lexical"].mean()) if "has_lexical" in g else np.nan,
            "present_resnik_frac": float(g["has_resnik"].mean()) if "has_resnik" in g else np.nan,
            "present_jaccard_frac": float(g["has_jaccard"].mean()) if "has_jaccard" in g else np.nan,
            "mean_available_channels": float(g["n_available_channels"].mean()),
            "structural_missing_frac": float(g["structural_missing"].mean()),
        }
        avail.append(row)
    pd.DataFrame(avail).sort_values(["human_domain", "matched_domain"]).to_csv(outdir / "06_channel_availability_summary.tsv", sep="\t", index=False)

    bundles, all_ranked = identify_ambiguous_bundles(
        feat, top_n=args.top_n_bundle,
        ambiguity_margin=args.ambiguity_margin,
        gray_low=args.gray_low,
        gray_high=args.gray_high,
        require_multiple_channels=args.require_multiple_channels,
    )
    bundles.to_csv(outdir / "01_ambiguous_bundles.tsv", sep="\t", index=False)

    if OpenAI is None:
        raise RuntimeError("openai package not installed")
    client = OpenAI()

    raw_path = outdir / "02_rerank_raw.jsonl"
    done = set()
    if args.resume and raw_path.exists():
        with raw_path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    done.add(obj.get("target_id"))
                except Exception:
                    pass

    with raw_path.open("a", encoding="utf-8") as fout:
        for _, b in bundles[bundles["ambiguous"] == True].iterrows():
            target_id = b["target_id"]
            if target_id in done:
                continue
            g = all_ranked[all_ranked["target_id"] == target_id].sort_values("transparent_rank").head(args.top_n_bundle).copy()
            if g.empty:
                continue
            obj = call_llm_bundle(
                client=client,
                model=args.model,
                target_id=target_id,
                hpo_label=str(g.iloc[0].get("hpo_label", "")),
                target_text=str(g.iloc[0].get("target_text", "")),
                domain=str(g.iloc[0].get("human_domain", "")),
                bundle=g,
                seed=args.seed,
            )
            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")

    rerank_rows = []
    if raw_path.exists():
        with raw_path.open("r", encoding="utf-8") as f:
            for line in f:
                obj = json.loads(line)
                tid = obj["target_id"]
                for rec in obj.get("selected_candidates", []):
                    rerank_rows.append({"target_id": tid, **rec})
    rr = pd.DataFrame(rerank_rows)
    merged = all_ranked.copy()
    if not rr.empty:
        n_rr = len(rr)
        rr = rr.drop_duplicates(subset=["target_id", "candidate_index"], keep="last")
        if len(rr) != n_rr:
            print(f"  [B1] rerank responses deduplicated: {n_rr} -> {len(rr)} rows. The raw jsonl "
                  f"contains repeated responses for the same target, which happens when a previous "
                  f"run was re-executed without --resume.", flush=True)
        merged["candidate_index"] = merged.groupby("target_id").cumcount() + 1
        n_pre = len(merged)
        merged = merged.merge(rr, on=["target_id", "candidate_index"], how="left")
        if len(merged) != n_pre:
            raise AssertionError(f"B1: the rerank merge changed the row count, {n_pre} -> "
                                 f"{len(merged)}. (target_id, candidate_index) is not unique in rr.")
    else:
        for c in ["rerank_action", "comparable_observable", "evidence_scope", "behavioral_analog_type", "strict_eligible", "broad_eligible", "reason"]:
            merged[c] = np.nan

    action_delta = {"promote": args.promote_bonus, "keep": 0.0, "demote": -args.demote_penalty, "abstain": -0.25}
    merged["rerank_delta"] = merged["rerank_action"].map(action_delta).fillna(0.0)
    merged["final_pair_score"] = (merged["transparent_score"] + merged["rerank_delta"]).clip(lower=0.0, upper=1.0)
    merged.to_csv(outdir / "03_reranked_pairs.tsv", sep="\t", index=False)

    summary = {
        "n_total_pairs": int(len(merged)),
        "n_targets": int(merged["target_id"].nunique()) if "target_id" in merged.columns else 0,
        "n_ambiguous_targets": int(bundles["ambiguous"].sum()) if not bundles.empty else 0,
        "n_reranked_records": int(len(rr)),
        "abstain_rate": float((rr["rerank_action"] == "abstain").mean()) if (not rr.empty and "rerank_action" in rr.columns) else 0.0,
        "cellular_or_circuit_only_rate": float((rr["evidence_scope"] == "cellular_or_circuit_only").mean()) if (not rr.empty and "evidence_scope" in rr.columns) else 0.0,
        "strict_eligible_rate": float(pd.to_numeric(merged["strict_eligible"], errors="coerce").fillna(0).mean()) if "strict_eligible" in merged.columns else 0.0,
        "structural_missing_pair_rate": float(pd.to_numeric(merged["structural_missing"], errors="coerce").fillna(0).mean()),
    }
    pd.DataFrame([summary]).to_csv(outdir / "04_rerank_summary.tsv", sep="\t", index=False)

    if "strict_eligible" in merged.columns:
        strict_any = merged.groupby("target_id", dropna=False)["strict_eligible"].apply(lambda s: pd.to_numeric(s, errors="coerce").fillna(0).astype(bool).any()).reset_index(name="has_strict_pair")
        missing = merged[["target_id", "hpo_id", "hpo_label", "human_domain"]].drop_duplicates().merge(strict_any, on="target_id", how="left")
        missing = missing[missing["has_strict_pair"] != True].copy()
    else:
        missing = merged[["target_id", "hpo_id", "hpo_label", "human_domain"]].drop_duplicates().copy()
    missing.to_csv(outdir / "05_targets_without_strict_pairs.tsv", sep="\t", index=False)

    config = {
        "candidate_feature_tsv": args.candidate_feature_tsv,
        "model": args.model,
        "seed": args.seed,
        "top_n_bundle": args.top_n_bundle,
        "ambiguity_margin": args.ambiguity_margin,
        "gray_low": args.gray_low,
        "gray_high": args.gray_high,
        "weights": weights,
        "promote_bonus": args.promote_bonus,
        "demote_penalty": args.demote_penalty,
        "require_multiple_channels": args.require_multiple_channels,
        "note": "Transparent score renormalizes weights per pair across available channels only; missing ontology channels are not treated as zero.",
    }
    (outdir / "07_run_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    print(f"Done. Outputs written to: {outdir.resolve()}")
    print(f"Targets: {merged['target_id'].nunique() if 'target_id' in merged.columns else 0}")
    print(f"Ambiguous targets: {summary['n_ambiguous_targets']}")


if __name__ == "__main__":
    main()
