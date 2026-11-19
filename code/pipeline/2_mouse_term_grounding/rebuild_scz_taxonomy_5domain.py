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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("rebuild_scz_taxonomy_5domain")


SCZ_DOMAINS: List[Dict[str, Any]] = [
    {
        "name": "delusions",
        "is_strict": True,
        "description": (
            "DSM-5-TR SCZ Criterion A.1: delusions (fixed false beliefs). "
            "Only assign primary_domain=delusions if a term is a direct "
            "belief readout. The aberrant-salience substrate (PPI, dopamine) "
            "is NOT a delusion analog -> route it to mechanism_substrate."
        ),
    },
    {
        "name": "hallucinations",
        "is_strict": True,
        "description": (
            "DSM-5-TR SCZ Criterion A.2: hallucinations (perception-like "
            "experiences without an external stimulus). Do not route "
            "substrate/gating terms here."
        ),
    },
    {
        "name": "disorganized_speech",
        "is_strict": True,
        "description": (
            "DSM-5-TR SCZ Criterion A.3: disorganized speech (derailment, "
            "incoherence, word salad). The closest candidate proxy is "
            "ultrasonic-vocalization (USV) SYNTAX anomaly (Scattoni 2008), a "
            "remote non-criterion proxy. If an MP captures USV syntax you MAY "
            "set primary_domain=disorganized_speech. "
            "Pure USV rate -> non_neurological_or_other."
        ),
    },
    {
        "name": "catatonic_disorganized_behavior",
        "is_strict": True,
        "description": (
            "DSM-5-TR SCZ Criterion A.4: grossly disorganized or catatonic "
            "behaviour. PARTIALLY MODELLABLE, the most tractable positive-pole "
            "criterion. BIDIRECTIONAL in motor expression: catatonic immobility "
            "(catalepsy, waxy flexibility / bar test, stupor, behavioural "
            "arrest, decreased locomotor activity) AND excessive purposeless "
            "activity (hyperlocomotion, motor stereotypy, frenetic activity) "
            "are BOTH analogs of A.4 -> use scz_direction_consistency="
            "bidirectional. Mouse anchors: catalepsy, waxy flexibility, "
            "immobility, hyperactivity, motor stereotypy. allow_strict_scz_"
            "face_validity=TRUE for organism-level motor analogs. EXCLUDE: "
            "motor-coordination / ataxia deficits without a disorganization "
            "frame (-> non_neurological_or_other); amphetamine-induced "
            "hyperlocomotion when the PHARMACOLOGICAL psychotomimetic context "
            "is the point (-> mechanism_substrate)."
        ),
    },
    {
        "name": "negative_symptoms",
        "is_strict": True,
        "description": (
            "DSM-5-TR SCZ Criterion A.5: negative symptoms. MOST MODELLABLE of "
            "Criterion A. Covers diminished emotional expression AND avolition, "
            "and INCLUDES alogia, anhedonia, and asociality (this domain "
            "ABSORBS the old standalone social_interaction domain: social "
            "withdrawal / reduced sociability IS the A.5 asociality pole). "
            "Mouse anchors: progressive-ratio break-point reduction and "
            "effort-based decision tasks (avolition); decreased sucrose "
            "preference (anhedonia); three-chamber reduced sociability, "
            "decreased social investigation, social withdrawal (asociality); "
            "reduced nest-building; blunted-affect proxies. allow_strict_scz_"
            "face_validity=TRUE for organism-level analogs. EXCLUDE: "
            "depression-specific behavioural-despair (forced-swim immobility) "
            "unless in an explicit psychosis-model frame; INCREASED sociability "
            "(that is the opposite direction -> scz_direction_consistency="
            "negative)."
        ),
    },
    {
        "name": "mechanism_substrate",
        "is_strict": False,
        "description": (
            "NON-STRICT mechanism axis (LOAD-BEARING). The aberrant-salience "
            "ENDOPHENOTYPE substrate of the positive-symptom pole: prepulse "
            "inhibition (PPI), sensorimotor gating, latent inhibition, "
            "psychotomimetic hyper-response (enhanced behavioural response to "
            "amphetamine / MK-801 / PCP), dopamine-mediated behavioural "
            "hyper-response, abnormal startle magnitude unrelated to fear. This "
            "is the dimension SCZ mouse models actually capture and that the "
            "Phenodigm baseline rewards, but it is NOT a DSM-5 diagnostic "
            "criterion (Kapur 2003: salience is substrate, not experience). "
            "allow_strict_scz_face_validity MUST be FALSE for every term here. "
            "This is the single most important routing rule in the redesign: "
            "PPI and sensorimotor gating are endophenotype validity, never face "
            "validity. Set allow_mechanistic_support_analysis=TRUE."
        ),
    },
    {
        "name": "cognitive_associated",
        "is_strict": False,
        "description": (
            "NON-STRICT. Working memory, attention, executive function, "
            "set-shifting, spatial learning, novel-object recognition, "
            "associative learning. These are DSM-5 SCZ ASSOCIATED FEATURES "
            "(MATRICS framework, Nuechterlein 2008), consistently observed but "
            "NOT a Criterion A diagnostic item, so they are NOT face validity "
            "for SCZ. allow_strict_scz_face_validity MUST be FALSE. "
            "allow_broad_support_analysis=TRUE."
        ),
    },
    {
        "name": "mechanistic_neurobiology",
        "is_strict": False,
        "description": (
            "NON-STRICT. Nervous-system terms at the cellular / molecular / "
            "circuit level WITHOUT a behavioural readout: abnormal synaptic "
            "plasticity, abnormal NMDA/dopamine receptor density, abnormal "
            "dopamine LEVEL, abnormal neuronal morphology, abnormal brain wave "
            "pattern. May be SCZ-relevant mechanism but cannot support "
            "behavioural face validity. allow_strict_scz_face_validity MUST be "
            "FALSE. allow_mechanistic_support_analysis=TRUE."
        ),
    },
    {
        "name": "non_neurological_or_other",
        "is_strict": False,
        "description": (
            "NON-STRICT default. Anatomical / metabolic / cardiovascular / "
            "immune / reproductive / developmental morphology with no "
            "nervous-system phenotype (abnormal kidney morphology, abnormal "
            "adipose tissue, liver hypoplasia). Also the home for generic "
            "unspecified neurological terms and pure USV-rate abnormalities. "
            "allow_strict_scz_face_validity MUST be FALSE."
        ),
    },
]

