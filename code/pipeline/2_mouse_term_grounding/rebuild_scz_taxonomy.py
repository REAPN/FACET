#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("rebuild_scz_taxonomy")


SCZ_DOMAINS: List[Dict[str, str]] = [
    {
        "name": "salience_dysregulation",
        "is_strict": True,
        "description": (
            "Aberrant salience attribution, sensorimotor-gating deficits, "
            "latent-inhibition failure, dopamine-mediated psychotomimetic "
            "hyper-response. Substrate of DSM-5-TR Criterion A.1 (delusions) "
            "and A.2 (hallucinations). Mouse anchors: prepulse inhibition (PPI) "
            "deficits, latent inhibition disruption, enhanced behavioural "
            "response to amphetamine / MK-801 / PCP, abnormal startle "
            "magnitude unrelated to fear. (Kapur 2003 aberrant-salience; "
            "Swerdlow 2008; Geyer 2001 / Powell 2009 PPI reviews; Weiner 2003 "
            "latent inhibition.) "
            "EXCLUDE: fear-conditioned startle (anxiety, not psychosis); "
            "generic locomotor hyperactivity without pharmacological context "
            "(that is disorganization)."
        ),
    },
    {
        "name": "disorganization",
        "is_strict": True,
        "description": (
            "Disorganized speech AND/OR grossly disorganized or catatonic "
            "behaviour (A.3 + A.4). BIDIRECTIONAL in motor expression: "
            "catatonic immobility (catalepsy, waxy flexibility, stupor) AND "
            "excessive purposeless activity (hyperlocomotion, stereotypy, "
            "frenetic activity) are BOTH analogs of A.4 — use "
            "scz_direction_consistency=bidirectional for these. Mouse "
            "anchors: catalepsy, waxy flexibility bar test, motor stereotypy, "
            "hyperactivity, abnormal grooming behaviour, abnormal vocalization "
            "(USV) when STRUCTURAL/syntactic (A.3 disorganized-speech proxy; "
            "Scattoni 2008). EXCLUDE: pure USV rate without syntactic context; "
            "motor coordination deficits without behavioural disorganization; "
            "repetitive behaviour that is a clear ASD-restricted-repetitive "
            "stereotypy (route to non_neurological_or_other or note in reason)."
        ),
    },
    {
        "name": "negative_symptoms_motivation",
        "is_strict": True,
        "description": (
            "Avolition, blunted affect, diminished motivation / effort, "
            "anhedonia, reduced goal-directed behaviour (A.5 — motivation "
            "pole). Mouse anchors: progressive ratio break-point reduction, "
            "effort-based decision-task deficits, decreased sucrose "
            "preference (anhedonia), reduced nest-building, reduced "
            "self-grooming as amotivational sign. (Carpenter 1988 deficit "
            "syndrome.) Distinguish from social_interaction (A.5 asociality "
            "pole, separate domain). EXCLUDE: depression-specific behavioural-"
            "despair phenotypes (forced-swim immobility) unless used in a "
            "psychosis-model context; pure metabolic weight loss without "
            "motivational component."
        ),
    },
    {
        "name": "social_interaction",
        "is_strict": True,
        "description": (
            "Asociality, social withdrawal, reduced sociability or social "
            "investigation (A.5 — asociality pole). Mouse anchors: "
            "three-chamber sociability with reduced preference for social "
            "partner, decreased social investigation, decreased social novelty "
            "preference, social avoidance after defeat. NOTE: this construct "
            "is ALSO central to ASD (where it is the defining construct). For "
            "SCZ classification, assign social_interaction when the MP is "
            "interpretable as social-withdrawal/asociality; the disorder "
            "discrimination happens downstream, not at the taxonomy step."
        ),
    },
    {
        "name": "cognitive_executive",
        "is_strict": True,
        "description": (
            "Working memory, attention, executive function, set-shifting, "
            "learning, novel-object recognition. DSM-5-TR Associated Features "
            "(not Criterion A but consistently observed in SCZ; MATRICS "
            "framework). Mouse anchors: T-maze and radial-arm working memory, "
            "5-choice serial reaction time, attentional set-shifting, Morris "
            "water maze spatial learning, novel object recognition, "
            "associative learning, fear conditioning (cognitive component "
            "only). (Nuechterlein 2008 MATRICS.) EXCLUDE: pure synaptic / "
            "mechanistic plasticity readouts without behavioural performance "
            "metric (route to mechanistic_neurobiology)."
        ),
    },
    {
        "name": "non_neurological_or_other",
        "is_strict": False,
        "description": (
            "Anatomical / metabolic / cardiovascular / immune / reproductive "
            "/ developmental morphology terms with no nervous-system "
            "phenotype. Default bucket when no SCZ-construct mapping applies. "
            "Examples: abnormal adipose tissue, liver hypoplasia, abnormal "
            "kidney morphology, abnormal hair pigmentation."
        ),
    },
    {
        "name": "mechanistic_neurobiology",
        "is_strict": False,
        "description": (
            "Nervous-system terms at the cellular / molecular / circuit "
            "level WITHOUT a behavioural readout. Examples: abnormal "
            "synaptic plasticity, abnormal NMDA receptor function, abnormal "
            "dopamine receptor density, abnormal neuronal morphology. These "
            "may be relevant to SCZ mechanism but cannot themselves support "
            "face-validity at the behavioural level. allow_strict_scz_face_"
            "validity must be FALSE for this category."
        ),
    },
    {
        "name": "generic_neurological_abnormality",
        "is_strict": False,
        "description": (
            "Generic neurological abnormalities that cannot be cleanly "
            "assigned to a specific SCZ domain — e.g. 'abnormal nervous "
            "system physiology', 'abnormal CNS development', without "
            "specifying a behavioural or anatomical substrate. Catch-all "
            "for unspecified neurological content. allow_strict_scz_face_"
            "validity must be FALSE."
        ),
    },
]

