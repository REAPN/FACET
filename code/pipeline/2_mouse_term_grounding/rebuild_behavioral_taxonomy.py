#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("rebuild_taxonomy_v4")


V4_CATEGORIES: List[Dict[str, str]] = [
    {
        "name": "sleep_circadian",
        "description": (
            "Disrupted sleep architecture, altered circadian rhythms, or abnormal "
            "rest-activity cycles. Includes: shortened/prolonged sleep duration, "
            "fragmented sleep, altered REM, circadian phase shifts, abnormal locomotor "
            "activity cycles. Relevant for: MDD, Bipolar, PTSD, Sleep Disorders."
        ),
    },
    {
        "name": "appetite_ingestive",
        "description": (
            "Abnormal food intake, body weight change driven by altered appetite, or "
            "feeding behaviour disruptions. Includes: hyperphagia, hypophagia, altered "
            "meal frequency/size, body weight gain/loss FROM feeding changes (not purely "
            "metabolic/endocrine). Relevant for: MDD, EatingDisorders. "
            "EXCLUDE: obesity/weight change due to metabolic or endocrine lesions unless "
            "feeding behaviour itself is altered."
        ),
    },
    {
        "name": "reward_motivation",
        "description": (
            "Altered hedonic value, effort for reward, or approach motivation. Includes: "
            "sucrose/saccharin preference, progressive-ratio effort, place preference, "
            "anhedonia proxies (reduced preference for reward), reduced reward-seeking. "
            "Relevant for: Substance, EatingDisorders, Paraphilic, MDD."
        ),
    },
    {
        "name": "substance_consummatory",
        "description": (
            "Voluntary intake of alcohol, drugs, or rewarding substances; "
            "conditioned place preference to drugs; withdrawal signs; locomotor "
            "sensitisation to drug exposure. Includes: ethanol preference/intake, "
            "operant drug self-administration, nicotine/cocaine sensitisation, "
            "naloxone-precipitated withdrawal. Relevant for: SubstanceAbuse."
        ),
    },
    {
        "name": "mood_despair",
        "description": (
            "Behavioural-despair / passive-coping phenotypes used as depression proxies "
            "in rodent models. Includes: forced-swim immobility, tail-suspension "
            "immobility, behavioural despair, anhedonia indexed by sucrose preference. "
            "Relevant for: MDD. "
            "EXCLUDE: generic inactivity or motor deficits unrelated to affective state."
        ),
    },
    {
        "name": "stress_neuroendocrine",
        "description": (
            "Dysregulation of the HPA axis, stress-hormone profiles, or physiological "
            "stress-reactivity. Includes: elevated/reduced corticosterone or ACTH, "
            "adrenal hypertrophy/atrophy, altered CRH/GR expression, abnormal "
            "stress-induced corticosterone surge. Relevant for: MDD, PTSD, Anxiety."
        ),
    },
    {
        "name": "pain_somatosensory",
        "description": (
            "Altered detection of or response to noxious stimuli. Includes: thermal pain "
            "threshold (hot-plate, Hargreaves), mechanical threshold (von Frey), chemical "
            "pain (formalin), hyperalgesia, allodynia, central sensitisation. "
            "Relevant for: SomaticSymptomDisorder, SexualPainDisorder. "
            "EXCLUDE: pure touch/proprioception or neutral somatosensory if no nociceptive component."
        ),
    },
    {
        "name": "aggression_dominance",
        "description": (
            "Offensive aggression, dominance hierarchy, or territory-related behavioural "
            "changes. Includes: resident-intruder attack latency/frequency, dominance tube "
            "test, territorial urine marking, irritability-aggression. "
            "Relevant for: DisruptiveImpulseControl, PersonalityDisorder."
        ),
    },
    {
        "name": "sexual_mating",
        "description": (
            "Sexual motivation, copulatory behaviour, or mating performance. Includes: "
            "mount frequency/latency, intromission, ejaculation, partner preference, "
            "sexual motivation in partner approach tests, genital morphology/function "
            "directly affecting sexual behaviour. Relevant for: SexualDysfunction, "
            "Paraphilic, GenderDysphoria."
        ),
    },
    {
        "name": "voiding_elimination",
        "description": (
            "Urination, defecation, or bladder/bowel control phenotypes. Includes: "
            "urination frequency/volume, enuresis, fecal pellet count, "
            "bladder capacity/compliance. Relevant for: EliminationDisorder."
        ),
    },
    {
        "name": "psychosis_gating",
        "description": (
            "Sensorimotor gating deficits or salience-dysregulation phenotypes used as "
            "schizophrenia / psychosis proxies. Includes: prepulse inhibition (PPI) "
            "deficits, latent inhibition disruption, enhanced locomotor sensitisation to "
            "amphetamine or MK-801, hyperlocomotion in novel environments, abnormal "
            "startle magnitude unrelated to fear. "
            "Relevant for: SCZ, Bipolar (mania phase), SchizotypalPD. "
            "EXCLUDE: fear-conditioned startle (relevant to Anxiety, not psychosis) and "
            "generic locomotor hyperactivity without pharmacological manipulation context."
        ),
    },
]