SCZ_DOMAIN_NAMES: List[str] = [c["name"] for c in SCZ_DOMAINS]
SCZ_STRICT_DOMAINS: List[str] = [c["name"] for c in SCZ_DOMAINS if c["is_strict"]]

FORCE_STRICT_FALSE: set = {
    "mechanism_substrate", "cognitive_associated",
    "mechanistic_neurobiology", "non_neurological_or_other",
}

DIRECTION_ENUM = ["positive", "bidirectional", "negative", "n/a"]


ANCHOR_SET: List[Dict[str, Any]] = [
    {"mp_id": "MP:0002822", "label_hint": "catalepsy",
     "expected_domain": "catatonic_disorganized_behavior", "expected_strict": True,
     "expected_direction": "bidirectional"},
    {"mp_id": "MP:0001399", "label_hint": "hyperactivity",
     "expected_domain": "catatonic_disorganized_behavior", "expected_strict": True,
     "expected_direction": "bidirectional"},
    {"mp_id": "MP:0001361", "label_hint": "abnormal social investigation / withdrawal",
     "expected_domain": "negative_symptoms", "expected_strict": True,
     "expected_direction": "negative"},
    {"mp_id": "MP:0009710", "label_hint": "anhedonia / decreased sucrose preference",
     "expected_domain": "negative_symptoms", "expected_strict": True,
     "expected_direction": "positive"},
    {"mp_id": "MP:0021111", "label_hint": "decreased social investigation",
     "expected_domain": "negative_symptoms", "expected_strict": True,
     "expected_direction": "negative"},
    {"mp_id": "MP:0003088", "label_hint": "abnormal prepulse inhibition",
     "expected_domain": "mechanism_substrate", "expected_strict": False,
     "expected_direction": "n/a"},
    {"mp_id": "MP:0002634", "label_hint": "abnormal sensorimotor gating",
     "expected_domain": "mechanism_substrate", "expected_strict": False,
     "expected_direction": "n/a"},
    {"mp_id": "MP:0002635", "label_hint": "reduced sensorimotor gating",
     "expected_domain": "mechanism_substrate", "expected_strict": False,
     "expected_direction": "n/a"},
    {"mp_id": "MP:0008428", "label_hint": "abnormal spatial working memory",
     "expected_domain": "cognitive_associated", "expected_strict": False,
     "expected_direction": "n/a"},
    {"mp_id": "MP:0001463", "label_hint": "abnormal spatial learning",
     "expected_domain": "cognitive_associated", "expected_strict": False,
     "expected_direction": "n/a"},
    {"mp_id": "MP:0001900", "label_hint": "impaired synaptic plasticity",
     "expected_domain": "mechanistic_neurobiology", "expected_strict": False,
     "expected_direction": "n/a"},
    {"mp_id": "MP:0001905", "label_hint": "abnormal dopamine level",
     "expected_domain": "mechanistic_neurobiology", "expected_strict": False,
     "expected_direction": "n/a"},
    {"mp_id": "MP:0002135", "label_hint": "abnormal kidney morphology",
     "expected_domain": "non_neurological_or_other", "expected_strict": False,
     "expected_direction": "n/a"},
]