SCZ_DOMAIN_NAMES: List[str] = [c["name"] for c in SCZ_DOMAINS]
SCZ_STRICT_DOMAINS: List[str] = [c["name"] for c in SCZ_DOMAINS if c["is_strict"]]

DIRECTION_ENUM = ["positive", "bidirectional", "negative", "n/a"]


ANCHOR_SET: List[Dict[str, Any]] = [
    {"mp_id": "MP:0003088", "label_hint": "abnormal prepulse inhibition",
     "expected_domain": "salience_dysregulation", "expected_strict": True,
     "expected_direction": "bidirectional"},
    {"mp_id": "MP:0001488", "label_hint": "increased startle reflex",
     "expected_domain": "salience_dysregulation", "expected_strict": True,
     "expected_direction": "positive"},
    {"mp_id": "MP:0030585", "label_hint": "enhanced response to amphetamine",
     "expected_domain": "salience_dysregulation", "expected_strict": True,
     "expected_direction": "positive"},
    {"mp_id": "MP:0006299", "label_hint": "abnormal latent inhibition",
     "expected_domain": "salience_dysregulation", "expected_strict": True,
     "expected_direction": "negative"},
    {"mp_id": "MP:0002822", "label_hint": "catalepsy",
     "expected_domain": "disorganization", "expected_strict": True,
     "expected_direction": "bidirectional"},
    {"mp_id": "MP:0001399", "label_hint": "hyperactivity",
     "expected_domain": "disorganization", "expected_strict": True,
     "expected_direction": "bidirectional"},
    {"mp_id": "MP:0001529", "label_hint": "abnormal vocalization",
     "expected_domain": "disorganization", "expected_strict": True,
     "expected_direction": "bidirectional"},
    {"mp_id": "MP:0001360", "label_hint": "abnormal social investigation",
     "expected_domain": "social_interaction", "expected_strict": True,
     "expected_direction": "negative"},
    {"mp_id": "MP:0008428", "label_hint": "abnormal spatial working memory",
     "expected_domain": "cognitive_executive", "expected_strict": True,
     "expected_direction": "negative"},
    {"mp_id": "MP:0002062", "label_hint": "abnormal associative learning",
     "expected_domain": "cognitive_executive", "expected_strict": True,
     "expected_direction": "negative"},
    {"mp_id": "MP:0001458", "label_hint": "abnormal object recognition memory",
     "expected_domain": "cognitive_executive", "expected_strict": True,
     "expected_direction": "negative"},
    {"mp_id": "MP:0020379", "label_hint": "abnormal sucrose solution preference",
     "expected_domain": "negative_symptoms_motivation", "expected_strict": True,
     "expected_direction": "negative"},
    {"mp_id": "MP:0001442", "label_hint": "decreased grooming behavior",
     "expected_domain": "negative_symptoms_motivation", "expected_strict": True,
     "expected_direction": "positive"},
    {"mp_id": "MP:0000003", "label_hint": "abnormal adipose tissue morphology",
     "expected_domain": "non_neurological_or_other", "expected_strict": False,
     "expected_direction": "n/a"},
    {"mp_id": "MP:0004859", "label_hint": "abnormal synaptic plasticity",
     "expected_domain": "mechanistic_neurobiology", "expected_strict": False,
     "expected_direction": "n/a"},
]


