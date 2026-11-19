#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
from openai import OpenAI


CLASSIFICATION_SCHEMA = {
    "name": "mp_term_asd_taxonomy",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "mp_id": {"type": "string"},
            "mp_label": {"type": "string"},
            "primary_domain": {
                "type": "string",
                "enum": [
                    "social_interaction",
                    "communication",
                    "repetitive_restricted",
                    "sensory_reactivity",
                    "cognitive_behavioral_support",
                    "motor_support",
                    "developmental_support",
                    "mechanistic_neurobiology",
                    "generic_neurological_abnormality",
                    "non_neurological_or_other",
                    "unclear",
                ],
            },
            "secondary_domain": {
                "type": "string",
                "enum": [
                    "none",
                    "social_interaction",
                    "communication",
                    "repetitive_restricted",
                    "sensory_reactivity",
                    "cognitive_behavioral_support",
                    "motor_support",
                    "developmental_support",
                    "mechanistic_neurobiology",
                    "generic_neurological_abnormality",
                    "non_neurological_or_other",
                    "unclear",
                ],
            },
            "relevance_tier": {
                "type": "integer",
                "enum": [1, 2, 3, 4, 5],
            },
            "tier_label": {
                "type": "string",
                "enum": [
                    "strict_face_validity",
                    "broad_behavioral_support",
                    "mechanistic_neural_support",
                    "generic_neurological_background",
                    "off_target_or_uninformative",
                ],
            },
            "allow_strict_asd_face_validity": {"type": "boolean"},
            "allow_broad_support_analysis": {"type": "boolean"},
            "allow_mechanistic_support_analysis": {"type": "boolean"},
            "needs_manual_review": {"type": "boolean"},
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
            },
            "reason": {"type": "string"},
        },
        "required": [
            "mp_id",
            "mp_label",
            "primary_domain",
            "secondary_domain",
            "relevance_tier",
            "tier_label",
            "allow_strict_asd_face_validity",
            "allow_broad_support_analysis",
            "allow_mechanistic_support_analysis",
            "needs_manual_review",
            "confidence",
            "reason",
        ],
    },
}


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".tsv", ".txt"}:
        return pd.read_csv(path, sep="\t")
    return pd.read_csv(path)


def normalize_space(x: Any) -> str:
    if pd.isna(x):
        return ""
    x = str(x)
    x = re.sub(r"\s+", " ", x).strip()
    return x


def detect_column(df: pd.DataFrame, preferred: Iterable[str]) -> Optional[str]:
    lower_map = {c.lower(): c for c in df.columns}
    for name in preferred:
        if name.lower() in lower_map:
            return lower_map[name.lower()]
    for c in df.columns:
        cl = c.lower()
        for name in preferred:
            if name.lower() in cl:
                return c
    return None


def build_unique_terms(
    df: pd.DataFrame,
    mp_id_col: str,
    mp_label_col: str,
    mp_definition_col: Optional[str],
    parent_col: Optional[str],
    ancestor_col: Optional[str],
) -> pd.DataFrame:
    keep = pd.DataFrame(
        {
            "mp_id": df[mp_id_col].map(normalize_space) if mp_id_col in df.columns else "",
            "mp_label": df[mp_label_col].map(normalize_space),
            "mp_definition": df[mp_definition_col].map(normalize_space) if mp_definition_col else "",
            "parent_label": df[parent_col].map(normalize_space) if parent_col else "",
            "ancestor_label": df[ancestor_col].map(normalize_space) if ancestor_col else "",
        }
    )
    keep = keep[(keep["mp_label"] != "")].copy()
    keep["context_len"] = (
        keep["mp_definition"].str.len().fillna(0)
        + keep["parent_label"].str.len().fillna(0)
        + keep["ancestor_label"].str.len().fillna(0)
    )
    keep = (
        keep.sort_values(["mp_id", "mp_label", "context_len"], ascending=[True, True, False])
        .drop_duplicates(subset=["mp_id", "mp_label"], keep="first")
        .drop(columns=["context_len"])
        .reset_index(drop=True)
    )
    return keep


