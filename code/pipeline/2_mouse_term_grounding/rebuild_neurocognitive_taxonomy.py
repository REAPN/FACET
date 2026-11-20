#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("rebuild_neurocognitive_taxonomy")


NCD_DOMAINS: List[Dict[str, Any]] = [
    {
        "name": "cognitive_executive",
        "is_strict": True,
        "description": (
            "DSM-5-TR NCD Criterion A cognitive core -- complex attention, executive "
            "function (planning, working memory, set-shifting, response inhibition, "
            "mental flexibility), and learning and memory (free recall, recognition, "
            "recent memory). Consolidates the attention/executive/memory poles into one "
            "domain. Mouse anchors: Morris water maze (incl. reversal), novel object "
            "recognition, working-memory deficits (radial-arm, T-maze delayed alternation), "
            "5-CSRTT attention, attentional set-shifting, go/no-go inhibition, contextual/"
            "associative conditioning deficits. EXCLUDE: pure synaptic/molecular plasticity "
            "readouts without a behavioural performance metric (-> mechanistic_neurobiology); "
            "motor-coordination deficits without a cognitive component (-> motor_coordination)."
        ),
    },
    {
        "name": "motor_coordination",
        "is_strict": True,
        "description": (
            "DSM-5-TR NCD Criterion A5 perceptual-motor function -- coordination, gait, "
            "postural control, praxis, visuospatial navigation, and etiology-specific motor "
            "signs (parkinsonism in Lewy body / Parkinson disease; chorea and motor "
            "disorganization in Huntington disease; gait disorder in vascular / TBI). Mouse "
            "anchors: rotarod, beam walk, gait analysis, pole test, ataxia, tremor, "
            "bradykinesia, postural instability. EXCLUDE: pure muscle/neuromuscular-junction "
            "pathology without a motor-behaviour readout."
        ),
    },
    {
        "name": "social_cognition_empathy",
        "is_strict": True,
        "description": (
            "DSM-5-TR NCD Criterion A6 social cognition -- recognition of others' emotional "
            "states, theory of mind, empathy-like behaviour, and behavioural regulation. Loss "
            "of empathy and social disinhibition are the behavioural-variant frontotemporal "
            "signature. Mouse anchors: observational fear (Jeon 2010 ACC-dependent), "
            "consolation-like behaviour, impaired social recognition / social memory, reduced "
            "reciprocal social novelty preference. NOTE: the social component overlaps with "
            "ASD -- assign on the construct (recognition/empathy processing), NOT gene identity; "
            "NCD-vs-ASD disambiguation happens downstream, not by inflating eligibility here. "
            "Distinguish from generic affiliation/engagement (that is adaptive social "
            "participation): this domain is the cognitive-social-PROCESSING dimension."
        ),
    },
    {
        "name": "adaptive_functioning",
        "is_strict": True,
        "description": (
            "DSM-5-TR NCD Criterion B -- the cognitive deficits get in the way of independence in "
            "everyday life (instrumental activities of daily living). Mouse anchors: "
            "abnormal nest-building (Deacon 2006 ADL proxy), abnormal burrowing, impaired "
            "home-cage self-care / grooming competence (as ADL). Direction is deficit/loss."
        ),
    },
    {
        "name": "neuropathology_progressive",
        "is_strict": True,
        "description": (
            "The etiology-defining PROGRESSIVE neuropathology named by the NCD subtype. This "
            "is a MECHANISTIC/pathology domain that is STRICT-ELIGIBLE for NCD (unlike ID), "
            "because the chapter-16 disorders ARE defined by their accumulating pathology. "
            "Includes: amyloid-beta deposits and plaques, tau protein deposits and "
            "neurofibrillary tangles (Alzheimer); TDP-43 and FTLD pathology (frontotemporal); "
            "alpha-synuclein aggregation and Lewy bodies (Lewy body / Parkinson); vascular "
            "white-matter rarefaction and infarct (vascular); CAG-expansion neurodegeneration "
            "(Huntington); spongiform change (prion); focal neuronal loss (TBI). Direction is "
            "PRESENCE (positive = pathology present). EXCLUDE from THIS domain (route to "
            "mechanistic_neurobiology): generic synaptic plasticity / LTP, neurotransmitter "
            "levels (dopamine, glutamate), dendritic spine density, and other mechanism that is "
            "NOT the disease-defining progressive pathology."
        ),
    },
    {
        "name": "mechanistic_neurobiology",
        "is_strict": False,
        "description": (
            "Nervous-system terms at the cellular / molecular / circuit level WITHOUT a "
            "behavioural readout AND that are NOT the NCD disease-defining progressive "
            "pathology. Examples: abnormal synaptic plasticity, abnormal LTP, abnormal "
            "dopamine level, abnormal dendritic spine density, abnormal neuronal morphology. "
            "May be relevant to NCD mechanism but cannot support behavioural-level face "
            "validity and is not the etiology signature. allow_strict_neurocognitive_face_"
            "validity must be FALSE. (Contrast neuropathology_progressive, which IS strict.)"
        ),
    },
    {
        "name": "non_neurological_or_other",
        "is_strict": False,
        "description": (
            "Anatomical / metabolic / cardiovascular / immune / reproductive / growth / "
            "developmental-morphology terms with no nervous-system behavioural phenotype and "
            "no NCD pathology signature. Default bucket when no NCD mapping applies. Examples: "
            "abnormal adipose tissue morphology, abnormal kidney morphology, abnormal coat "
            "colour. Also the bucket for generic non-specific neurological terms such as "
            "'abnormal brain morphology' or 'abnormal nervous system development' that carry no "
            "specific NCD domain or progressive-pathology content."
        ),
    },
]