RECLASSIFY_SCHEMA: Dict[str, Any] = {
    "name": "scz_taxonomy_reclassify",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "mp_id": {"type": "string"},
                        "primary_domain": {
                            "type": "string",
                            "enum": SCZ_DOMAIN_NAMES,
                        },
                        "secondary_domain": {
                            "type": "string",
                            "enum": SCZ_DOMAIN_NAMES + [""],
                        },
                        "allow_strict_scz_face_validity": {"type": "boolean"},
                        "allow_broad_support_analysis": {"type": "boolean"},
                        "allow_mechanistic_support_analysis": {"type": "boolean"},
                        "scz_direction_consistency": {
                            "type": "string",
                            "enum": DIRECTION_ENUM,
                        },
                        "confidence": {
                            "type": "number",
                        },
                        "reason": {"type": "string"},
                    },
                    "required": [
                        "mp_id",
                        "primary_domain",
                        "secondary_domain",
                        "allow_strict_scz_face_validity",
                        "allow_broad_support_analysis",
                        "allow_mechanistic_support_analysis",
                        "scz_direction_consistency",
                        "confidence",
                        "reason",
                    ],
                },
            }
        },
        "required": ["items"],
    },
}


def category_set_hash(domains: List[Dict[str, Any]]) -> str:
    blob = json.dumps(
        sorted(
            [{"name": c["name"],
              "is_strict": c["is_strict"],
              "description": c["description"][:200]}
             for c in domains],
            key=lambda x: x["name"],
        ),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def batch_cache_key(batch: List[Dict[str, Any]], cat_hash: str) -> str:
    mp_ids = ",".join(sorted(r["mp_id"] for r in batch))
    s = f"{cat_hash}|{mp_ids}"
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:20]


def _build_category_block() -> str:
    lines = []
    for c in SCZ_DOMAINS:
        tag = "[STRICT]" if c["is_strict"] else "[NON-STRICT]"
        lines.append(f"  {c['name']} {tag}:\n     {c['description']}")
    return "\n\n".join(lines)


CATEGORY_BLOCK = _build_category_block()


def _safe(v: Any) -> str:
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    return str(v) if v is not None else ""