V4_CATEGORY_NAMES: List[str] = [c["name"] for c in V4_CATEGORIES]


RECLASSIFY_SCHEMA: Dict[str, Any] = {
    "name": "taxonomy_reclassify",
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
                        "is_psychiatric_behavioral": {"type": "boolean"},
                        "categories": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": V4_CATEGORY_NAMES,
                            },
                        },
                        "rationale": {"type": "string"},
                    },
                    "required": [
                        "mp_id",
                        "is_psychiatric_behavioral",
                        "categories",
                        "rationale",
                    ],
                },
            }
        },
        "required": ["items"],
    },
}


def category_set_hash(categories: List[Dict[str, str]]) -> str:
    blob = json.dumps(
        sorted(
            [{"name": c["name"], "description": c["description"][:200]}
             for c in categories],
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
    for c in V4_CATEGORIES:
        lines.append(f"  {c['name']}:\n     {c['description']}")
    return "\n\n".join(lines)


CATEGORY_BLOCK = _build_category_block()


def _safe(v: Any) -> str:
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    return str(v) if v is not None else ""


def build_prompt(batch: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    developer_prompt = f"""
You are a mouse-phenotype ontologist classifying MP (Mammalian Phenotype)
terms for a CROSS-DISORDER psychiatric-genetics pipeline.

Your job: for each MP term in the batch, decide —
  1. Is it RELEVANT to any cross-disorder psychiatric behavioral domain?
     A term is relevant if a mouse assay capturing it could provide evidence
     for OR against the face validity of a psychiatric disorder model.
     Most metabolic, anatomical, cardiovascular, immune, reproductive-anatomy,
     and developmental morphology terms are NOT behaviorally relevant.
     Be CONSERVATIVE — when in doubt, mark is_psychiatric_behavioral = false.

  2. If yes, which of the 11 categories below apply? (multi-label OK)
     Assign ONLY categories the term DIRECTLY captures. Do NOT assign a
     category because the upstream biology is vaguely related.
     Example: "abnormal HPA axis physiology" → stress_neuroendocrine YES;
              "abnormal adrenal gland morphology" → stress_neuroendocrine NO
              (anatomy, not a behavioral/physiological readout).

Categories:
{CATEGORY_BLOCK}

Rules:
  - is_psychiatric_behavioral = false → categories must be []
  - is_psychiatric_behavioral = true  → categories must have ≥ 1 entry
  - Keep rationale concise (1 sentence max)
  - Use MP ontology context only; ignore gene names or disease associations

Output JSON matching the strict schema.
""".strip()

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
        f"Classify the following {len(batch)} MP terms:\n\n"
        + "\n\n".join(lines)
    )
    return [
        {"role": "developer", "content": developer_prompt},
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
            RateLimitError,
            APITimeoutError,
            APIConnectionError,
            InternalServerError,
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
            sleep_s = min(max_backoff,
                          base_backoff * (2 ** attempt))
            sleep_s = sleep_s * (0.5 + 0.5 * random.random())
            log.warning(
                "  LLM transient error (attempt %d/%d): %s — sleeping %.1fs",
                attempt + 1, max_attempts,
                type(exc).__name__, sleep_s,
            )
            time.sleep(sleep_s)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("call_llm exhausted retries without an exception "
                       "object — should be unreachable")


def safe_write_tsv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    df.to_csv(tmp, sep="\t", index=False)
    tmp.replace(path)
    log.info("Wrote %s (%d rows, %d cols)", path, len(df), len(df.columns))


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Reclassify dump-bucket MP terms into v4 psychiatric categories."
    )
    ap.add_argument(
        "--taxonomy_in",
        default="mp_term_taxonomy_broad_v3/03_mp_term_taxonomy.tsv",
        help="Input v3 taxonomy TSV.",
    )
    ap.add_argument(
        "--outdir",
        default="mp_term_taxonomy_broad_v4",
        help="Output directory for v4 taxonomy.",
    )
    ap.add_argument(
        "--cache_dir",
        default=None,
        help="Cache directory for LLM batch responses. "
             "Default: <outdir>/cache/",
    )
    ap.add_argument(
        "--batch_size",
        type=int,
        default=15,
        help="MP terms per LLM call (default 15).",
    )
    ap.add_argument(
        "--max_terms",
        type=int,
        default=None,
        help="Cap on dump-bucket terms to process. REQUIRES --dry_run. "
             "Without --dry_run, unprocessed dump-bucket rows would be "
             "silently dropped from the output v4 file.",
    )
    ap.add_argument(
        "--model",
        default=None,
        help="OpenAI model. Defaults to env OPENAI_MODEL or gpt-5.4-mini.",
    )
    ap.add_argument(
        "--seed",
        type=int,
        default=1,
    )
    ap.add_argument(
        "--dry_run",
        action="store_true",
        help="Process but do NOT write the output TSV. Required with --max_terms.",
    )
    ap.add_argument(
        "--force_recache",
        action="store_true",
        help="Ignore existing cache and re-call the API for all batches.",
    )
    args = ap.parse_args()

    if args.max_terms and not args.dry_run:
        ap.error(
            "--max_terms requires --dry_run. Without --dry_run the output v4 TSV "
            "would contain only the capped subset of dump-bucket rows, silently "
            "dropping the rest. Use --dry_run for testing, or omit --max_terms "
            "for a full production run."
        )

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
    log.info("Loading v3 taxonomy: %s", tax_path)
    tax = pd.read_csv(tax_path, sep="\t", low_memory=False)
    log.info("v3 taxonomy: %d rows", len(tax))

    is_dump = tax["primary_domain"] == "non_neurological_or_other"
    dump_df = tax[is_dump].copy().reset_index(drop=True)
    other_df = tax[~is_dump].copy().reset_index(drop=True)
    log.info("Dump bucket: %d terms | Already classified: %d terms",
             len(dump_df), len(other_df))

    if not dump_df["mp_id"].is_unique:
        dups = dump_df[dump_df["mp_id"].duplicated(keep=False)]["mp_id"].unique().tolist()
        log.warning(
            "Dump bucket has %d non-unique mp_ids (%s...); "
            "deduplicating (keeping first occurrence).",
            len(dups), dups[:5],
        )
        dump_df = dump_df.drop_duplicates(subset="mp_id", keep="first").reset_index(drop=True)
        log.info("After dedup: %d dump-bucket terms", len(dump_df))

    if args.max_terms:
        dump_df = dump_df.head(args.max_terms)
        log.info("--max_terms %d: processing %d dump-bucket terms",
                 args.max_terms, len(dump_df))

    cat_hash = category_set_hash(V4_CATEGORIES)
    log.info("Category-set hash: %s", cat_hash)
    log.info("Categories (%d): %s", len(V4_CATEGORY_NAMES),
             ", ".join(V4_CATEGORY_NAMES))

    records = dump_df.to_dict(orient="records")
    batches = [
        records[i: i + args.batch_size]
        for i in range(0, len(records), args.batch_size)
    ]
    log.info("Batches: %d (size=%d)", len(batches), args.batch_size)

    results: Dict[str, Dict[str, Any]] = {}
    n_cache_hits = 0
    n_api_calls = 0
    n_errors = 0
    t0 = time.time()

    for i, batch in enumerate(batches, start=1):
        key = batch_cache_key(batch, cat_hash)
        cache_path = cache_dir / f"{key}.json"

        data: Optional[Dict[str, Any]] = None
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
                cache_path.write_text(
                    json.dumps(data, indent=2), encoding="utf-8"
                )
                n_api_calls += 1
            except Exception as exc:
                log.error("LLM call failed on batch %d/%d: %s", i, len(batches), exc)
                n_errors += 1
                for row in batch:
                    results[row["mp_id"]] = {
                        "is_psychiatric_behavioral": False,
                        "categories": [],
                        "rationale": f"LLM_ERROR: {exc}",
                        "_llm_error": True,
                    }
                continue

        for item in data.get("items", []):
            mp_id = item.get("mp_id", "")
            if not mp_id:
                continue
            results[mp_id] = {
                "is_psychiatric_behavioral": bool(item.get("is_psychiatric_behavioral", False)),
                "categories": list(item.get("categories", [])),
                "rationale": str(item.get("rationale", "")),
            }

        if i % 20 == 0 or i == len(batches):
            elapsed = time.time() - t0
            n_accepted = sum(1 for v in results.values() if v["is_psychiatric_behavioral"])
            log.info(
                "progress: batch %d/%d | cache=%d api=%d err=%d | "
                "accepted=%d/%d | %.1fs elapsed",
                i, len(batches), n_cache_hits, n_api_calls, n_errors,
                n_accepted, len(results), elapsed,
            )

    def _v4_label(mp_id: str) -> str:
        r = results.get(mp_id)
        if r is None:
            return "non_behavioral"
        if r.get("_llm_error"):
            return "LLM_ERROR_RETRY"
        if not r["is_psychiatric_behavioral"]:
            return "non_behavioral"
        cats = r["categories"]
        return "|".join(cats) if cats else "non_behavioral"

    dump_df = dump_df.copy()
    dump_df["behavioral_domain_v4"] = dump_df["mp_id"].apply(_v4_label)

    other_df = other_df.copy()
    other_df["behavioral_domain_v4"] = other_df["primary_domain"]

    n_error_rows = (dump_df["behavioral_domain_v4"] == "LLM_ERROR_RETRY").sum()
    if n_error_rows > 0:
        log.warning(
            "%d dump-bucket terms have LLM_ERROR_RETRY label (from %d failed batches). "
            "Re-run the script to retry these batches; they will NOT be written to the "
            "v4 output until resolved.",
            n_error_rows, n_errors,
        )

    total_processed = len(dump_df) if not args.max_terms else args.max_terms
    n_accepted = (
        (dump_df["behavioral_domain_v4"] != "non_behavioral")
        & (dump_df["behavioral_domain_v4"] != "LLM_ERROR_RETRY")
    ).sum()
    log.info(
        "Dump-bucket reclassification: %d/%d accepted as psychiatric-behavioral (%.1f%%)",
        n_accepted, total_processed, 100.0 * n_accepted / max(total_processed, 1),
    )
    if n_accepted > 0:
        from collections import Counter
        cat_counts: Counter = Counter()
        for lbl in dump_df["behavioral_domain_v4"]:
            if lbl != "non_behavioral" and lbl != "LLM_ERROR_RETRY":
                for c in lbl.split("|"):
                    cat_counts[c] += 1
        log.info("Category distribution:")
        for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1]):
            log.info("  %-30s  %d", cat, cnt)

    if args.dry_run:
        log.info("--dry_run: skipping output write.")
        log.info("Sample dump-bucket assignments:")
        preview = dump_df[["mp_id", "mp_label", "behavioral_domain_v4"]].head(20)
        print(preview.to_string(index=False))
        return 0

    if n_error_rows > 0:
        log.error(
            "Refusing to write v4 output: %d terms have LLM_ERROR_RETRY labels "
            "(%d failed batches). Re-run the script to retry. "
            "Use --force_recache if the error was transient.",
            n_error_rows, n_errors,
        )
        return 2

    v4 = pd.concat([dump_df, other_df], ignore_index=True)
    v4 = v4.sort_values("mp_id").reset_index(drop=True)

    out_tsv = outdir / "03_mp_term_taxonomy.tsv"
    safe_write_tsv(v4, out_tsv)

    accepted = dump_df[dump_df["behavioral_domain_v4"] != "non_behavioral"].copy()
    accepted_path = outdir / "04_newly_accepted_behavioral_terms.tsv"
    safe_write_tsv(accepted, accepted_path)

    run_cfg = {
        "script": "rebuild_behavioral_taxonomy.py",
        "taxonomy_in": str(tax_path),
        "model": model,
        "seed": args.seed,
        "batch_size": args.batch_size,
        "category_set_hash": cat_hash,
        "categories": V4_CATEGORY_NAMES,
        "n_dump_bucket_input": len(dump_df),
        "n_newly_accepted": int(n_accepted),
        "n_errors": n_errors,
        "n_api_calls": n_api_calls,
        "n_cache_hits": n_cache_hits,
        "elapsed_seconds": round(time.time() - t0, 1),
    }
    cfg_path = outdir / "99_rebuild_run_config.json"
    cfg_path.write_text(json.dumps(run_cfg, indent=2), encoding="utf-8")
    log.info("Wrote run config: %s", cfg_path)

    log.info("Done. v4 taxonomy at: %s", out_tsv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