NCD_DOMAIN_NAMES: List[str] = [c["name"] for c in NCD_DOMAINS]
NCD_STRICT_DOMAINS: List[str] = [c["name"] for c in NCD_DOMAINS if c["is_strict"]]
DIRECTION_ENUM = ["positive", "bidirectional", "negative", "n/a"]


ANCHOR_SET: List[Dict[str, Any]] = [
    {"mp_id": "MP:0001463", "label_hint": "abnormal spatial learning",
     "expected_domain": "cognitive_executive", "expected_strict": True},
    {"mp_id": "MP:0001458", "label_hint": "abnormal object recognition memory",
     "expected_domain": "cognitive_executive", "expected_strict": True},
    {"mp_id": "MP:0002062", "label_hint": "abnormal associative learning",
     "expected_domain": "cognitive_executive", "expected_strict": True},
    {"mp_id": "MP:0001469", "label_hint": "abnormal contextual conditioning behavior",
     "expected_domain": "cognitive_executive", "expected_strict": True},
    {"mp_id": "MP:0001516", "label_hint": "abnormal motor coordination/balance",
     "expected_domain": "motor_coordination", "expected_strict": True},
    {"mp_id": "MP:0001406", "label_hint": "abnormal gait",
     "expected_domain": "motor_coordination", "expected_strict": True},
    {"mp_id": "MP:0001393", "label_hint": "ataxia",
     "expected_domain": "motor_coordination", "expected_strict": True},
    {"mp_id": "MP:0021112", "label_hint": "impaired social recognition",
     "expected_domain": "social_cognition_empathy", "expected_strict": True},
    {"mp_id": "MP:0020396", "label_hint": "abnormal social recognition",
     "expected_domain": "social_cognition_empathy", "expected_strict": True},
    {"mp_id": "MP:0001447", "label_hint": "abnormal nest building behavior (ADL proxy)",
     "expected_domain": "adaptive_functioning", "expected_strict": True},
    {"mp_id": "MP:0001440", "label_hint": "abnormal grooming behavior (self-care/ADL)",
     "expected_domain": "adaptive_functioning", "expected_strict": True},
    {"mp_id": "MP:0003329", "label_hint": "amyloid beta deposits",
     "expected_domain": "neuropathology_progressive", "expected_strict": True},
    {"mp_id": "MP:0004250", "label_hint": "tau protein deposits",
     "expected_domain": "neuropathology_progressive", "expected_strict": True},
    {"mp_id": "MP:0003214", "label_hint": "neurofibrillary tangles",
     "expected_domain": "neuropathology_progressive", "expected_strict": True},
    {"mp_id": "MP:0001900", "label_hint": "impaired synaptic plasticity (mechanism, NOT etiology pathology)",
     "expected_domain": "mechanistic_neurobiology", "expected_strict": False},
    {"mp_id": "MP:0001905", "label_hint": "abnormal dopamine level (neurotransmitter, NOT progressive pathology)",
     "expected_domain": "mechanistic_neurobiology", "expected_strict": False},
    {"mp_id": "MP:0002135", "label_hint": "abnormal kidney morphology",
     "expected_domain": "non_neurological_or_other", "expected_strict": False},
]