GENERIC_HARD_RULES = [
    (re.compile(r"\babnormal behavior\b", re.I), "generic_neurological_background"),
    (re.compile(r"\babnormal nervous system (morphology|physiology)\b", re.I), "generic_neurological_background"),
    (re.compile(r"\babnormal brain (morphology|physiology)\b", re.I), "generic_neurological_background"),
    (re.compile(r"\babnormality of nervous system physiology\b", re.I), "generic_neurological_background"),
    (re.compile(r"\babnormality of nervous system morphology\b", re.I), "generic_neurological_background"),
]


def apply_hard_rule(mp_label: str, mp_definition: str, parent_label: str, ancestor_label: str) -> Optional[Dict[str, Any]]:
    text = " ".join([mp_label, mp_definition, parent_label, ancestor_label]).strip()
    for pat, kind in GENERIC_HARD_RULES:
        if pat.search(text):
            return {
                "primary_domain": "generic_neurological_abnormality",
                "secondary_domain": "none",
                "relevance_tier": 4,
                "tier_label": "generic_neurological_background",
                "allow_strict_asd_face_validity": False,
                "allow_broad_support_analysis": False,
                "allow_mechanistic_support_analysis": True,
                "needs_manual_review": False,
                "confidence": 0.99,
                "reason": "Hard-rule classification: broad neurological umbrella term should not drive ASD face-validity ranking.",
            }
    return None