RECLASSIFY_SCHEMA: Dict[str, Any] = {
    "name": "scz_5domain_taxonomy_reclassify",
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
                        "primary_domain": {"type": "string", "enum": SCZ_DOMAIN_NAMES},
                        "secondary_domain": {"type": "string", "enum": SCZ_DOMAIN_NAMES + [""]},
                        "allow_strict_scz_face_validity": {"type": "boolean"},
                        "allow_broad_support_analysis": {"type": "boolean"},
                        "allow_mechanistic_support_analysis": {"type": "boolean"},
                        "scz_direction_consistency": {"type": "string", "enum": DIRECTION_ENUM},
                        "confidence": {"type": "number"},
                        "reason": {"type": "string"},
                    },
                    "required": [
                        "mp_id", "primary_domain", "secondary_domain",
                        "allow_strict_scz_face_validity",
                        "allow_broad_support_analysis",
                        "allow_mechanistic_support_analysis",
                        "scz_direction_consistency", "confidence", "reason",
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
            [{"name": c["name"], "is_strict": c["is_strict"],
              "description": c["description"][:200]} for c in domains],
            key=lambda x: x["name"],
        ),
        sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def batch_cache_key(batch: List[Dict[str, Any]], cat_hash: str) -> str:
    mp_ids = ",".join(sorted(r["mp_id"] for r in batch))
    return hashlib.sha1(f"{cat_hash}|{mp_ids}".encode("utf-8")).hexdigest()[:20]


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
terms for a CRITERION-STRICT Schizophrenia (SCZ) face-validity pipeline. The scored
face-validity domains are EXACTLY the five DSM-5-TR Criterion A items, one domain
each. Everything that is a mechanism, an endophenotype substrate, or an associated
feature is NON-STRICT and reported off the face-validity axis.

For each MP term assign ONE primary_domain from the 9-value enum below, set the
strict-eligibility flag, and report self-rated confidence. Single-label: pick the ONE
domain the term most directly captures. Record a genuinely-relevant second domain in
secondary_domain, else "".

DOMAINS:
{CATEGORY_BLOCK}

