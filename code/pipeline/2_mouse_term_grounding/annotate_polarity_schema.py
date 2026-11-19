#!/usr/bin/env python3
"""annotate_polarity_schema.py
===========================
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("polarity_annot")


POLARITY_SCHEMA = {
    "name": "polarity_term_schema",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "entity_id": {"type": "string"},
            "domain": {
                "type": "string",
                "enum": [
                    "social_interaction",
                    "communication",
                    "repetitive_restricted",
                    "sensory_reactivity",
                    "developmental_support",
                    "cognitive_behavioral_support",
                    "motor_support",
                    "other",
                ],
            },
            "feature": {"type": "string"},
            "assay_metric": {
                "type": "string",
                "enum": [
                    "latency", "duration", "frequency", "count",
                    "accuracy", "error_rate", "threshold",
                    "preference_score", "intensity",
                    "presence_absence", "other", "unknown",
                ],
            },
            "observed_direction": {
                "type": "string",
                "enum": [
                    "increase", "decrease", "present", "absent",
                    "abnormal_unspecified", "mixed", "unknown",
                ],
            },
            "functional_effect": {
                "type": "string",
                "enum": [
                    "more", "less", "slower", "faster",
                    "hyper", "hypo", "impaired", "enhanced",
                    "abnormal_unspecified", "unknown",
                ],
            },
            "polarity_resolution": {
                "type": "string",
                "enum": ["explicit", "inferred", "coarse", "unknown"],
            },
            "polarity_confidence": {"type": "number"},
            "reasoning": {"type": "string"},
        },
        "required": [
            "entity_id", "domain", "feature", "assay_metric",
            "observed_direction", "functional_effect",
            "polarity_resolution", "polarity_confidence", "reasoning",
        ],
    },
}


DEVELOPER_PROMPT = """\
You annotate a phenotype term's polarity schema for cross-species ASD
face-validity scoring. Use the structured semantic layer:

  measured feature  →  observed direction  →  functional effect

Definitions:
- domain: choose ONE of:
    social_interaction       (DSM-5 ASD core)
    communication             (DSM-5 ASD core)
    repetitive_restricted     (DSM-5 ASD core)
    sensory_reactivity        (DSM-5 ASD core)
    developmental_support     (developmental milestones, growth, onset)
    cognitive_behavioral_support  (broader behavioral / cognitive,
                                   non-ASD-core; e.g. learning, memory,
                                   aggression, fear, anxiety, reflexes,
                                   prepulse inhibition, novelty response)
    motor_support             (motor coordination, gait, hyperactivity,
                                tremor, dystonia, postural)
    other                     (residual)