def call_openai_classify(
    client: OpenAI,
    model: str,
    row: Dict[str, str],
    seed: int,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    developer_prompt = """
You are classifying a Mammalian Phenotype (MP) term for ASD-related analysis.

IMPORTANT ANTI-LEAKAGE / ANTI-DOUBLE-DIPPING RULES:
- You must classify ONLY from the MP term text and optional definition/parent/ancestor context.
- Do NOT infer anything from genotype, gene, disease label, SFARI status, or any ranking result.
- Treat this as a blinded ontology-term taxonomy task.

Goal:
Assign the MP term to a domain and analytic tier for later ASD mouse-model analysis.

Tier definitions:
1 = strict_face_validity
   Direct DSM-5 ASD-face-validity phenotype. Be STRICT — only the four canonical
   anchors below qualify, and only when the term clearly maps to one of them.
2 = broad_behavioral_support
   Behavioral/developmental support phenotype relevant to ASD context but not itself a direct
   core face-validity phenotype. Examples: learning/memory, attention, anxiety-like behavior,
   motor coordination, developmental delay, nociception/pain thresholds, habituation.
3 = mechanistic_neural_support
   Mechanistic neural phenotype relevant to ASD biology but not a face-validity phenotype.
   Examples: synaptic transmission, circuit physiology, EEG/brain-wave abnormalities,
   seizure susceptibility, neuronal morphology.
4 = generic_neurological_background
   Very broad neurological or behavioral abnormality / umbrella term that is too generic to be
   informative for strict ranking.
5 = off_target_or_uninformative
   Non-neural, multisystem, or otherwise not meaningfully informative for ASD face-validity.

Tier 1 boundaries (explicit positive AND negative examples — be strict):

  social_interaction (Tier 1):
    YES: deficits in conspecific peer interaction, social investigation,
         social recognition, social approach, social novelty preference,
         reciprocal social play, affiliation behavior between peers.
    NO (use Tier 2 instead):
         - maternal behavior (pup retrieval, nest building, lactation-related)
         - agonistic / dominance behavior (mounting, submission, aggression,
           barbering as a dominance trait, fighting, territorial display)
         - sexual / mating behavior
         - parental investment behavior

  communication (Tier 1):
    YES: vocalization output (especially ultrasonic vocalization in pups
         or adults), reciprocal communication-like behavior, communicative
         gesture-like output.
    NO (Tier 2 or lower):
         - general auditory function (hearing thresholds without behavioral context)
         - non-communicative vocal sounds

  repetitive_restricted (Tier 1):
    YES: stereotypy, repetitive grooming with rigid pattern, perseveration,
         insistence on sameness, restricted/fixated interests, ritualized
         non-communicative behavior, marble burying as repetitive output.
    NO (Tier 2):
         - general grooming behavior (without rigidity / excessive pattern)
         - barbering as a coping or dominance trait
         - sexual mounting, head-bobbing in courtship contexts
         - normal exploration

  sensory_reactivity (Tier 1):
    YES: hyper/hyporeactivity to ENVIRONMENTAL sensory INPUT — auditory
         hypersensitivity, tactile aversion or unresponsiveness, visual
         fascination or aversion, olfactory hyper/hyporesponse, thermal
         hyperreactivity to environmental temperature, indifference to
         environmental sensory input.
    NO (Tier 2 — these are general somatosensory/cognitive function,
         not DSM-5 sensory reactivity):
         - nociception / pain thresholds (thermal nociception, mechanical
           nociception, chemical nociception, nociceptive thresholds)
         - habituation / dishabituation (cognitive, not sensory reactivity)
         - general reflex function (e.g., baseline startle without
           hyper/hypo qualifier)
         - itch / scratching behavior unless framed as sensory hyperreactivity

When in doubt at the Tier 1 / Tier 2 boundary, prefer Tier 2 and set
needs_manual_review=true. BUT also do not be so conservative that you
miss clear Tier 1 anchors — "social withdrawal", "abnormal social play",
"abnormal response to tactile stimuli", "auditory hypersensitivity" are
the canonical examples and should be Tier 1 without hesitation.

CRITICAL DISTINCTION — sensory CAPACITY vs sensory REACTIVITY:
DSM-5 sensory_reactivity is about how the organism RESPONDS to
environmental sensory input. It is NOT about whether the organism CAN
sense the input at all.
  - capacity-to-sense (deficit/loss of sensory ability): Tier 2 or Tier 5,
    NEVER Tier 1.
      Examples: anosmia (loss of smell capacity) → Tier 5.
                photosensitivity as dermatologic UV reaction → Tier 5.
                abnormal thermosensation (capacity to detect temperature)
                  → Tier 2 (somatosensory function).
                abnormal nociception / pain thresholds → Tier 2.
                deafness, blindness → Tier 5 (capacity loss).
  - reactivity-to-input (hyper/hyporeactivity to environmental sensory
    stimuli): Tier 1 sensory_reactivity.
      Examples: auditory hypersensitivity → Tier 1.
                abnormal behavioral response to light → Tier 1.
                tactile aversion or unresponsiveness to texture → Tier 1.
                indifference to pain stimulus (BEHAVIORAL response, NOT
                  pain threshold) → Tier 1, mark needs_review.
                abnormal response to novel odor → borderline; if framed
                  as behavioral reactivity, Tier 1; if framed as
                  habituation/recognition, Tier 2.

CRITICAL DISTINCTION — Tier 4 is for UMBRELLA terms only:
Tier 4 (generic_neurological_background) is reserved for top-of-ontology
umbrella nodes like "abnormal behavior" (the parent of all behavior
terms), "abnormal nervous system physiology" (the parent of all CNS
physiology terms), "abnormality of the nervous system" (anatomic
umbrella). These are too generic to inform strict ranking.
SPECIFIC behavioral phenotypes belong in Tier 2 even if not face-validity-
relevant. Examples:
  - "abnormal locomotor activity" → Tier 2 (specific motor phenotype).
  - "increased aggression" → Tier 2 (specific behavior, not Tier 4).
  - "abnormal feeding behavior" → Tier 2.
  - "tremors" → Tier 2.
  - "abnormal behavior" (as the umbrella node itself) → Tier 4.
  - "abnormal nervous system physiology" → Tier 4.

WORKED EXAMPLES (use these as anchors when borderline):

Social interaction:
  abnormal social investigation                  → Tier 1 social_interaction
  decreased social novelty preference            → Tier 1 social_interaction
  social withdrawal                              → Tier 1 social_interaction
  abnormal social play behavior                  → Tier 1 social_interaction
  impaired social recognition                    → Tier 1 social_interaction
  abnormal pup retrieval                         → Tier 2 (maternal, NOT social_interaction)
  submission towards male mice                   → Tier 2 (agonistic)
  abnormal mounting behavior                     → Tier 2 (sexual/dominance)
  abnormal aggression                            → Tier 2 (agonistic)

Communication:
  decreased vocalization                         → Tier 1 communication
  abnormal ultrasonic vocalization               → Tier 1 communication
  hearing loss / deafness                        → Tier 5 (capacity, NOT communication)

Repetitive / restricted:
  stereotypic behavior                           → Tier 1 repetitive_restricted
  increased grooming behavior with rigid pattern → Tier 1 repetitive_restricted
  perseveration                                  → Tier 1 repetitive_restricted
  abnormal grooming behavior (general)           → Tier 2 (could be coping, dominance)
  abnormal barbering behavior                    → Tier 2 (typically dominance/coping)

Sensory reactivity vs capacity:
  auditory hypersensitivity                      → Tier 1 sensory_reactivity
  abnormal response to tactile stimuli           → Tier 1 sensory_reactivity
  abnormal behavioral response to light          → Tier 1 sensory_reactivity
  unresponsive to tactile stimuli                → Tier 1 sensory_reactivity
  abnormal startle reflex (without hyper/hypo)   → Tier 2 (general reflex)
  abnormal thermal nociception                   → Tier 2 (pain capacity)
  abnormal mechanical nociception                → Tier 2
  abnormal chemical nociception                  → Tier 2
  abnormal thermosensation                       → Tier 2 (capacity)
  abnormal dishabituation                        → Tier 2 (cognitive)
  anosmia                                        → Tier 5 (loss of capacity)
  photosensitivity                               → Tier 5 (dermatologic UV reaction)
  abnormal contrast sensitivity                  → Tier 2 (visual capacity); mark
                                                    needs_review if framed as visual
                                                    reactivity.

Tier 4 vs Tier 2 (umbrella vs specific):
  abnormal behavior (umbrella node)              → Tier 4 generic
  abnormal nervous system physiology             → Tier 4 generic
  abnormality of behavior/neurological           → Tier 4 generic
  abnormal locomotor activity                    → Tier 2 motor_support
  increased aggression                           → Tier 2
  abnormal feeding behavior                      → Tier 2
  tremors                                        → Tier 2 motor_support
  ataxia                                         → Tier 2 motor_support

Domain guidance:
- social_interaction: as above (Tier 1 anchor); do not assign for
  maternal/agonistic/sexual behavior.
- communication: vocalization, ultrasonic vocalization, reciprocal
  communication-like output.
- repetitive_restricted: stereotypy, perseveration, restricted patterning;
  exclude general grooming and dominance-trait barbering.
- sensory_reactivity: hyper/hyporeactivity to environmental sensory input;
  exclude nociception, habituation, and general reflex function.
- cognitive_behavioral_support: learning, memory, cognition, attention,
  anxiety/fear-like behavior, habituation, nociception.
- motor_support: gait, coordination, balance, locomotor abnormalities.
- developmental_support: developmental delay, growth/developmental timing
  with plausible ASD relevance.
- mechanistic_neurobiology: synaptic, circuit, electrophysiologic, neuronal,
  seizure-related mechanism.
- generic_neurological_abnormality: umbrella nervous-system or behavior term.
- non_neurological_or_other: outside useful ASD relevance.
- unclear: ambiguous.

Conservative instructions:
- Do NOT promote mechanistic neural phenotypes into strict face validity.
- Terms like abnormal synaptic transmission, abnormal brain wave pattern,
  abnormal CNS physiology, seizure EEG patterns, etc. should generally be
  Tier 3 or 4, not Tier 1.
- Nociception terms (thermal/mechanical/chemical pain thresholds) belong
  in Tier 2 (broad behavioral support), NOT Tier 1 sensory_reactivity.
- Habituation/dishabituation terms belong in Tier 2 cognitive support,
  NOT Tier 1.
- Maternal behavior (pup retrieval, nest building) belongs in Tier 2,
  NOT Tier 1 social_interaction.
- Agonistic/dominance behaviors (mounting, submission, aggression) belong
  in Tier 2, NOT Tier 1.
- Only set allow_strict_asd_face_validity=true for Tier 1.
- allow_broad_support_analysis can be true for Tiers 1-3 when appropriate.
- allow_mechanistic_support_analysis can be true for Tier 3 and some Tier 4.
- Set needs_manual_review=true when ambiguity is material.
""".strip()

    user_prompt = f"""
Classify this blinded MP term.

mp_id: {row['mp_id']}
mp_label: {row['mp_label']}
mp_definition: {row['mp_definition'] or 'NA'}
parent_label: {row['parent_label'] or 'NA'}
ancestor_label: {row['ancestor_label'] or 'NA'}
""".strip()

    response = client.chat.completions.create(
        model=model,
        temperature=0,
        seed=seed,
        messages=[
            {"role": "developer", "content": developer_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_schema", "json_schema": CLASSIFICATION_SCHEMA},
    )

    content = response.choices[0].message.content
    parsed = json.loads(content)
    meta = {
        "response_id": getattr(response, "id", None),
        "response_model": getattr(response, "model", model),
        "system_fingerprint": getattr(response, "system_fingerprint", None),
        "usage": getattr(response, "usage", None).model_dump() if getattr(response, "usage", None) else None,
    }
    return parsed, meta


def classify_terms(
    unique_df: pd.DataFrame,
    outdir: Path,
    model: str,
    seed: int,
    max_terms: Optional[int],
    resume: bool,
) -> pd.DataFrame:
    client = OpenAI()
    raw_path = outdir / "02_mp_term_taxonomy_raw.jsonl"

    completed: Dict[Tuple[str, str], Dict[str, Any]] = {}
    if resume and raw_path.exists():
        with raw_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                key = (rec["mp_id"], rec["mp_label"])
                completed[key] = rec

    rows_out: List[Dict[str, Any]] = []
    to_iter = unique_df.copy()
    if max_terms is not None:
        to_iter = to_iter.head(max_terms).copy()

    with raw_path.open("a", encoding="utf-8") as raw_fh:
        for i, row in to_iter.iterrows():
            key = (row["mp_id"], row["mp_label"])
            if key in completed:
                rows_out.append(completed[key])
                continue

            hard = apply_hard_rule(
                row["mp_label"],
                row["mp_definition"],
                row["parent_label"],
                row["ancestor_label"],
            )
            if hard is not None:
                rec = {
                    **row.to_dict(),
                    **hard,
                    "source": "hard_rule",
                    "response_id": None,
                    "response_model": None,
                    "system_fingerprint": None,
                    "usage": None,
                }
            else:
                parsed, meta = call_openai_classify(
                    client=client,
                    model=model,
                    row=row.to_dict(),
                    seed=seed,
                )
                rec = {
                    **row.to_dict(),
                    **parsed,
                    **meta,
                    "source": "openai",
                }

            raw_fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            rows_out.append(rec)
            print(
                f"[{len(rows_out)}/{len(to_iter)}] {row['mp_id'] or 'NA'} | {row['mp_label']} -> "
                f"tier {rec['relevance_tier']} ({rec['tier_label']})"
            )

    return pd.DataFrame(rows_out)


def merge_back(
    original_df: pd.DataFrame,
    taxonomy_df: pd.DataFrame,
    mp_id_col: str,
    mp_label_col: str,
) -> pd.DataFrame:
    out = original_df.copy()
    out["_merge_mp_id"] = out[mp_id_col].map(normalize_space) if mp_id_col in out.columns else ""
    out["_merge_mp_label"] = out[mp_label_col].map(normalize_space)

    tax = taxonomy_df.copy()
    tax["_merge_mp_id"] = tax["mp_id"].map(normalize_space)
    tax["_merge_mp_label"] = tax["mp_label"].map(normalize_space)

    merged = out.merge(
        tax.drop(columns=["mp_id", "mp_label"], errors="ignore"),
        on=["_merge_mp_id", "_merge_mp_label"],
        how="left",
    )
    return merged.drop(columns=["_merge_mp_id", "_merge_mp_label"], errors="ignore")


def summarize_taxonomy(taxonomy_df: pd.DataFrame) -> pd.DataFrame:
    by_tier = (
        taxonomy_df.groupby(["relevance_tier", "tier_label", "primary_domain"], dropna=False)
        .size()
        .reset_index(name="n_terms")
        .sort_values(["relevance_tier", "n_terms", "primary_domain"], ascending=[True, False, True])
    )
    return by_tier


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mouse_mp_csv", type=str, required=True)
    parser.add_argument("--outdir", type=str, default="mp_term_taxonomy")
    parser.add_argument("--model", type=str, default=os.environ.get("OPENAI_MODEL", "gpt-5.4-mini"))
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max_terms", type=int, default=None)

    parser.add_argument("--mp_id_col", type=str, default=None)
    parser.add_argument("--mp_label_col", type=str, default=None)
    parser.add_argument("--mp_definition_col", type=str, default=None)
    parser.add_argument("--parent_col", type=str, default=None)
    parser.add_argument("--ancestor_col", type=str, default=None)
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    df = read_table(Path(args.mouse_mp_csv))

    mp_id_col = args.mp_id_col or detect_column(df, ["mp_id", "phenotype_id", "mp term id", "mpid"])
    mp_label_col = args.mp_label_col or detect_column(df, ["mp_term", "mp_label", "phenotype_term", "phenotype label"])
    mp_definition_col = args.mp_definition_col or detect_column(df, ["mp_definition", "definition", "phenotype_definition"])
    parent_col = args.parent_col or detect_column(df, ["parent_label", "parent_term", "parent"])
    ancestor_col = args.ancestor_col or detect_column(df, ["ancestor_label", "ancestor_term", "ancestor"])

    if mp_label_col is None:
        raise RuntimeError("Could not detect MP term label column. Pass --mp_label_col explicitly.")

    unique_df = build_unique_terms(
        df=df,
        mp_id_col=mp_id_col if mp_id_col else mp_label_col,
        mp_label_col=mp_label_col,
        mp_definition_col=mp_definition_col,
        parent_col=parent_col,
        ancestor_col=ancestor_col,
    )
    unique_df.to_csv(outdir / "01_unique_mp_terms.tsv", sep="\t", index=False)

    taxonomy_df = classify_terms(
        unique_df=unique_df,
        outdir=outdir,
        model=args.model,
        seed=args.seed,
        max_terms=args.max_terms,
        resume=args.resume,
    )

    taxonomy_df["allow_strict_asd_face_validity"] = taxonomy_df["allow_strict_asd_face_validity"].astype(bool)
    taxonomy_df["allow_broad_support_analysis"] = taxonomy_df["allow_broad_support_analysis"].astype(bool)
    taxonomy_df["allow_mechanistic_support_analysis"] = taxonomy_df["allow_mechanistic_support_analysis"].astype(bool)
    taxonomy_df["needs_manual_review"] = taxonomy_df["needs_manual_review"].astype(bool)

    taxonomy_df.to_csv(outdir / "03_mp_term_taxonomy.tsv", sep="\t", index=False)

    merged = merge_back(
        original_df=df,
        taxonomy_df=taxonomy_df,
        mp_id_col=mp_id_col if mp_id_col else mp_label_col,
        mp_label_col=mp_label_col,
    )
    merged.to_csv(outdir / "04_mouse_rows_with_taxonomy.tsv", sep="\t", index=False)

    review = taxonomy_df[
        (taxonomy_df["needs_manual_review"]) |
        (taxonomy_df["confidence"] < 0.75) |
        (taxonomy_df["primary_domain"].isin(["unclear", "generic_neurological_abnormality"]))
    ].copy()
    review.to_csv(outdir / "05_manual_review_queue.tsv", sep="\t", index=False)

    summary = summarize_taxonomy(taxonomy_df)
    summary.to_csv(outdir / "06_taxonomy_summary.tsv", sep="\t", index=False)

    config = {
        "mouse_mp_csv": args.mouse_mp_csv,
        "outdir": str(outdir),
        "model": args.model,
        "seed": args.seed,
        "resume": args.resume,
        "max_terms": args.max_terms,
        "detected_columns": {
            "mp_id_col": mp_id_col,
            "mp_label_col": mp_label_col,
            "mp_definition_col": mp_definition_col,
            "parent_col": parent_col,
            "ancestor_col": ancestor_col,
        },
        "notes": [
            "Classifier is blinded to genotype, gene, SFARI, disease labels, and HPO-matching results.",
            "Freeze 03_mp_term_taxonomy.tsv before downstream reranking to reduce analytic leakage.",
            "Review 05_manual_review_queue.tsv manually before using strict Tier 1 terms in final ASD face-validity ranking.",
        ],
    }
    (outdir / "07_run_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    print(f"Unique MP terms classified: {taxonomy_df.shape[0]}")
    print(f"Strict face-validity terms (Tier 1): {(taxonomy_df['relevance_tier'] == 1).sum()}")
    print(f"Broad support terms (Tier 2): {(taxonomy_df['relevance_tier'] == 2).sum()}")
    print(f"Mechanistic terms (Tier 3): {(taxonomy_df['relevance_tier'] == 3).sum()}")
    print(f"Generic neurological terms (Tier 4): {(taxonomy_df['relevance_tier'] == 4).sum()}")
    print(f"Off-target/uninformative terms (Tier 5): {(taxonomy_df['relevance_tier'] == 5).sum()}")
    print(f"Manual review queue: {review.shape[0]}")
    print(f"Outputs written to: {outdir.resolve()}")


if __name__ == "__main__":
    main()