DEVELOPER_PROMPT = f"""
You are a mouse-phenotype ontologist classifying Mammalian Phenotype (MP) ontology
terms for a Schizophrenia (SCZ) face-validity pipeline based on DSM-5-TR Criterion A
and Associated Features (Nuechterlein 2008 MATRICS framework).

For each MP term, assign ONE primary_domain from the 8-value enum below, set the
strict-eligibility flag, and report self-rated confidence. Single-label: pick the
ONE domain the term most directly captures. If a second domain is non-trivially
relevant, record it in secondary_domain (otherwise ""). Do not invent overlap.

DOMAINS:
{CATEGORY_BLOCK}

DECISION RULES:
  1. allow_strict_scz_face_validity = TRUE only when:
     - primary_domain is one of the 5 strict domains, AND
     - the MP captures an organism-level behavioural readout (not pure mechanism), AND
     - it is a direct or close analog of the SCZ symptom (not a remote / weak proxy).
     Examples of TRUE: "impaired prepulse inhibition", "catalepsy", "abnormal
     social investigation", "abnormal spatial working memory", "decreased sucrose
     preference".
     Examples of FALSE despite being neurological: "abnormal synaptic plasticity"
     (mechanistic), "abnormal nervous system development" (too generic), "abnormal
     locomotor activity" without psychosis context (too generic — but call
     "amphetamine-induced hyperlocomotion" TRUE because the pharmacological context
     anchors it to salience_dysregulation).

  2. allow_broad_support_analysis = TRUE for any organism-level behavioural term
     in a strict domain, AND for organism-level terms in non-strict buckets that
     could provide weak / supporting evidence (e.g. generic sleep abnormality
     could weakly support disorganization but isn't strict).

  3. allow_mechanistic_support_analysis = TRUE for mechanistic_neurobiology terms
     and any term where the underlying mechanism is interpretable as SCZ-relevant
     (e.g. dopamine receptor density, NMDA function). FALSE for purely anatomical
     non-neural terms.

  4. scz_direction_consistency:
     - "positive": MP captures only one direction (e.g. "decreased sucrose
       preference" → negative_symptoms_motivation, direction=positive because
       the MP IS the SCZ-consistent phenotype direction)
     - "bidirectional": both directions are SCZ-relevant on the same axis. The
       canonical case is A.4 catatonia: catalepsy (immobility) AND hyperactivity
       (agitation) are both A.4 analogs on opposite poles. Use this flag for any
       MP capturing an axis where SCZ models span both directions.
     - "negative": MP captures the OPPOSITE of the SCZ-relevant direction (e.g.
       "increased social investigation" is the opposite of A.5 asociality; the
       SCZ phenotype is decreased, not increased)
     - "n/a": non-strict buckets or terms without directional content.

  5. CATATONIA HANDLING (load-bearing): MPs capturing motor immobility (catalepsy,
     waxy flexibility, stupor, behavioural arrest, decreased locomotor activity)
     AND MPs capturing motor agitation (hyperactivity, hyperlocomotion, motor
     stereotypy, frenetic activity, increased grooming as stereotypy) are BOTH
     analogs of DSM-5 A.4 "grossly disorganized or catatonic behaviour".
     Assign primary_domain=disorganization AND scz_direction_consistency=
     bidirectional for both poles. Sister-target evidence (catalepsy is a sister
     of hyperactivity along the catatonia axis) should NOT be marked mismatch.

  6. MOUSE-ONLY READOUTS (USV, grooming variants): case-by-case. Ultrasonic
     vocalization (USV) abnormalities CAN map to A.3 disorganized speech proxy
     IF the MP captures structural/syntactic anomaly (e.g. "abnormal vocalization
     syntax"); pure rate abnormalities (e.g. "decreased vocalization") are weaker
     and should be primary_domain=disorganization with allow_strict_scz_face_
     validity=FALSE (broad-support only) unless the MP definition explicitly
     references organization/syntax. Use confidence < 0.8 for borderline USV
     calls so the manual-review trigger catches them.

  7. ASD-CONSTRUCT OVERLAP (social_interaction, repetitive/stereotypy): the
     social_interaction domain is intrinsically shared between ASD and SCZ. For
     this classification step, assign social_interaction whenever the MP captures
     asociality / social withdrawal / reduced sociability, regardless of which
     disorder the term was historically tagged for. The SCZ-vs-ASD disambiguation
     happens downstream (gene-evidence, paradigm overlap), not here. Repetitive /
     restricted MPs that are pure ASD-stereotypy (e.g. "increased marble burying")
     usually do NOT map to SCZ disorganization unless they describe motor
     stereotypy in a catatonia-relevant frame — when in doubt, route to
     non_neurological_or_other with allow_broad_support_analysis=TRUE and a
     reason explaining the ambiguity.

  8. CONFIDENCE: report your true self-rated confidence ∈ [0, 1].
     - 0.95+: textbook anchor (PPI, catalepsy, sucrose preference)
     - 0.80-0.94: clear mapping with one minor edge case
     - 0.70-0.79: defensible but reasonable alternative exists
     - <0.70: genuinely uncertain; manual review will be triggered

  9. REASON: 1 sentence, cite the SCZ construct or paradigm anchor when relevant
     (e.g. "PPI deficit is canonical A.1/A.2 sensorimotor-gating substrate per
     Geyer 2001" or "abnormal kidney morphology has no nervous-system involvement").

Output JSON matching the strict schema.
""".strip()