- feature: short noun phrase for the specific measurable thing
  (e.g., 'social investigation', 'vocalization rate', 'stereotypy
  frequency', 'startle reflex amplitude').
- assay_metric: how this is typically measured. Choose from:
    latency, duration, frequency, count, accuracy, error_rate,
    threshold, preference_score, intensity, presence_absence, other,
    unknown.
- observed_direction: the literal direction stated in the source text.
  'abnormal_unspecified' if the source says only "abnormal" or "altered"
  with no direction.
- functional_effect: the BIOLOGICALLY interpreted direction after applying
  the metric. Use this guide:
    latency × increase     → slower
    latency × decrease     → faster
    duration × increase    → more
    duration × decrease    → less
    frequency × increase   → more
    frequency × decrease   → less
    threshold × increase   → hypo (less responsive)
    threshold × decrease   → hyper (more responsive)
    accuracy × increase    → enhanced
    accuracy × decrease    → impaired
    error_rate × increase  → impaired
    error_rate × decrease  → enhanced
    preference_score × increase → more (preference)
    preference_score × decrease → less (preference)
    presence_absence × present → present
    presence_absence × absent  → absent
- polarity_resolution:
    explicit:  the source text DIRECTLY states the direction
    inferred:  direction is implied by metric semantics or definition
    coarse:    only "abnormal/altered/aberrant" — direction unknown
    unknown:   cannot determine
- polarity_confidence: 0.0 to 1.0 (your confidence in this annotation)
- reasoning: 1-2 sentences explaining your decisions

SPECIAL RULES (apply in order):
1. NEGATION INVERSION: 'failure of', 'lack of', 'inability to',
   'no decrease in', 'no increase in' invert the implied direction.
   Example: 'failure of habituation' → observed_direction=absent,
   functional_effect=more (persistent response).
2. CONVENTION: stereotypy/repetitive motor terms (spinning, head tossing,
   stereotypic behavior) without modifier → observed_direction=
   abnormal_unspecified, but feature='stereotypy', and functional_effect=
   abnormal_unspecified UNLESS modifier present.
3. SENSORY DOMAIN BOTH-DIRECTIONS: in sensory_reactivity, BOTH hyper and
   hypo are DSM-5-relevant. Annotate the literal direction as observed
   (do not collapse to bidirectional). Cross-species matching will be
   handled at comparison time.
4. ABNORMAL UMBRELLA: if the term is purely 'abnormal X' with no
   directional modifier in the LABEL and definition, use observed_direction=
   abnormal_unspecified, polarity_resolution=coarse, confidence ≤ 0.5.
5. EXAMPLE: 'increased latency to find food' →
     feature='food-finding behavior', assay_metric='latency',
     observed_direction='increase', functional_effect='slower',
     polarity_resolution='inferred', confidence=0.85.
"""

USER_TEMPLATE = """\
Annotate the polarity schema for this entity.

entity_id:       {entity_id}
entity_type:     {entity_type}
source_text:     {source_text}
"""


def call_llm(client, model: str, entity_id: str, entity_type: str,
             source_text: str, seed: int) -> Dict:
    user = USER_TEMPLATE.format(
        entity_id=entity_id,
        entity_type=entity_type,
        source_text=source_text,
    )
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        seed=seed,
        messages=[
            {"role": "developer", "content": DEVELOPER_PROMPT},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_schema", "json_schema": POLARITY_SCHEMA},
    )
    return json.loads(resp.choices[0].message.content)


def load_hpo_targets(path: Path) -> List[Dict]:
    df = pd.read_csv(path, sep="\t")
    out = []
    for _, r in df.iterrows():
        text = f"{r['hpo_label']}; {r.get('normalized_phenotype', '')}"
        out.append({
            "entity_id": str(r["hpo_id"]),
            "entity_type": "human_target",
            "source_text": text.strip("; "),
        })
    return out


def load_mp_subset(path: Path, include_t2_non_asd_domain: bool = False) -> List[Dict]:
    df = pd.read_csv(path, sep="\t", low_memory=False)
    df["relevance_tier"] = pd.to_numeric(df["relevance_tier"], errors="coerce")
    asd_domains = {"social_interaction", "communication",
                   "repetitive_restricted", "sensory_reactivity"}
    nonasd_domains = {"cognitive_behavioral_support", "motor_support",
                      "developmental_support"}
    if include_t2_non_asd_domain:
        allowed = asd_domains | nonasd_domains
    else:
        allowed = asd_domains
    sub = df[(df["relevance_tier"].isin([1, 2]))
             & (df["primary_domain"].isin(allowed))]
    n_t1 = int((sub["relevance_tier"] == 1).sum())
    n_t2 = int((sub["relevance_tier"] == 2).sum())
    log.info(
        "MP subset: %d T1 + %d T2 = %d rows (allowed domains: %s)",
        n_t1, n_t2, len(sub), sorted(allowed),
    )
    out = []
    for _, r in sub.iterrows():
        text = f"{r['mp_label']}; {r.get('mp_definition', '')}"
        out.append({
            "entity_id": str(r["mp_id"]),
            "entity_type": "mouse_term",
            "source_text": text.strip("; "),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--hpo_tsv", type=str,
                    default="pilot_hpo_run_hybrid_v3/07_final_resolved_hpo_terms.tsv")
    ap.add_argument("--mp_taxonomy", type=str,
                    default="mp_term_taxonomy_broad_v3/03_mp_term_taxonomy.tsv")
    ap.add_argument("--model", type=str,
                    default=os.environ.get("OPENAI_MODEL", "gpt-5.4"))
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument(
        "--include_t2_non_asd_domain",
        action="store_true",
        help=("Also annotate T2 mouse terms in cognitive_behavioral_support, "
              "motor_support, and developmental_support domains. Required for "
              "the broad-mode benchmark to apply cross_domain_partial=0.4 "
              "weighting uniformly. Adds ~350 entities (~$7 LLM cost)."),
    )
    ap.add_argument(
        "--append_existing",
        action="store_true",
        help=("Read the existing 01_term_annotations.tsv and only annotate "
              "entities not already present. Preserves prior annotations "
              "including any manual overrides applied via "
              "apply_polarity_overrides.py."),
    )
    ap.add_argument("--outdir", type=str, default="polarity_schema_v1")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    if OpenAI is None:
        log.error("openai package not importable")
        return 2
    client = OpenAI()

    hpo = load_hpo_targets(Path(args.hpo_tsv))
    log.info("HPO targets: %d", len(hpo))
    mp = load_mp_subset(Path(args.mp_taxonomy),
                        include_t2_non_asd_domain=args.include_t2_non_asd_domain)
    log.info("MP subset: %d", len(mp))
    entities = hpo + mp
    log.info("Total entities considered: %d", len(entities))

    annot_path = outdir / "01_term_annotations.tsv"
    existing_df = None
    existing_ids = set()
    if args.append_existing and annot_path.exists():
        existing_df = pd.read_csv(annot_path, sep="\t")
        existing_ids = set(existing_df["entity_id"].astype(str).tolist())
        log.info("Append mode: %d existing annotations will be preserved",
                 len(existing_ids))
        entities = [e for e in entities if e["entity_id"] not in existing_ids]
        log.info("Entities to ANNOTATE (new only): %d", len(entities))
    else:
        log.info("Total entities to annotate: %d", len(entities))

    raw_path = outdir / "02_llm_raw.jsonl"
    raw_mode = "a" if args.append_existing and raw_path.exists() else "w"
    if raw_mode == "w":
        raw_path.write_text("")

    annotations = []
    for i, ent in enumerate(entities, 1):
        log.info("[%d/%d] %s %s | %s",
                 i, len(entities), ent["entity_type"], ent["entity_id"],
                 ent["source_text"][:80])
        try:
            obj = call_llm(client, args.model,
                           ent["entity_id"], ent["entity_type"],
                           ent["source_text"], args.seed)
        except Exception as e:
            log.warning("call failed for %s: %s", ent["entity_id"], e)
            continue
        with open(raw_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"input": ent, "output": obj}) + "\n")
        obj["entity_type"] = ent["entity_type"]
        obj["source_text"] = ent["source_text"]
        annotations.append(obj)

    log.info("Annotations collected: %d / %d", len(annotations), len(entities))

    cols = ["entity_id", "entity_type", "source_text", "domain", "feature",
            "assay_metric", "observed_direction", "functional_effect",
            "polarity_resolution", "polarity_confidence", "reasoning"]
    df_new = pd.DataFrame(annotations, columns=cols)

    if existing_df is not None:
        df_out = pd.concat([existing_df, df_new], ignore_index=True)
        df_out = df_out.drop_duplicates(subset=["entity_id"], keep="first")
        log.info("Merged: %d existing + %d new = %d total",
                 len(existing_df), len(df_new), len(df_out))
    else:
        df_out = df_new
    df_out.to_csv(annot_path, sep="\t", index=False)
    log.info("Wrote %s (%d rows)", annot_path, len(df_out))

    cfg = {
        "hpo_tsv": args.hpo_tsv,
        "mp_taxonomy": args.mp_taxonomy,
        "model": args.model,
        "seed": args.seed,
        "n_entities": len(entities),
        "n_annotated": len(annotations),
        "elapsed_seconds": round(time.time() - t0, 1),
        "method": (
            "LLM-annotated polarity schema. Rules from polarity_ideas.txt: "
            "measured_feature -> observed_direction -> functional_effect. "
            "Replaces regex polarity for the high-stakes T1+T2 ASD-domain "
            "subset and 48 HPO v3 targets. Outputs are consumed by "
            "aggregate_support_clustered_broad.py --polarity_mode schema."
        ),
    }
    (outdir / "03_run_config.json").write_text(json.dumps(cfg, indent=2))
    log.info("Done in %.1fs", time.time() - t0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