RECLASSIFY_SCHEMA: Dict[str, Any] = {
    "name": "ncd_taxonomy_reclassify",
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
                        "primary_domain": {"type": "string", "enum": NCD_DOMAIN_NAMES},
                        "secondary_domain": {"type": "string", "enum": NCD_DOMAIN_NAMES + [""]},
                        "allow_strict_neurocognitive_face_validity": {"type": "boolean"},
                        "allow_broad_support_analysis": {"type": "boolean"},
                        "allow_mechanistic_support_analysis": {"type": "boolean"},
                        "neurocognitive_direction_consistency": {"type": "string", "enum": DIRECTION_ENUM},
                        "confidence": {"type": "number"},
                        "reason": {"type": "string"},
                    },
                    "required": [
                        "mp_id", "primary_domain", "secondary_domain",
                        "allow_strict_neurocognitive_face_validity", "allow_broad_support_analysis",
                        "allow_mechanistic_support_analysis", "neurocognitive_direction_consistency",
                        "confidence", "reason",
                    ],
                },
            }
        },
        "required": ["items"],
    },
}


def category_set_hash(domains: List[Dict[str, Any]]) -> str:
    blob = json.dumps(
        sorted([{"name": c["name"], "is_strict": c["is_strict"],
                 "description": c["description"][:200]} for c in domains],
               key=lambda x: x["name"]),
        sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def batch_cache_key(batch: List[Dict[str, Any]], cat_hash: str) -> str:
    mp_ids = ",".join(sorted(r["mp_id"] for r in batch))
    return hashlib.sha1(f"{cat_hash}|{mp_ids}".encode("utf-8")).hexdigest()[:20]


def _build_category_block() -> str:
    lines = []
    for c in NCD_DOMAINS:
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
terms for a Neurocognitive Disorder (NCD) face-validity pipeline based on DSM-5-TR
Chapter 16 Major/Mild Neurocognitive Disorder, defined by ACQUIRED cognitive decline
from a previous baseline across six neurocognitive domains, with etiology-specific
progressive neuropathology.

For each MP term, assign ONE primary_domain from the 7-value enum below, set the
strict-eligibility flag, and report self-rated confidence. Single-label: pick the
ONE domain the term most directly captures. If a second domain is non-trivially
relevant, record it in secondary_domain (otherwise ""). Do not invent overlap.

DOMAINS:
{CATEGORY_BLOCK}

DECISION RULES:
  1. allow_strict_neurocognitive_face_validity = TRUE only when:
     - primary_domain is one of the 5 strict NCD domains, AND
     - for the FOUR BEHAVIOURAL domains (cognitive_executive, motor_coordination,
       social_cognition_empathy, adaptive_functioning): the MP captures an
       organism-level behavioural readout (not pure mechanism) that is a direct or
       close analog of the NCD criterion; OR
     - for neuropathology_progressive: the MP is the disease-defining PROGRESSIVE
       pathology of an NCD etiology (amyloid, tau, tangles, alpha-synuclein/Lewy
       body, TDP-43, vascular white-matter injury, CAG degeneration, spongiform
       change, focal neuronal loss). This is the ONE strict domain that is
       mechanistic rather than behavioural.
     TRUE examples: "abnormal spatial learning", "abnormal object recognition memory"
     (-> cognitive_executive); "abnormal gait", "ataxia", "abnormal motor
     coordination/balance" (-> motor_coordination); "impaired social recognition"
     (-> social_cognition_empathy); "abnormal nest building behavior", "abnormal
     grooming behavior" (-> adaptive_functioning); "amyloid beta deposits", "tau
     protein deposits", "neurofibrillary tangles", "neurodegeneration" (->
     neuropathology_progressive).
     FALSE despite being neurological: "impaired synaptic plasticity" / "abnormal
     dopamine level" / "abnormal dendritic spine density" (generic mechanism, NOT the
     disease-defining progressive pathology -> mechanistic_neurobiology); "abnormal
     brain morphology" (too generic -> non_neurological_or_other).

  2. THE LOAD-BEARING NCD BOUNDARY -- neuropathology_progressive vs
     mechanistic_neurobiology. Amyloid/tau/tangle/synuclein/TDP-43/spongiform/CAG-
     degeneration/focal-neuronal-loss are the ETIOLOGY-DEFINING progressive pathology
     of the chapter-16 disorders -> neuropathology_progressive, STRICT, direction
     positive (presence). Synaptic plasticity, LTP, neurotransmitter levels, spine
     density, generic neuronal morphology are MECHANISM that is not itself the disease
     signature -> mechanistic_neurobiology, NON-strict. When uncertain, ask: "is this
     the accumulating pathology that DEFINES an NCD subtype, or an upstream mechanism?"

  3. COGNITIVE vs MOTOR distinction: learning/memory/attention/executive PARADIGMS
     (water maze, NOR, working memory, set-shifting, 5-CSRTT, conditioning) ->
     cognitive_executive. Pure movement/coordination/gait/tremor/ataxia/parkinsonism
     without a cognitive component -> motor_coordination. A perceptual-motor term that
     is really a visuospatial-cognition readout stays cognitive_executive.

  4. SOCIAL COGNITION vs ADAPTIVE SOCIAL: emotion recognition, empathy-like behaviour,
     social recognition/memory, theory-of-mind proxies -> social_cognition_empathy.
     Generic social affiliation/engagement or self-care/daily-living competence ->
     adaptive_functioning. Loss of empathy / social disinhibition is the bvFTD
     signature and belongs to social_cognition_empathy.

  5. NO BIDIRECTIONAL DOMAINS FOR NCD. neurocognitive_direction_consistency:
       - "positive": the MP IS the NCD-consistent direction -- a deficit/impairment/
         decline for the four behavioural domains, or PRESENCE of pathology for
         neuropathology_progressive (e.g. "abnormal spatial learning", "amyloid beta
         deposits", "neurodegeneration").
       - "negative": the MP is the OPPOSITE of the NCD-relevant direction (e.g.
         "enhanced spatial learning", "decreased amyloid beta deposits", "improved
         motor coordination").
       - "n/a": non-strict buckets or terms without directional content.
       - Do NOT use "bidirectional" for NCD.

  6. ACQUIRED-DECLINE / AGE-RELATEDNESS: NCD is defined by decline from a prior
     baseline. Where a term denotes progressive or age-related change, that supports
     NCD relevance, but classify by the DOMAIN of the phenotype (a progressive memory
     deficit is still cognitive_executive; progressive motor decline is still
     motor_coordination). Do not create a separate "progression" domain; progression
     is captured by neuropathology_progressive only when it is pathology.

  7. ASD / SCZ / ID GENE & CONSTRUCT OVERLAP: many NCD genes overlap other disorders.
     Classify on the PHENOTYPE CONSTRUCT, not gene identity or historical disorder
     tag. NCD-vs-ID (degenerative vs developmental) and NCD-vs-ASD disambiguation
     happens downstream, not at this taxonomy step.

  8. allow_broad_support_analysis = TRUE for any organism-level behavioural term in a
     strict behavioural domain, for pathology terms in neuropathology_progressive, AND
     for organism-level terms in non-strict buckets that could provide weak/supporting
     evidence. allow_mechanistic_support_analysis = TRUE for mechanistic_neurobiology
     terms and any term whose mechanism is interpretable as NCD-relevant (dopamine,
     cholinergic, synaptic-plasticity readouts). FALSE for purely anatomical non-neural
     terms.

  9. CONFIDENCE in [0, 1]: 0.95+ textbook anchor (water maze, amyloid deposits,
     nest-building); 0.80-0.94 clear with one edge case; 0.70-0.79 defensible but
     alternative exists; <0.70 genuinely uncertain (manual review triggered).

  10. REASON: 1 sentence; cite the NCD criterion, etiology, or paradigm anchor when
      relevant (e.g. "amyloid beta deposits are the defining Alzheimer pathology ->
      neuropathology_progressive" or "impaired synaptic plasticity is upstream
      mechanism, not the disease-defining accumulating pathology").

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
            f"  ancestor: {_safe(r.get('ancestor_label'))}")
    user_prompt = (f"Classify the following {len(batch)} MP terms for NCD face validity:\n\n"
                   + "\n\n".join(lines))
    return [{"role": "developer", "content": DEVELOPER_PROMPT},
            {"role": "user", "content": user_prompt}]


def call_llm(messages, model, seed, max_attempts=5, base_backoff=4.0, max_backoff=90.0):
    import random
    from openai import OpenAI
    try:
        from openai import (RateLimitError, APITimeoutError,
                            APIConnectionError, InternalServerError)
        TRANSIENT = (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)
    except ImportError:
        TRANSIENT = (Exception,)
    client = OpenAI()
    last_exc = None
    for attempt in range(max_attempts):
        try:
            resp = client.chat.completions.create(
                model=model, temperature=0, seed=seed, messages=messages,
                response_format={"type": "json_schema", "json_schema": RECLASSIFY_SCHEMA})
            return json.loads(resp.choices[0].message.content)
        except TRANSIENT as exc:
            last_exc = exc
            if attempt == max_attempts - 1:
                raise
            sleep_s = min(max_backoff, base_backoff * (2 ** attempt)) * (0.5 + 0.5 * random.random())
            log.warning("  LLM transient error (attempt %d/%d): %s -- sleeping %.1fs",
                        attempt + 1, max_attempts, type(exc).__name__, sleep_s)
            time.sleep(sleep_s)
    if last_exc:
        raise last_exc
    raise RuntimeError("call_llm exhausted retries")


def safe_write_tsv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    df.to_csv(tmp, sep="\t", index=False)
    tmp.replace(path)
    log.info("Wrote %s (%d rows, %d cols)", path, len(df), len(df.columns))


def run_pilot(tax, model, seed, cache_dir, cat_hash, pass_threshold):
    anchor_ids = [a["mp_id"] for a in ANCHOR_SET]
    anchor_df = tax[tax["mp_id"].isin(anchor_ids)].copy()
    if len(anchor_df) < len(anchor_ids):
        missing = set(anchor_ids) - set(anchor_df["mp_id"])
        log.warning("Pilot anchors MISSING from taxonomy (will FAIL): %s", missing)
    records = anchor_df.to_dict(orient="records")
    log.info("Pilot: classifying %d anchor MPs", len(records))
    key = batch_cache_key(records, cat_hash)
    cache_path = cache_dir / f"pilot_{key}.json"
    data = None
    if cache_path.exists():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            log.info("Cache hit: %s", cache_path.name)
        except Exception:
            data = None
    if data is None:
        log.info("Calling LLM (model=%s, seed=%d) ...", model, seed)
        data = call_llm(build_prompt(records), model=model, seed=seed)
        cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    got_by = {it["mp_id"]: it for it in data.get("items", [])}
    exp_by = {a["mp_id"]: a for a in ANCHOR_SET}
    print("\n" + "=" * 120)
    print(f"{'MP':<13} {'Hint':<52} {'Expected':<28} {'Predicted':<28} Pass")
    print("-" * 120)
    n_pass = 0
    for mp_id in anchor_ids:
        exp = exp_by[mp_id]; got = got_by.get(mp_id)
        if got is None:
            print(f"{mp_id:<13} {exp['label_hint'][:51]:<52} "
                  f"{exp['expected_domain']:<28} {'(missing)':<28} FAIL")
            continue
        ok = (got["primary_domain"] == exp["expected_domain"]
              and bool(got["allow_strict_neurocognitive_face_validity"]) == exp["expected_strict"])
        n_pass += int(ok)
        es = f"{exp['expected_domain']}/{'T' if exp['expected_strict'] else 'F'}"
        gs = (f"{got['primary_domain']}/{'T' if got['allow_strict_neurocognitive_face_validity'] else 'F'}"
              f"(c{got['confidence']:.2f})")
        print(f"{mp_id:<13} {exp['label_hint'][:51]:<52} {es:<28} {gs:<28} {'PASS' if ok else 'FAIL'}")
    n_total = len(anchor_ids)
    print("-" * 120)
    print(f"Anchor result: {n_pass}/{n_total} pass.  "
          f"[{n_total}/{n_total} gate: {'MET' if n_pass == n_total else 'NOT MET'}]  "
          f"[>=85% gate: {'MET' if n_pass >= 0.85 * n_total else 'NOT MET'}]")
    print(f"Configured production gate (--pilot_pass_threshold): {pass_threshold}/{n_total} "
          f"-> {'PROCEED' if n_pass >= pass_threshold else 'DO NOT PROCEED'}")
    print()
    print("Per-anchor LLM rationale (adjudicate any FAIL: is the LLM right, or the anchor "
          "expectation wrong? -- cf. SCZ MP:0001529 USV precedent):")
    for mp_id in anchor_ids:
        got = got_by.get(mp_id)
        if got:
            print(f"  [{mp_id}] dir={got['neurocognitive_direction_consistency']:<5} {got['reason']}")
    print("=" * 120)
    return 0 if n_pass >= pass_threshold else 3


def main() -> int:
    ap = argparse.ArgumentParser(description="Reclassify MP terms into the 5-domain NCD strict set.")
    ap.add_argument("--taxonomy_in", default="mp_term_taxonomy_broad_v3/03_mp_term_taxonomy.tsv")
    ap.add_argument("--outdir", default="mp_term_taxonomy_neurocognitive_v1")
    ap.add_argument("--cache_dir", default=None)
    ap.add_argument("--batch_size", type=int, default=15)
    ap.add_argument("--max_terms", type=int, default=None, help="Cap (REQUIRES --dry_run).")
    ap.add_argument("--model", default=None, help="Default env OPENAI_MODEL or gpt-5.4-mini.")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--dry_run", action="store_true")
    ap.add_argument("--force_recache", action="store_true")
    ap.add_argument("--pilot", action="store_true", help="Run 17 anchor MPs + pass/fail; no full write.")
    ap.add_argument("--pilot_pass_threshold", type=int, default=17,
                    help="Anchors required to proceed. Default 17 (strict; all anchors). "
                         "Use 15 for the >=85%% gate.")
    ap.add_argument("--confidence_threshold", type=float, default=0.7)
    args = ap.parse_args()

    if args.max_terms and not args.dry_run and not args.pilot:
        ap.error("--max_terms requires --dry_run (or use --pilot).")

    outdir = Path(args.outdir)
    cache_dir = Path(args.cache_dir) if args.cache_dir else outdir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    outdir.mkdir(parents=True, exist_ok=True)
    model = args.model or os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")
    log.info("Model: %s | seed: %d | batch_size: %d", model, args.seed, args.batch_size)

    tax_path = Path(args.taxonomy_in)
    if not tax_path.exists():
        log.error("Taxonomy not found: %s", tax_path)
        return 1
    tax = pd.read_csv(tax_path, sep="\t", low_memory=False)
    log.info("Input taxonomy: %d rows, %d cols", len(tax), len(tax.columns))

    cat_hash = category_set_hash(NCD_DOMAINS)
    log.info("Category-set hash: %s | categories (%d, %d strict): %s",
             cat_hash, len(NCD_DOMAIN_NAMES), len(NCD_STRICT_DOMAINS), ", ".join(NCD_DOMAIN_NAMES))

    if args.pilot:
        return run_pilot(tax, model, args.seed, cache_dir, cat_hash, args.pilot_pass_threshold)

    if not tax["mp_id"].is_unique:
        tax = tax.drop_duplicates(subset="mp_id", keep="first").reset_index(drop=True)
        log.info("After dedup: %d rows", len(tax))
    if args.max_terms:
        tax = tax.head(args.max_terms)
        log.info("--max_terms %d", len(tax))

    records = tax.to_dict(orient="records")
    batches = [records[i:i + args.batch_size] for i in range(0, len(records), args.batch_size)]
    log.info("Batches: %d (size=%d)", len(batches), args.batch_size)

    results: Dict[str, Dict[str, Any]] = {}
    n_cache_hits = n_api_calls = n_errors = 0
    t0 = time.time()
    for i, batch in enumerate(batches, start=1):
        key = batch_cache_key(batch, cat_hash)
        cache_path = cache_dir / f"{key}.json"
        data = None
        if not args.force_recache and cache_path.exists():
            try:
                data = json.loads(cache_path.read_text(encoding="utf-8"))
                n_cache_hits += 1
            except Exception:
                data = None
        if data is None:
            try:
                data = call_llm(build_prompt(batch), model=model, seed=args.seed)
                cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                n_api_calls += 1
            except Exception as exc:
                log.error("LLM call failed on batch %d/%d: %s", i, len(batches), exc)
                n_errors += 1
                for row in batch:
                    results[row["mp_id"]] = {"primary_domain": "LLM_ERROR_RETRY", "secondary_domain": "",
                        "allow_strict_neurocognitive_face_validity": False, "allow_broad_support_analysis": False,
                        "allow_mechanistic_support_analysis": False, "neurocognitive_direction_consistency": "n/a",
                        "confidence": 0.0, "reason": f"LLM_ERROR: {exc}", "_llm_error": True}
                continue
        def _store(it):
            mid = it.get("mp_id", "")
            if not mid:
                return
            results[mid] = {
                "primary_domain": it.get("primary_domain", "non_neurological_or_other"),
                "secondary_domain": it.get("secondary_domain", ""),
                "allow_strict_neurocognitive_face_validity": bool(it.get("allow_strict_neurocognitive_face_validity", False)),
                "allow_broad_support_analysis": bool(it.get("allow_broad_support_analysis", False)),
                "allow_mechanistic_support_analysis": bool(it.get("allow_mechanistic_support_analysis", False)),
                "neurocognitive_direction_consistency": it.get("neurocognitive_direction_consistency", "n/a"),
                "confidence": float(it.get("confidence", 0.0)),
                "reason": str(it.get("reason", "")),
            }
        for item in data.get("items", []):
            _store(item)
        present = {it.get("mp_id") for it in data.get("items", []) if it.get("mp_id")}
        missing_rows = [r for r in batch if r["mp_id"] not in present]
        if missing_rows:
            log.warning("batch %d/%d: LLM dropped %d item(s) (%s); sub-retrying",
                        i, len(batches), len(missing_rows),
                        ",".join(r["mp_id"] for r in missing_rows))
            queue, tries, recovered = [missing_rows], 0, []
            while queue and tries < 8:
                sub = queue.pop(0); tries += 1
                try:
                    sd = call_llm(build_prompt(sub), model=model, seed=args.seed); n_api_calls += 1
                except Exception as exc:
                    log.warning("  sub-retry call failed: %s", exc); sd = {"items": []}
                got = {it.get("mp_id") for it in sd.get("items", []) if it.get("mp_id")}
                for it in sd.get("items", []):
                    _store(it); recovered.append(it)
                still = [r for r in sub if r["mp_id"] not in got]
                if still and len(sub) > 1:
                    half = len(sub) // 2
                    queue.append(sub[:half]); queue.append(sub[half:])
            if recovered:
                merged = {it.get("mp_id"): it for it in data.get("items", []) if it.get("mp_id")}
                for it in recovered:
                    if it.get("mp_id"):
                        merged[it["mp_id"]] = it
                cache_path.write_text(json.dumps({"items": list(merged.values())}, indent=2),
                                      encoding="utf-8")
        if i % 20 == 0 or i == len(batches):
            n_strict = sum(1 for v in results.values() if v.get("allow_strict_neurocognitive_face_validity"))
            log.info("progress: batch %d/%d | cache=%d api=%d err=%d | strict=%d/%d | %.1fs",
                     i, len(batches), n_cache_hits, n_api_calls, n_errors, n_strict, len(results),
                     time.time() - t0)

    out = tax.copy()
    cols = {k: [] for k in ["primary_domain", "secondary_domain", "allow_strict_neurocognitive_face_validity",
            "allow_broad_support_analysis", "allow_mechanistic_support_analysis",
            "neurocognitive_direction_consistency", "confidence_neurocognitive",
            "needs_manual_review_neurocognitive", "reason_neurocognitive"]}
    for mp_id in out["mp_id"]:
        r = results.get(mp_id)
        if r is None:
            cols["primary_domain"].append("LLM_ERROR_RETRY"); cols["secondary_domain"].append("")
            cols["allow_strict_neurocognitive_face_validity"].append(False); cols["allow_broad_support_analysis"].append(False)
            cols["allow_mechanistic_support_analysis"].append(False); cols["neurocognitive_direction_consistency"].append("n/a")
            cols["confidence_neurocognitive"].append(0.0); cols["needs_manual_review_neurocognitive"].append(True)
            cols["reason_neurocognitive"].append("MISSING_FROM_LLM_OUTPUT"); continue
        cols["primary_domain"].append(r["primary_domain"]); cols["secondary_domain"].append(r["secondary_domain"])
        cols["allow_strict_neurocognitive_face_validity"].append(r["allow_strict_neurocognitive_face_validity"])
        cols["allow_broad_support_analysis"].append(r["allow_broad_support_analysis"])
        cols["allow_mechanistic_support_analysis"].append(r["allow_mechanistic_support_analysis"])
        cols["neurocognitive_direction_consistency"].append(r["neurocognitive_direction_consistency"])
        cols["confidence_neurocognitive"].append(r["confidence"])
        cols["needs_manual_review_neurocognitive"].append(r["confidence"] < args.confidence_threshold or r.get("_llm_error", False))
        cols["reason_neurocognitive"].append(r["reason"])

    for k, v in cols.items():
        out[k] = v

    n_error_rows = int((out["primary_domain"] == "LLM_ERROR_RETRY").sum())
    n_strict = int(out["allow_strict_neurocognitive_face_validity"].sum())
    n_review = int(out["needs_manual_review_neurocognitive"].sum())
    log.info("NCD classification: %d strict-eligible | %d need manual review | %d LLM_ERROR_RETRY",
             n_strict, n_review, n_error_rows)
    log.info("primary_domain distribution:")
    for k, v in out["primary_domain"].value_counts().items():
        log.info("  %-35s %d", k, v)
    log.info("strict-eligible per NCD domain:")
    se = out[out["allow_strict_neurocognitive_face_validity"]]
    for k, v in se["primary_domain"].value_counts().items():
        log.info("  %-35s %d", k, v)

    if args.dry_run:
        log.info("--dry_run: skipping output write.")
        print(out[["mp_id", "mp_label", "primary_domain", "allow_strict_neurocognitive_face_validity",
                   "confidence_neurocognitive"]].head(20).to_string(index=False))
        return 0
    if n_error_rows > 0:
        log.error("Refusing to write: %d LLM_ERROR_RETRY rows. Re-run to retry (cache resumes).", n_error_rows)
        return 2

    safe_write_tsv(out, outdir / "03_mp_term_taxonomy.tsv")
    safe_write_tsv(out[out["allow_strict_neurocognitive_face_validity"]].copy(), outdir / "04_strict_eligible_terms.tsv")
    run_cfg = {"script": "rebuild_neurocognitive_taxonomy.py", "taxonomy_in": str(tax_path), "model": model,
               "seed": args.seed, "batch_size": args.batch_size, "category_set_hash": cat_hash,
               "categories": NCD_DOMAIN_NAMES, "strict_categories": NCD_STRICT_DOMAINS,
               "n_input": len(tax), "n_strict_eligible": n_strict, "n_needs_manual_review": n_review,
               "confidence_threshold": args.confidence_threshold, "n_errors": n_errors,
               "n_api_calls": n_api_calls, "n_cache_hits": n_cache_hits,
               "elapsed_seconds": round(time.time() - t0, 1)}
    (outdir / "99_rebuild_run_config.json").write_text(json.dumps(run_cfg, indent=2), encoding="utf-8")
    log.info("Done. NCD taxonomy at: %s", outdir / "03_mp_term_taxonomy.tsv")
    log.info("Next: neurocognitive.disorder.json taxonomy_tsv pointer already set, "
             "then run Stage 1 -> 2a -> 2b -> 2c -> 3 (via stage3_aggregate.py wrapper) -> 4 -> 5.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