def build_prompt(batch: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    lines = []
    for r in batch:
        lines.append(
            f"- mp_id: {r['mp_id']}\n"
            f"  label: {_safe(r.get('mp_label'))}\n"
            f"  definition: {_safe(r.get('mp_definition'))}\n"
            f"  parent: {_safe(r.get('parent_label'))}\n"
            f"  ancestor: {_safe(r.get('ancestor_label'))}"
        )
    user_prompt = (
        f"Classify the following {len(batch)} MP terms for SCZ face validity:\n\n"
        + "\n\n".join(lines)
    )
    return [
        {"role": "developer", "content": DEVELOPER_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def call_llm(
    messages: List[Dict[str, str]],
    model: str,
    seed: int,
    max_attempts: int = 5,
    base_backoff: float = 4.0,
    max_backoff: float = 90.0,
) -> Dict[str, Any]:
    import random
    from openai import OpenAI
    try:
        from openai import (
            RateLimitError, APITimeoutError,
            APIConnectionError, InternalServerError,
        )
        TRANSIENT = (RateLimitError, APITimeoutError,
                     APIConnectionError, InternalServerError)
    except ImportError:
        TRANSIENT = (Exception,)

    client = OpenAI()
    last_exc = None
    for attempt in range(max_attempts):
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0,
                seed=seed,
                messages=messages,
                response_format={"type": "json_schema",
                                 "json_schema": RECLASSIFY_SCHEMA},
            )
            return json.loads(response.choices[0].message.content)
        except TRANSIENT as exc:
            last_exc = exc
            if attempt == max_attempts - 1:
                raise
            sleep_s = min(max_backoff, base_backoff * (2 ** attempt))
            sleep_s = sleep_s * (0.5 + 0.5 * random.random())
            log.warning(
                "  LLM transient error (attempt %d/%d): %s — sleeping %.1fs",
                attempt + 1, max_attempts, type(exc).__name__, sleep_s,
            )
            time.sleep(sleep_s)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("call_llm exhausted retries without an exception object")


def safe_write_tsv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    df.to_csv(tmp, sep="\t", index=False)
    tmp.replace(path)
    log.info("Wrote %s (%d rows, %d cols)", path, len(df), len(df.columns))


def run_pilot(tax: pd.DataFrame, model: str, seed: int,
              cache_dir: Path, cat_hash: str) -> int:
    anchor_ids = [a["mp_id"] for a in ANCHOR_SET]
    anchor_df = tax[tax["mp_id"].isin(anchor_ids)].copy()
    if len(anchor_df) < len(anchor_ids):
        missing = set(anchor_ids) - set(anchor_df["mp_id"])
        log.warning("Pilot anchors missing from taxonomy: %s", missing)

    records = anchor_df.to_dict(orient="records")
    log.info("Pilot: classifying %d anchor MPs", len(records))

    batch = records
    key = batch_cache_key(batch, cat_hash)
    cache_path = cache_dir / f"pilot_{key}.json"

    data = None
    if cache_path.exists():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            log.info("Cache hit: %s", cache_path.name)
        except Exception:
            data = None

    if data is None:
        messages = build_prompt(batch)
        log.info("Calling LLM (model=%s, seed=%d) ...", model, seed)
        data = call_llm(messages, model=model, seed=seed)
        cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    results_by_id = {item["mp_id"]: item for item in data.get("items", [])}
    expected_by_id = {a["mp_id"]: a for a in ANCHOR_SET}

    print()
    print("=" * 110)
    print(f"{'MP':<13} {'Hint':<35} {'Expected':<32} {'Predicted':<32} {'Pass'}")
    print("-" * 110)
    n_pass = 0
    n_total = 0
    for mp_id in anchor_ids:
        exp = expected_by_id[mp_id]
        got = results_by_id.get(mp_id)
        if got is None:
            print(f"{mp_id:<13} {exp['label_hint'][:34]:<35} "
                  f"{exp['expected_domain']:<32} {'(missing)':<32} FAIL")
            n_total += 1
            continue
        domain_ok = got["primary_domain"] == exp["expected_domain"]
        strict_ok = bool(got["allow_strict_scz_face_validity"]) == exp["expected_strict"]
        passed = domain_ok and strict_ok
        if passed:
            n_pass += 1
        n_total += 1
        exp_str = f"{exp['expected_domain']}/{'T' if exp['expected_strict'] else 'F'}"
        got_str = (f"{got['primary_domain']}/"
                   f"{'T' if got['allow_strict_scz_face_validity'] else 'F'} "
                   f"(c={got['confidence']:.2f})")
        print(f"{mp_id:<13} {exp['label_hint'][:34]:<35} "
              f"{exp_str:<32} {got_str:<32} {'PASS' if passed else 'FAIL'}")
    print("-" * 110)
    print(f"Pilot result: {n_pass}/{n_total} anchors pass.")
    print()
    if n_pass >= 12:
        print("PASS THRESHOLD MET (>=12/15). You may proceed to full corpus by")
        print("re-running this script without --pilot.")
    else:
        print(f"PASS THRESHOLD NOT MET ({n_pass} < 12). Inspect the FAIL rows above.")
        print("Common causes: prompt phrasing on edge cases (USV, hyperactivity-as-A.4),")
        print("MP-definition wording that misleads the LLM. Iterate the prompt or surface")
        print("to the supervising researcher before committing the $1.50 full-corpus spend.")
    print()
    print("Per-anchor LLM rationale (for inspection):")
    for mp_id in anchor_ids:
        got = results_by_id.get(mp_id)
        if got:
            print(f"  [{mp_id}] {got['reason']}")
    print("=" * 110)
    return 0 if n_pass >= 12 else 3


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Reclassify all MP terms into the SCZ strict-domain set. "
            "Fork of rebuild_behavioral_taxonomy.py."
        )
    )
    ap.add_argument(
        "--taxonomy_in",
        default="mp_term_taxonomy_broad_v3/03_mp_term_taxonomy.tsv",
        help="Input taxonomy TSV (v3 or v4). Default: v3.",
    )
    ap.add_argument(
        "--outdir", default="mp_term_taxonomy_scz_v1",
        help="Output directory. Default: mp_term_taxonomy_scz_v1.",
    )
    ap.add_argument(
        "--cache_dir", default=None,
        help="Cache directory. Default: <outdir>/cache/",
    )
    ap.add_argument("--batch_size", type=int, default=15,
                    help="MP terms per LLM call (default 15).")
    ap.add_argument(
        "--max_terms", type=int, default=None,
        help="Cap on terms to process. REQUIRES --dry_run.",
    )
    ap.add_argument(
        "--model", default=None,
        help="OpenAI model. Defaults to env OPENAI_MODEL or gpt-5.4-mini.",
    )
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument(
        "--dry_run", action="store_true",
        help="Process but do NOT write the output TSV.",
    )
    ap.add_argument(
        "--force_recache", action="store_true",
        help="Ignore existing cache and re-call the API for all batches.",
    )
    ap.add_argument(
        "--pilot", action="store_true",
        help="Run only the 15 anchor MPs + print pass/fail table. "
             "Does not write the full taxonomy. Use BEFORE the full run.",
    )
    ap.add_argument(
        "--confidence_threshold", type=float, default=0.7,
        help="Below this confidence, set needs_manual_review=True. Default 0.7.",
    )
    args = ap.parse_args()

    if args.max_terms and not args.dry_run and not args.pilot:
        ap.error("--max_terms requires --dry_run (or use --pilot).")

    outdir = Path(args.outdir)
    cache_dir = Path(args.cache_dir) if args.cache_dir else outdir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    outdir.mkdir(parents=True, exist_ok=True)

    model = args.model or os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")
    log.info("Model: %s | seed: %d | batch_size: %d",
             model, args.seed, args.batch_size)

    tax_path = Path(args.taxonomy_in)
    if not tax_path.exists():
        log.error("Taxonomy not found: %s", tax_path)
        return 1
    log.info("Loading input taxonomy: %s", tax_path)
    tax = pd.read_csv(tax_path, sep="\t", low_memory=False)
    log.info("Input taxonomy: %d rows, %d columns", len(tax), len(tax.columns))

    cat_hash = category_set_hash(SCZ_DOMAINS)
    log.info("Category-set hash: %s", cat_hash)
    log.info("Categories (%d, %d strict): %s",
             len(SCZ_DOMAIN_NAMES), len(SCZ_STRICT_DOMAINS),
             ", ".join(SCZ_DOMAIN_NAMES))

    if args.pilot:
        return run_pilot(tax, model=model, seed=args.seed,
                          cache_dir=cache_dir, cat_hash=cat_hash)

    if not tax["mp_id"].is_unique:
        dups = tax[tax["mp_id"].duplicated(keep=False)]["mp_id"].unique().tolist()
        log.warning("Non-unique mp_ids in input (%d); deduping (keep first): %s",
                    len(dups), dups[:5])
        tax = tax.drop_duplicates(subset="mp_id", keep="first").reset_index(drop=True)
        log.info("After dedup: %d rows", len(tax))

    if args.max_terms:
        tax = tax.head(args.max_terms)
        log.info("--max_terms %d: processing %d terms", args.max_terms, len(tax))

    records = tax.to_dict(orient="records")
    batches = [records[i: i + args.batch_size]
               for i in range(0, len(records), args.batch_size)]
    log.info("Batches: %d (size=%d)", len(batches), args.batch_size)

    results: Dict[str, Dict[str, Any]] = {}
    n_cache_hits = 0
    n_api_calls = 0
    n_errors = 0
    t0 = time.time()

    for i, batch in enumerate(batches, start=1):
        key = batch_cache_key(batch, cat_hash)
        cache_path = cache_dir / f"{key}.json"

        data = None
        if not args.force_recache and cache_path.exists():
            try:
                data = json.loads(cache_path.read_text(encoding="utf-8"))
                n_cache_hits += 1
            except Exception as exc:
                log.warning("Cache read failed for %s: %s; re-calling", key, exc)

        if data is None:
            messages = build_prompt(batch)
            try:
                data = call_llm(messages, model=model, seed=args.seed)
                cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                n_api_calls += 1
            except Exception as exc:
                log.error("LLM call failed on batch %d/%d: %s", i, len(batches), exc)
                n_errors += 1
                for row in batch:
                    results[row["mp_id"]] = {
                        "primary_domain": "LLM_ERROR_RETRY",
                        "secondary_domain": "",
                        "allow_strict_scz_face_validity": False,
                        "allow_broad_support_analysis": False,
                        "allow_mechanistic_support_analysis": False,
                        "scz_direction_consistency": "n/a",
                        "confidence": 0.0,
                        "reason": f"LLM_ERROR: {exc}",
                        "_llm_error": True,
                    }
                continue

        for item in data.get("items", []):
            mp_id = item.get("mp_id", "")
            if not mp_id:
                continue
            results[mp_id] = {
                "primary_domain": item.get("primary_domain",
                                            "non_neurological_or_other"),
                "secondary_domain": item.get("secondary_domain", ""),
                "allow_strict_scz_face_validity": bool(item.get(
                    "allow_strict_scz_face_validity", False)),
                "allow_broad_support_analysis": bool(item.get(
                    "allow_broad_support_analysis", False)),
                "allow_mechanistic_support_analysis": bool(item.get(
                    "allow_mechanistic_support_analysis", False)),
                "scz_direction_consistency": item.get(
                    "scz_direction_consistency", "n/a"),
                "confidence": float(item.get("confidence", 0.0)),
                "reason": str(item.get("reason", "")),
            }

        if i % 20 == 0 or i == len(batches):
            elapsed = time.time() - t0
            n_strict = sum(1 for v in results.values()
                            if v.get("allow_strict_scz_face_validity"))
            log.info(
                "progress: batch %d/%d | cache=%d api=%d err=%d | "
                "strict_eligible=%d/%d | %.1fs elapsed",
                i, len(batches), n_cache_hits, n_api_calls, n_errors,
                n_strict, len(results), elapsed,
            )

    out = tax.copy()
    new_cols = {
        "primary_domain": [],
        "secondary_domain": [],
        "allow_strict_scz_face_validity": [],
        "allow_broad_support_analysis": [],
        "allow_mechanistic_support_analysis": [],
        "scz_direction_consistency": [],
        "confidence_scz": [],
        "needs_manual_review_scz": [],
        "reason_scz": [],
    }
    for mp_id in out["mp_id"]:
        r = results.get(mp_id)
        if r is None:
            new_cols["primary_domain"].append("LLM_ERROR_RETRY")
            new_cols["secondary_domain"].append("")
            new_cols["allow_strict_scz_face_validity"].append(False)
            new_cols["allow_broad_support_analysis"].append(False)
            new_cols["allow_mechanistic_support_analysis"].append(False)
            new_cols["scz_direction_consistency"].append("n/a")
            new_cols["confidence_scz"].append(0.0)
            new_cols["needs_manual_review_scz"].append(True)
            new_cols["reason_scz"].append("MISSING_FROM_LLM_OUTPUT")
            continue
        new_cols["primary_domain"].append(r["primary_domain"])
        new_cols["secondary_domain"].append(r["secondary_domain"])
        new_cols["allow_strict_scz_face_validity"].append(
            r["allow_strict_scz_face_validity"])
        new_cols["allow_broad_support_analysis"].append(
            r["allow_broad_support_analysis"])
        new_cols["allow_mechanistic_support_analysis"].append(
            r["allow_mechanistic_support_analysis"])
        new_cols["scz_direction_consistency"].append(
            r["scz_direction_consistency"])
        new_cols["confidence_scz"].append(r["confidence"])
        nmr = (r["confidence"] < args.confidence_threshold
               or r.get("_llm_error", False))
        new_cols["needs_manual_review_scz"].append(nmr)
        new_cols["reason_scz"].append(r["reason"])

    out["primary_domain"] = new_cols["primary_domain"]
    out["secondary_domain"] = new_cols["secondary_domain"]
    out["allow_strict_scz_face_validity"] = new_cols["allow_strict_scz_face_validity"]
    out["allow_broad_support_analysis"] = new_cols["allow_broad_support_analysis"]
    out["allow_mechanistic_support_analysis"] = new_cols["allow_mechanistic_support_analysis"]
    out["scz_direction_consistency"] = new_cols["scz_direction_consistency"]
    out["confidence_scz"] = new_cols["confidence_scz"]
    out["needs_manual_review_scz"] = new_cols["needs_manual_review_scz"]
    out["reason_scz"] = new_cols["reason_scz"]

    n_error_rows = (out["primary_domain"] == "LLM_ERROR_RETRY").sum()
    n_strict = out["allow_strict_scz_face_validity"].sum()
    n_review = out["needs_manual_review_scz"].sum()
    log.info(
        "SCZ classification: %d strict-eligible | %d need manual review | "
        "%d LLM_ERROR_RETRY",
        n_strict, n_review, n_error_rows,
    )
    log.info("primary_domain distribution:")
    for k, v in out["primary_domain"].value_counts().items():
        log.info("  %-35s %d", k, v)

    if args.dry_run:
        log.info("--dry_run: skipping output write.")
        log.info("Sample assignments (first 20):")
        preview = out[["mp_id", "mp_label", "primary_domain",
                        "allow_strict_scz_face_validity",
                        "confidence_scz"]].head(20)
        print(preview.to_string(index=False))
        return 0

    if n_error_rows > 0:
        log.error(
            "Refusing to write SCZ v1 output: %d terms have LLM_ERROR_RETRY. "
            "Re-run to retry. Use --force_recache if errors were transient.",
            n_error_rows,
        )
        return 2

    out_tsv = outdir / "03_mp_term_taxonomy.tsv"
    safe_write_tsv(out, out_tsv)

    strict_df = out[out["allow_strict_scz_face_validity"]].copy()
    strict_path = outdir / "04_strict_eligible_terms.tsv"
    safe_write_tsv(strict_df, strict_path)

    run_cfg = {
        "script": "rebuild_scz_taxonomy.py",
        "taxonomy_in": str(tax_path),
        "model": model,
        "seed": args.seed,
        "batch_size": args.batch_size,
        "category_set_hash": cat_hash,
        "categories": SCZ_DOMAIN_NAMES,
        "strict_categories": SCZ_STRICT_DOMAINS,
        "n_input": len(tax),
        "n_strict_eligible": int(n_strict),
        "n_needs_manual_review": int(n_review),
        "confidence_threshold": args.confidence_threshold,
        "n_errors": n_errors,
        "n_api_calls": n_api_calls,
        "n_cache_hits": n_cache_hits,
        "elapsed_seconds": round(time.time() - t0, 1),
    }
    cfg_path = outdir / "99_rebuild_run_config.json"
    cfg_path.write_text(json.dumps(run_cfg, indent=2), encoding="utf-8")
    log.info("Wrote run config: %s", cfg_path)

    log.info("Done. SCZ taxonomy at: %s", out_tsv)
    log.info("Next step: update scz.disorder.json stage2_candidate_features."
             "taxonomy_tsv pointer, then re-run Stage 2a -> 4.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