DECISION RULES (criterion-strict; these override any intuition that a mechanism
"supports" a criterion):

  1. JUDGE A.1 TO A.3 ON THE EVIDENCE. Route a term to delusions, hallucinations,
     or disorganized_speech only if it is a direct organism-level readout of that
     criterion, and set allow_strict_scz_face_validity by your own judgment of
     analog quality. Do not force salience or gating terms into them (those go to
     mechanism_substrate).

  2. PPI / SENSORIMOTOR GATING / LATENT INHIBITION / PSYCHOTOMIMETIC RESPONSE ->
     mechanism_substrate, allow_strict_scz_face_validity=FALSE, ALWAYS. This is the
     single most important rule. Prepulse inhibition and sensorimotor gating are the
     aberrant-salience ENDOPHENOTYPE, not a DSM criterion (Kapur 2003). They are
     endophenotype validity, never face validity. Do not route them to any strict
     domain and never mark them strict.

  3. allow_strict_scz_face_validity = TRUE only when ALL hold:
     - primary_domain is catatonic_disorganized_behavior (A.4) or negative_symptoms
       (A.5) -- the only two modellable criteria, AND
     - the MP is an organism-level behavioural readout (not pure mechanism), AND
     - it is a direct / close analog of the criterion (not a remote proxy).
     TRUE examples: "catalepsy", "waxy flexibility", "hyperactivity" (A.4
     bidirectional), "decreased sucrose preference", "abnormal social investigation",
     "progressive ratio break point reduction" (A.5).
     FALSE examples: "abnormal prepulse inhibition" (mechanism_substrate),
     "abnormal spatial working memory" (cognitive_associated), "impaired synaptic
     plasticity" (mechanistic_neurobiology), "abnormal kidney morphology" (other).

  4. NEGATIVE SYMPTOMS ABSORBS ASOCIALITY. Social withdrawal / reduced sociability /
     decreased social investigation is the A.5 asociality pole -> primary_domain=
     negative_symptoms, strict=TRUE (direction=negative because the SCZ-consistent
     phenotype is DECREASED sociability; "increased social investigation" is direction
     =negative meaning opposite of the SCZ direction). There is no longer a standalone
     social_interaction domain.

  5. CATATONIA IS BIDIRECTIONAL (A.4, load-bearing). Motor immobility (catalepsy, waxy
     flexibility, stupor, behavioural arrest, decreased locomotor activity) AND motor
     agitation (hyperactivity, hyperlocomotion, motor stereotypy) are BOTH A.4 analogs.
     Assign primary_domain=catatonic_disorganized_behavior with scz_direction_
     consistency=bidirectional for both poles. BUT amphetamine / MK-801 / PCP-induced
     hyperlocomotion, where the pharmacological psychotomimetic context is the point,
     is mechanism_substrate, not A.4.

  6. COGNITION IS AN ASSOCIATED FEATURE, NOT A CRITERION (for SCZ). Working memory,
     attention, set-shifting, spatial learning, novel-object recognition ->
     cognitive_associated, strict=FALSE. (This differs from disorders where cognition
     IS a criterion; here it is not.)

  7. USV / mouse-only readouts: USV syntax anomaly MAY route to disorganized_speech
     but strict=FALSE (remote proxy). Pure USV rate -> non_neurological_or_other.

  8. scz_direction_consistency: "positive" = MP is itself the SCZ-consistent direction;
     "bidirectional" = both poles SCZ-relevant (A.4 catatonia); "negative" = MP is the
     OPPOSITE of the SCZ direction; "n/a" = non-strict buckets / no directional content.

  9. CONFIDENCE in [0,1]: 0.95+ textbook anchor; 0.80-0.94 clear with one edge case;
     0.70-0.79 defensible but alternative exists; <0.70 genuinely uncertain (manual
     review triggered).

 10. REASON: 1 sentence citing the criterion or the reason for non-strict routing
     (e.g. "catalepsy is the canonical A.4 catatonia analog" or "PPI is the salience
     endophenotype substrate, mechanism axis not a Criterion A item").

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
        f"Classify the following {len(batch)} MP terms for criterion-strict SCZ "
        f"face validity:\n\n" + "\n\n".join(lines)
    )
    return [
        {"role": "developer", "content": DEVELOPER_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


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
            response = client.chat.completions.create(
                model=model, temperature=0, seed=seed, messages=messages,
                response_format={"type": "json_schema", "json_schema": RECLASSIFY_SCHEMA},
            )
            return json.loads(response.choices[0].message.content)
        except TRANSIENT as exc:
            last_exc = exc
            if attempt == max_attempts - 1:
                raise
            sleep_s = min(max_backoff, base_backoff * (2 ** attempt))
            sleep_s = sleep_s * (0.5 + 0.5 * random.random())
            log.warning("  LLM transient error (attempt %d/%d): %s -- sleeping %.1fs",
                        attempt + 1, max_attempts, type(exc).__name__, sleep_s)
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


def _apply_force_false(primary_domain: str, allow_strict: bool) -> bool:
    if primary_domain in FORCE_STRICT_FALSE:
        return False
    return bool(allow_strict)


def run_pilot(tax, model, seed, cache_dir, cat_hash):
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
    print("=" * 118)
    print(f"{'MP':<13} {'Hint':<40} {'Expected':<34} {'Predicted':<34} {'Pass'}")
    print("-" * 118)
    n_pass = n_total = 0
    for mp_id in anchor_ids:
        exp = expected_by_id[mp_id]
        got = results_by_id.get(mp_id)
        n_total += 1
        if got is None:
            print(f"{mp_id:<13} {exp['label_hint'][:39]:<40} "
                  f"{exp['expected_domain']:<34} {'(missing)':<34} FAIL")
            continue
        strict_got = _apply_force_false(got["primary_domain"],
                                        got["allow_strict_scz_face_validity"])
        domain_ok = got["primary_domain"] == exp["expected_domain"]
        strict_ok = strict_got == exp["expected_strict"]
        passed = domain_ok and strict_ok
        if passed:
            n_pass += 1
        exp_str = f"{exp['expected_domain']}/{'T' if exp['expected_strict'] else 'F'}"
        got_str = (f"{got['primary_domain']}/{'T' if strict_got else 'F'} "
                   f"(c={got['confidence']:.2f})")
        print(f"{mp_id:<13} {exp['label_hint'][:39]:<40} "
              f"{exp_str:<34} {got_str:<34} {'PASS' if passed else 'FAIL'}")
    print("-" * 118)
    print(f"Pilot result: {n_pass}/{n_total} anchors pass.")
    print()
    thr = 11
    if n_pass >= thr:
        print(f"PASS THRESHOLD MET (>={thr}/{n_total}). Re-run without --pilot for the full corpus.")
    else:
        print(f"PASS THRESHOLD NOT MET ({n_pass} < {thr}). Inspect FAIL rows; likely the")
        print("mechanism routing rules (rules 1, 2, 6) need a prompt tweak-spot fix")
        print("before committing the full-corpus spend.")
    print()
    print("Per-anchor LLM rationale:")
    for mp_id in anchor_ids:
        got = results_by_id.get(mp_id)
        if got:
            print(f"  [{mp_id}] {got['reason']}")
    print("=" * 118)
    return 0 if n_pass >= thr else 3


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Reclassify MP terms into the criterion-strict 5-domain SCZ set.")
    ap.add_argument("--taxonomy_in",
                    default="mp_term_taxonomy_broad_v3/03_mp_term_taxonomy.tsv")
    ap.add_argument("--outdir", default="mp_term_taxonomy_scz_5domain_v1")
    ap.add_argument("--cache_dir", default=None)
    ap.add_argument("--batch_size", type=int, default=15)
    ap.add_argument("--max_terms", type=int, default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--dry_run", action="store_true")
    ap.add_argument("--force_recache", action="store_true")
    ap.add_argument("--pilot", action="store_true")
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
    log.info("Loading input taxonomy: %s", tax_path)
    tax = pd.read_csv(tax_path, sep="\t", low_memory=False)
    log.info("Input taxonomy: %d rows, %d columns", len(tax), len(tax.columns))

    cat_hash = category_set_hash(SCZ_DOMAINS)
    log.info("Category-set hash: %s", cat_hash)
    log.info("Categories (%d, %d strict): %s", len(SCZ_DOMAIN_NAMES),
             len(SCZ_STRICT_DOMAINS), ", ".join(SCZ_DOMAIN_NAMES))

    if args.pilot:
        return run_pilot(tax, model=model, seed=args.seed,
                         cache_dir=cache_dir, cat_hash=cat_hash)

    if not tax["mp_id"].is_unique:
        dups = tax[tax["mp_id"].duplicated(keep=False)]["mp_id"].unique().tolist()
        log.warning("Non-unique mp_ids (%d); deduping keep-first: %s", len(dups), dups[:5])
        tax = tax.drop_duplicates(subset="mp_id", keep="first").reset_index(drop=True)

    if args.max_terms:
        tax = tax.head(args.max_terms)
        log.info("--max_terms %d: processing %d terms", args.max_terms, len(tax))

    records = tax.to_dict(orient="records")
    batches = [records[i: i + args.batch_size] for i in range(0, len(records), args.batch_size)]
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
                        "primary_domain": "LLM_ERROR_RETRY", "secondary_domain": "",
                        "allow_strict_scz_face_validity": False,
                        "allow_broad_support_analysis": False,
                        "allow_mechanistic_support_analysis": False,
                        "scz_direction_consistency": "n/a", "confidence": 0.0,
                        "reason": f"LLM_ERROR: {exc}", "_llm_error": True,
                    }
                continue
        for item in data.get("items", []):
            mp_id = item.get("mp_id", "")
            if not mp_id:
                continue
            pd_ = item.get("primary_domain", "non_neurological_or_other")
            results[mp_id] = {
                "primary_domain": pd_,
                "secondary_domain": item.get("secondary_domain", ""),
                "allow_strict_scz_face_validity": _apply_force_false(
                    pd_, item.get("allow_strict_scz_face_validity", False)),
                "allow_broad_support_analysis": bool(item.get("allow_broad_support_analysis", False)),
                "allow_mechanistic_support_analysis": bool(item.get("allow_mechanistic_support_analysis", False)),
                "scz_direction_consistency": item.get("scz_direction_consistency", "n/a"),
                "confidence": float(item.get("confidence", 0.0)),
                "reason": str(item.get("reason", "")),
            }
        if i % 20 == 0 or i == len(batches):
            elapsed = time.time() - t0
            n_strict = sum(1 for v in results.values() if v.get("allow_strict_scz_face_validity"))
            log.info("progress: batch %d/%d | cache=%d api=%d err=%d | strict=%d/%d | %.1fs",
                     i, len(batches), n_cache_hits, n_api_calls, n_errors,
                     n_strict, len(results), elapsed)

    out = tax.copy()
    cols = {k: [] for k in [
        "primary_domain", "secondary_domain", "allow_strict_scz_face_validity",
        "allow_broad_support_analysis", "allow_mechanistic_support_analysis",
        "scz_direction_consistency", "confidence_scz", "needs_manual_review_scz",
        "reason_scz"]}
    for mp_id in out["mp_id"]:
        r = results.get(mp_id)
        if r is None:
            cols["primary_domain"].append("LLM_ERROR_RETRY")
            cols["secondary_domain"].append("")
            cols["allow_strict_scz_face_validity"].append(False)
            cols["allow_broad_support_analysis"].append(False)
            cols["allow_mechanistic_support_analysis"].append(False)
            cols["scz_direction_consistency"].append("n/a")
            cols["confidence_scz"].append(0.0)
            cols["needs_manual_review_scz"].append(True)
            cols["reason_scz"].append("MISSING_FROM_LLM_OUTPUT")
            continue
        cols["primary_domain"].append(r["primary_domain"])
        cols["secondary_domain"].append(r["secondary_domain"])
        cols["allow_strict_scz_face_validity"].append(r["allow_strict_scz_face_validity"])
        cols["allow_broad_support_analysis"].append(r["allow_broad_support_analysis"])
        cols["allow_mechanistic_support_analysis"].append(r["allow_mechanistic_support_analysis"])
        cols["scz_direction_consistency"].append(r["scz_direction_consistency"])
        cols["confidence_scz"].append(r["confidence"])
        nmr = (r["confidence"] < args.confidence_threshold or r.get("_llm_error", False))
        cols["needs_manual_review_scz"].append(nmr)
        cols["reason_scz"].append(r["reason"])

    for k, v in cols.items():
        out[k] = v

    n_error_rows = int((out["primary_domain"] == "LLM_ERROR_RETRY").sum())
    n_strict = int(out["allow_strict_scz_face_validity"].sum())
    n_review = int(out["needs_manual_review_scz"].sum())
    log.info("SCZ 5-domain classification: %d strict-eligible | %d manual-review | %d LLM_ERROR",
             n_strict, n_review, n_error_rows)
    log.info("primary_domain distribution:")
    for k, v in out["primary_domain"].value_counts().items():
        log.info("  %-35s %d", k, v)
    for dom in ["delusions", "hallucinations", "disorganized_speech",
                "catatonic_disorganized_behavior", "negative_symptoms",
                "mechanism_substrate"]:
        sub = out[out["primary_domain"] == dom]
        ns = int(sub["allow_strict_scz_face_validity"].sum())
        log.info("  domain %-32s n=%-5d strict=%d", dom, len(sub), ns)

    if args.dry_run:
        log.info("--dry_run: skipping output write.")
        preview = out[["mp_id", "mp_label", "primary_domain",
                       "allow_strict_scz_face_validity", "confidence_scz"]].head(20)
        print(preview.to_string(index=False))
        return 0

    if n_error_rows > 0:
        log.error("Refusing to write: %d LLM_ERROR_RETRY rows. Re-run to retry.", n_error_rows)
        return 2

    out_tsv = outdir / "03_mp_term_taxonomy.tsv"
    safe_write_tsv(out, out_tsv)
    strict_df = out[out["allow_strict_scz_face_validity"]].copy()
    safe_write_tsv(strict_df, outdir / "04_strict_eligible_terms.tsv")

    run_cfg = {
        "script": "rebuild_scz_taxonomy_5domain.py",
        "taxonomy_in": str(tax_path), "model": model, "seed": args.seed,
        "batch_size": args.batch_size, "category_set_hash": cat_hash,
        "categories": SCZ_DOMAIN_NAMES, "strict_categories": SCZ_STRICT_DOMAINS,
        "force_strict_false_domains": sorted(FORCE_STRICT_FALSE),
        "n_input": len(tax), "n_strict_eligible": n_strict,
        "n_needs_manual_review": n_review,
        "confidence_threshold": args.confidence_threshold,
        "n_errors": n_errors, "n_api_calls": n_api_calls,
        "n_cache_hits": n_cache_hits, "elapsed_seconds": round(time.time() - t0, 1),
    }
    (outdir / "99_rebuild_run_config.json").write_text(
        json.dumps(run_cfg, indent=2), encoding="utf-8")
    log.info("Done. SCZ 5-domain taxonomy at: %s", out_tsv)
    log.info("Next: point scz.disorder.json stage2_candidate_features.taxonomy_tsv at")
    log.info("  %s, then run Stage 1 -> 5.", out_tsv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
