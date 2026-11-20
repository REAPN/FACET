#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, logging, os, time
from pathlib import Path
from typing import Any, Dict, List
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("rebuild_mdd_taxonomy")

MDD_DOMAINS: List[Dict[str, Any]] = [
    {"name": "depressed_mood", "is_strict": True, "bidir": False,
     "description": ("DSM-5-TR A1 — persistent sad/empty/irritable mood, dysphoric affect, behavioural "
        "despair. Mouse anchors: forced-swim-test (FST) / tail-suspension-test (TST) immobility "
        "('behavioural despair'), chronic-unpredictable-stress depressive profile, social-defeat. "
        "CONSTRUCT-VALIDITY CONTROVERSIAL (FST/TST may index acute stress-coping, not despair; Cryan & "
        "Holmes 2005) — still strict-eligible. EXCLUDE: pure locomotor immobility without despair context.")},
    {"name": "anhedonia", "is_strict": True, "bidir": False,
     "description": ("DSM-5-TR A2 — diminished pleasure / reduced reward responsiveness. Mouse anchors: "
        "decreased sucrose/saccharin preference, ICSS threshold elevation, progressive-ratio break-point "
        "reduction, reduced reward seeking. Direction: the MDD-consistent pole is REDUCED reward "
        "(positive). EXCLUDE: metabolic feeding changes without hedonic component.")},
    {"name": "weight_appetite_change", "is_strict": True, "bidir": True,
     "description": ("DSM-5-TR A3 — BIDIRECTIONAL weight/appetite dysregulation (loss OR gain; "
        "hypophagia OR hyperphagia). Mouse anchors: abnormal food intake, abnormal body weight, "
        "altered feeding. Mark mdd_direction_consistency='bidirectional' (both poles MDD-relevant). "
        "EXCLUDE: diet-induced-obesity / pure metabolic terms with no behavioural/appetite component.")},
    {"name": "sleep_disturbance", "is_strict": True, "bidir": True,
     "description": ("DSM-5-TR A4 — BIDIRECTIONAL sleep architecture abnormality (insomnia OR hypersomnia; "
        "REM fragmentation, decreased REM latency). Mouse anchors: abnormal sleep pattern, abnormal "
        "paradoxical (REM) sleep, sleep-wake cycle abnormality. mdd_direction_consistency='bidirectional'. "
        "EXCLUDE: circadian-locomotor terms better placed in psychomotor unless sleep-specific.")},
    {"name": "psychomotor_change", "is_strict": True, "bidir": True,
     "description": ("DSM-5-TR A5 — BIDIRECTIONAL psychomotor disturbance (agitation OR retardation). Mouse "
        "anchors: increased locomotor activity / hyperactivity (agitation pole) AND decreased locomotor "
        "activity / hypoactivity (retardation pole) — BOTH map here, mdd_direction_consistency="
        "'bidirectional' (like SCZ catatonia). EXCLUDE: motor-coordination deficits (ataxia) without an "
        "activity-level change.")},
    {"name": "fatigue", "is_strict": True, "bidir": False,
     "description": ("DSM-5-TR A6 — fatigue / loss of energy / lethargy; decreased physical effort. Mouse "
        "anchors: decreased grip strength, reduced wheel-running, reduced voluntary locomotion in "
        "chronic-stress models, effort-based-task (progressive-ratio) deficits. Direction: reduced "
        "energy/effort (positive). EXCLUDE: primary neuromuscular weakness without an effort/energy frame.")},
    {"name": "worthlessness_guilt", "is_strict": True, "bidir": False,
     "description": ("DSM-5-TR A7 — worthlessness / excessive guilt; negative self-schema. Mouse anchors "
        "(WEAK / controversial): reduced social dominance / submissive posture after social defeat, "
        "stress-induced passive coping. NEAR-UNMAPPABLE — self-evaluative cognition has no clear mouse "
        "analog; expect very few strict-eligible. EXCLUDE: generic social-subordinate behaviour without a "
        "defeat/negative-self frame.")},
    {"name": "concentration_indecisiveness", "is_strict": True, "bidir": False,
     "description": ("DSM-5-TR A8 — diminished concentration / indecisiveness. Mouse anchors: impaired "
        "attention (5-CSRTT), impaired working memory, reversal-learning / cognitive-flexibility deficits "
        "in chronic-stress models. Direction: impaired (positive). Overlaps with general cognition — "
        "assign here when an attention/concentration/decision frame is present.")},
    {"name": "suicidality", "is_strict": True, "bidir": False,
     "description": ("DSM-5-TR A9 — repeated thoughts about death / suicidal thoughts. Mouse anchors (PROXY / "
        "controversial): learned-helplessness escape-failure (shuttlebox after inescapable shock), "
        "behavioural-helplessness. NEAR-UNMAPPABLE — suicidal ideation is non-modelable; the LH "
        "escape-failure proxy indexes motivational collapse. Expect very few strict-eligible. EXCLUDE: "
        "sensory touch-escape / nociceptive-escape responses (not helplessness).")},
    {"name": "non_neurological_or_other", "is_strict": False, "bidir": False,
     "description": ("Anatomical / metabolic / cardiovascular / immune / reproductive / morphology terms "
        "with no nervous-system behavioural phenotype. Default bucket. NOTE: pure metabolic feeding/weight "
        "terms with NO behavioural/appetite-regulation component go here, not weight_appetite_change.")},
    {"name": "mechanistic_neurobiology", "is_strict": False, "bidir": False,
     "description": ("Nervous-system terms at cellular/molecular/circuit level WITHOUT a behavioural "
        "readout (abnormal synaptic plasticity, monoamine/serotonin/dopamine levels, receptor density, "
        "HPA-axis/corticosterone). May be MDD-mechanism-relevant but not behavioural face validity. "
        "allow_strict_mdd_face_validity must be FALSE.")},
    {"name": "generic_neurological_abnormality", "is_strict": False, "bidir": False,
     "description": ("Generic neurological abnormalities not assignable to a specific MDD domain (abnormal "
        "nervous system development/morphology/physiology without a behavioural substrate). "
        "allow_strict_mdd_face_validity must be FALSE.")},
]
MDD_DOMAIN_NAMES = [c["name"] for c in MDD_DOMAINS]
MDD_STRICT_DOMAINS = [c["name"] for c in MDD_DOMAINS if c["is_strict"]]
DIRECTION_ENUM = ["positive", "bidirectional", "negative", "n/a"]

ANCHOR_SET: List[Dict[str, Any]] = [
    {"mp_id": "MP:0002573", "label_hint": "behavioral despair", "expected_domain": "depressed_mood", "expected_strict": True},
    {"mp_id": "MP:0014414", "label_hint": "increased depression-related behavior", "expected_domain": "depressed_mood", "expected_strict": True},
    {"mp_id": "MP:0020379", "label_hint": "abnormal sucrose solution preference (anhedonia)", "expected_domain": "anhedonia", "expected_strict": True},
    {"mp_id": "MP:0005449", "label_hint": "abnormal food intake (bidirectional)", "expected_domain": "weight_appetite_change", "expected_strict": True},
    {"mp_id": "MP:0001259", "label_hint": "abnormal body weight (bidirectional)", "expected_domain": "weight_appetite_change", "expected_strict": True},
    {"mp_id": "MP:0001501", "label_hint": "abnormal sleep pattern (bidirectional)", "expected_domain": "sleep_disturbance", "expected_strict": True},
    {"mp_id": "MP:0003194", "label_hint": "abnormal frequency of paradoxical (REM) sleep", "expected_domain": "sleep_disturbance", "expected_strict": True},
    {"mp_id": "MP:0001399", "label_hint": "hyperactivity (agitation pole, bidirectional)", "expected_domain": "psychomotor_change", "expected_strict": True},
    {"mp_id": "MP:0001402", "label_hint": "decreased locomotor activity (retardation pole, bidirectional)", "expected_domain": "psychomotor_change", "expected_strict": True},
    {"mp_id": "MP:0010053", "label_hint": "decreased grip strength (fatigue proxy)", "expected_domain": "fatigue", "expected_strict": True},
    {"mp_id": "MP:0014370", "label_hint": "impaired spatial working memory (concentration)", "expected_domain": "concentration_indecisiveness", "expected_strict": True},
    {"mp_id": "MP:0000003", "label_hint": "abnormal adipose tissue morphology", "expected_domain": "non_neurological_or_other", "expected_strict": False},
    {"mp_id": "MP:0004859", "label_hint": "abnormal synaptic plasticity", "expected_domain": "mechanistic_neurobiology", "expected_strict": False},
    {"mp_id": "MP:0001905", "label_hint": "abnormal dopamine level", "expected_domain": "mechanistic_neurobiology", "expected_strict": False},
    {"mp_id": "MP:0003861", "label_hint": "abnormal nervous system development", "expected_domain": "generic_neurological_abnormality", "expected_strict": False},
]

RECLASSIFY_SCHEMA: Dict[str, Any] = {
    "name": "mdd_taxonomy_reclassify", "strict": True,
    "schema": {"type": "object", "additionalProperties": False, "properties": {"items": {"type": "array",
        "items": {"type": "object", "additionalProperties": False, "properties": {
            "mp_id": {"type": "string"},
            "primary_domain": {"type": "string", "enum": MDD_DOMAIN_NAMES},
            "secondary_domain": {"type": "string", "enum": MDD_DOMAIN_NAMES + [""]},
            "allow_strict_mdd_face_validity": {"type": "boolean"},
            "allow_broad_support_analysis": {"type": "boolean"},
            "allow_mechanistic_support_analysis": {"type": "boolean"},
            "mdd_direction_consistency": {"type": "string", "enum": DIRECTION_ENUM},
            "confidence": {"type": "number"}, "reason": {"type": "string"}},
        "required": ["mp_id", "primary_domain", "secondary_domain", "allow_strict_mdd_face_validity",
            "allow_broad_support_analysis", "allow_mechanistic_support_analysis",
            "mdd_direction_consistency", "confidence", "reason"]}}}, "required": ["items"]}}


def category_set_hash(domains):
    blob = json.dumps(sorted([{"name": c["name"], "is_strict": c["is_strict"], "description": c["description"][:200]}
        for c in domains], key=lambda x: x["name"]), sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def batch_cache_key(batch, cat_hash):
    return hashlib.sha1((cat_hash + "|" + ",".join(sorted(r["mp_id"] for r in batch))).encode()).hexdigest()[:20]


def _build_category_block():
    out = []
    for c in MDD_DOMAINS:
        tag = "[STRICT]" if c["is_strict"] else "[NON-STRICT]"
        if c.get("bidir"):
            tag += "[BIDIRECTIONAL]"
        out.append(f"  {c['name']} {tag}:\n     {c['description']}")
    return "\n\n".join(out)


CATEGORY_BLOCK = _build_category_block()


def _safe(v):
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    return str(v) if v is not None else ""


DEVELOPER_PROMPT = f"""
You are a mouse-phenotype ontologist classifying Mammalian Phenotype (MP) ontology
terms for a Major Depressive Disorder (MDD) face-validity pipeline based on DSM-5-TR
Criterion A (the 9 depressive symptoms).

For each MP term assign ONE primary_domain from the 12-value enum, set the
strict-eligibility flag, mark direction, and report confidence. Single-label; record a
non-trivial second domain in secondary_domain else "".

DOMAINS:
{CATEGORY_BLOCK}

DECISION RULES:
  1. allow_strict_mdd_face_validity = TRUE only when primary_domain is one of the 9
     strict MDD domains AND the MP is an organism-level behavioural readout AND a
     direct/close analog of the MDD symptom. FALSE for mechanistic (synaptic
     plasticity, monoamine levels, corticosterone) and generic neurological terms.

  2. BIDIRECTIONAL DOMAINS (load-bearing): weight_appetite_change, sleep_disturbance,
     and psychomotor_change each span BOTH poles. For psychomotor: hyperactivity /
     increased locomotor (agitation) AND hypoactivity / decreased locomotor
     (retardation) BOTH map to psychomotor_change. For weight: gain AND loss. For
     sleep: insomnia AND hypersomnia. Set mdd_direction_consistency='bidirectional'
     for any term on these axes; opposite-pole terms are SISTER evidence, NOT mismatch.

  3. mdd_direction_consistency: 'positive' = the MP IS the MDD-consistent direction
     for a unidirectional domain (e.g. decreased sucrose preference = anhedonia;
     behavioural despair; decreased grip strength = fatigue; impaired working memory).
     'bidirectional' = on a bidirectional axis (rule 2). 'negative' = OPPOSITE of the
     MDD direction for a unidirectional domain (e.g. increased reward seeking; enhanced
     memory). 'n/a' = non-strict buckets.

  4. CONSTRUCT-VALIDITY-CONTROVERSIAL domains. depressed_mood (FST/TST immobility),
     worthlessness_guilt (social-defeat submission), suicidality (learned-helplessness
     escape-failure): these mouse paradigms are debated (acute stress-coping vs
     depressive despair; Cryan & Holmes 2005). Still assign them strict-eligible when
     the construct matches, but use confidence <= 0.8 so borderline calls are flagged.
     worthlessness_guilt and suicidality are NEAR-UNMAPPABLE — assign strict only for a
     genuine learned-helplessness / defeat-submission analog, otherwise route to a
     better domain or non-strict.

  5. METABOLIC vs APPETITE: pure diet-induced / metabolic weight terms with no
     behavioural appetite-regulation component go to non_neurological_or_other, NOT
     weight_appetite_change.

  6. CROSS-DISORDER OVERLAP: many MDD behaviours overlap other disorders (anhedonia
     with SCZ negative symptoms; sleep/appetite with anxiety). Assign on the MDD
     construct; disorder discrimination happens downstream, not here.

  7. CONFIDENCE in [0,1]: 0.95+ textbook anchor (behavioural despair, sucrose
     preference, sleep pattern, locomotor activity); 0.80-0.94 clear; 0.70-0.79
     defensible alternative exists; <0.70 uncertain. REASON: 1 sentence citing the
     MDD criterion/paradigm.

Output JSON matching the strict schema.
""".strip()


def build_prompt(batch):
    lines = [f"- mp_id: {r['mp_id']}\n  label: {_safe(r.get('mp_label'))}\n  definition: {_safe(r.get('mp_definition'))}\n"
             f"  parent: {_safe(r.get('parent_label'))}\n  ancestor: {_safe(r.get('ancestor_label'))}" for r in batch]
    return [{"role": "developer", "content": DEVELOPER_PROMPT},
            {"role": "user", "content": f"Classify the following {len(batch)} MP terms for MDD face validity:\n\n" + "\n\n".join(lines)}]


def call_llm(messages, model, seed, max_attempts=5, base_backoff=4.0, max_backoff=90.0):
    import random
    from openai import OpenAI
    try:
        from openai import RateLimitError, APITimeoutError, APIConnectionError, InternalServerError
        TRANSIENT = (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)
    except ImportError:
        TRANSIENT = (Exception,)
    client = OpenAI(); last = None
    for attempt in range(max_attempts):
        try:
            resp = client.chat.completions.create(model=model, temperature=0, seed=seed, messages=messages,
                response_format={"type": "json_schema", "json_schema": RECLASSIFY_SCHEMA})
            return json.loads(resp.choices[0].message.content)
        except TRANSIENT as exc:
            last = exc
            if attempt == max_attempts - 1:
                raise
            s = min(max_backoff, base_backoff * (2 ** attempt)) * (0.5 + 0.5 * random.random())
            log.warning("  transient %s; sleep %.1fs", type(exc).__name__, s); time.sleep(s)
    raise last


def safe_write_tsv(df, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp"); df.to_csv(tmp, sep="\t", index=False); tmp.replace(path)
    log.info("Wrote %s (%d rows, %d cols)", path, len(df), len(df.columns))


def run_pilot(tax, model, seed, cache_dir, cat_hash, threshold):
    ids = [a["mp_id"] for a in ANCHOR_SET]
    rec = tax[tax["mp_id"].isin(ids)].to_dict(orient="records")
    miss = set(ids) - {r["mp_id"] for r in rec}
    if miss:
        log.warning("anchors missing: %s", miss)
    key = batch_cache_key(rec, cat_hash); cp = cache_dir / f"pilot_{key}.json"
    data = json.loads(cp.read_text()) if cp.exists() else None
    if data is None:
        data = call_llm(build_prompt(rec), model=model, seed=seed); cp.write_text(json.dumps(data, indent=2))
    got = {it["mp_id"]: it for it in data.get("items", [])}; exp = {a["mp_id"]: a for a in ANCHOR_SET}
    print("\n" + "=" * 116)
    n = 0
    for mp in ids:
        e = exp[mp]; g = got.get(mp)
        if not g:
            print(f"{mp:<13} {e['label_hint'][:44]:<46} MISSING FAIL"); continue
        ok = g["primary_domain"] == e["expected_domain"] and bool(g["allow_strict_mdd_face_validity"]) == e["expected_strict"]
        n += int(ok)
        print(f"{mp:<13} {e['label_hint'][:44]:<46} {e['expected_domain']:<26} "
              f"{g['primary_domain']}/{'T' if g['allow_strict_mdd_face_validity'] else 'F'}/{g['mdd_direction_consistency']}(c{g['confidence']:.2f}) {'PASS' if ok else 'FAIL'}")
    print("-" * 116)
    print(f"Anchor result: {n}/{len(ids)}  [15/15 gate: {'MET' if n==len(ids) else 'NOT MET'}]  [>=85%: {'MET' if n>=0.85*len(ids) else 'NOT MET'}]  "
          f"gate {threshold}/{len(ids)} -> {'PROCEED' if n>=threshold else 'DO NOT PROCEED'}")
    print("Per-anchor rationale (adjudicate FAILs):")
    for mp in ids:
        g = got.get(mp)
        if g:
            print(f"  [{mp}] dir={g['mdd_direction_consistency']:<13} {g['reason']}")
    print("=" * 116)
    return 0 if n >= threshold else 3


def main():
    ap = argparse.ArgumentParser(description="Reclassify MP terms into the 9-domain MDD strict set.")
    ap.add_argument("--taxonomy_in", default="mp_term_taxonomy_broad_v3/03_mp_term_taxonomy.tsv")
    ap.add_argument("--outdir", default="mp_term_taxonomy_mdd_v1")
    ap.add_argument("--cache_dir", default=None)
    ap.add_argument("--batch_size", type=int, default=15)
    ap.add_argument("--max_terms", type=int, default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--dry_run", action="store_true")
    ap.add_argument("--force_recache", action="store_true")
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--pilot_pass_threshold", type=int, default=15)
    ap.add_argument("--confidence_threshold", type=float, default=0.7)
    args = ap.parse_args()
    if args.max_terms and not args.dry_run and not args.pilot:
        ap.error("--max_terms requires --dry_run or --pilot.")
    outdir = Path(args.outdir); cache_dir = Path(args.cache_dir) if args.cache_dir else outdir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True); outdir.mkdir(parents=True, exist_ok=True)
    model = args.model or os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")
    log.info("Model %s | seed %d | batch %d", model, args.seed, args.batch_size)
    tax_path = Path(args.taxonomy_in)
    if not tax_path.exists():
        log.error("not found: %s", tax_path); return 1
    tax = pd.read_csv(tax_path, sep="\t", low_memory=False)
    cat_hash = category_set_hash(MDD_DOMAINS)
    log.info("cat hash %s | %d cats (%d strict)", cat_hash, len(MDD_DOMAIN_NAMES), len(MDD_STRICT_DOMAINS))
    if args.pilot:
        return run_pilot(tax, model, args.seed, cache_dir, cat_hash, args.pilot_pass_threshold)
    if not tax["mp_id"].is_unique:
        tax = tax.drop_duplicates(subset="mp_id", keep="first").reset_index(drop=True)
    if args.max_terms:
        tax = tax.head(args.max_terms)
    records = tax.to_dict(orient="records")
    batches = [records[i:i + args.batch_size] for i in range(0, len(records), args.batch_size)]
    log.info("batches %d", len(batches))
    results: Dict[str, Dict[str, Any]] = {}
    n_cache = n_api = n_err = 0; t0 = time.time()
    for i, batch in enumerate(batches, 1):
        cp = cache_dir / f"{batch_cache_key(batch, cat_hash)}.json"
        data = None
        if not args.force_recache and cp.exists():
            try:
                data = json.loads(cp.read_text()); n_cache += 1
            except Exception:
                data = None
        if data is None:
            try:
                data = call_llm(build_prompt(batch), model=model, seed=args.seed); cp.write_text(json.dumps(data, indent=2)); n_api += 1
            except Exception as exc:
                log.error("batch %d failed: %s", i, exc); n_err += 1
                for r in batch:
                    results[r["mp_id"]] = {"primary_domain": "LLM_ERROR_RETRY", "secondary_domain": "",
                        "allow_strict_mdd_face_validity": False, "allow_broad_support_analysis": False,
                        "allow_mechanistic_support_analysis": False, "mdd_direction_consistency": "n/a",
                        "confidence": 0.0, "reason": f"LLM_ERROR: {exc}", "_llm_error": True}
                continue

        def _store(it):
            mid = it.get("mp_id", "")
            if not mid:
                return
            results[mid] = {"primary_domain": it.get("primary_domain", "non_neurological_or_other"),
                "secondary_domain": it.get("secondary_domain", ""),
                "allow_strict_mdd_face_validity": bool(it.get("allow_strict_mdd_face_validity", False)),
                "allow_broad_support_analysis": bool(it.get("allow_broad_support_analysis", False)),
                "allow_mechanistic_support_analysis": bool(it.get("allow_mechanistic_support_analysis", False)),
                "mdd_direction_consistency": it.get("mdd_direction_consistency", "n/a"),
                "confidence": float(it.get("confidence", 0.0)), "reason": str(it.get("reason", ""))}
        for it in data.get("items", []):
            _store(it)
        present = {it.get("mp_id") for it in data.get("items", []) if it.get("mp_id")}
        missing = [r for r in batch if r["mp_id"] not in present]
        if missing:
            log.warning("batch %d dropped %d; sub-retry", i, len(missing))
            queue, tries, rec = [missing], 0, []
            while queue and tries < 8:
                sub = queue.pop(0); tries += 1
                try:
                    sd = call_llm(build_prompt(sub), model=model, seed=args.seed); n_api += 1
                except Exception:
                    sd = {"items": []}
                gotids = {it.get("mp_id") for it in sd.get("items", []) if it.get("mp_id")}
                for it in sd.get("items", []):
                    _store(it); rec.append(it)
                still = [r for r in sub if r["mp_id"] not in gotids]
                if still and len(sub) > 1:
                    h = len(sub) // 2; queue += [sub[:h], sub[h:]]
            if rec:
                merged = {it.get("mp_id"): it for it in data.get("items", []) if it.get("mp_id")}
                for it in rec:
                    if it.get("mp_id"):
                        merged[it["mp_id"]] = it
                cp.write_text(json.dumps({"items": list(merged.values())}, indent=2))
        if i % 20 == 0 or i == len(batches):
            ns = sum(1 for v in results.values() if v.get("allow_strict_mdd_face_validity"))
            log.info("batch %d/%d | cache=%d api=%d err=%d | strict=%d/%d | %.0fs", i, len(batches), n_cache, n_api, n_err, ns, len(results), time.time() - t0)

    out = tax.copy()
    cols = {k: [] for k in ["primary_domain", "secondary_domain", "allow_strict_mdd_face_validity",
        "allow_broad_support_analysis", "allow_mechanistic_support_analysis", "mdd_direction_consistency",
        "confidence_mdd", "needs_manual_review_mdd", "reason_mdd"]}
    for mp in out["mp_id"]:
        r = results.get(mp)
        if r is None:
            for k, v in [("primary_domain", "LLM_ERROR_RETRY"), ("secondary_domain", ""), ("allow_strict_mdd_face_validity", False),
                ("allow_broad_support_analysis", False), ("allow_mechanistic_support_analysis", False),
                ("mdd_direction_consistency", "n/a"), ("confidence_mdd", 0.0), ("needs_manual_review_mdd", True), ("reason_mdd", "MISSING")]:
                cols[k].append(v)
            continue
        cols["primary_domain"].append(r["primary_domain"]); cols["secondary_domain"].append(r["secondary_domain"])
        cols["allow_strict_mdd_face_validity"].append(r["allow_strict_mdd_face_validity"])
        cols["allow_broad_support_analysis"].append(r["allow_broad_support_analysis"])
        cols["allow_mechanistic_support_analysis"].append(r["allow_mechanistic_support_analysis"])
        cols["mdd_direction_consistency"].append(r["mdd_direction_consistency"])
        cols["confidence_mdd"].append(r["confidence"])
        cols["needs_manual_review_mdd"].append(r["confidence"] < args.confidence_threshold or r.get("_llm_error", False))
        cols["reason_mdd"].append(r["reason"])
    for k, v in cols.items():
        out[k] = v
    n_err_rows = int((out["primary_domain"] == "LLM_ERROR_RETRY").sum())
    n_strict = int(out["allow_strict_mdd_face_validity"].sum())
    log.info("MDD: %d strict-eligible | %d review | %d ERROR", n_strict, int(out["needs_manual_review_mdd"].sum()), n_err_rows)
    for k, v in out["primary_domain"].value_counts().items():
        log.info("  %-32s %d", k, v)
    log.info("strict-eligible per MDD domain:")
    for k, v in out[out["allow_strict_mdd_face_validity"]]["primary_domain"].value_counts().items():
        log.info("  %-32s %d", k, v)
    if args.dry_run:
        print(out[["mp_id", "mp_label", "primary_domain", "allow_strict_mdd_face_validity", "mdd_direction_consistency", "confidence_mdd"]].head(20).to_string(index=False)); return 0
    if n_err_rows > 0:
        log.error("Refusing to write: %d LLM_ERROR_RETRY rows. Re-run (cache resumes).", n_err_rows); return 2
    safe_write_tsv(out, outdir / "03_mp_term_taxonomy.tsv")
    safe_write_tsv(out[out["allow_strict_mdd_face_validity"]].copy(), outdir / "04_strict_eligible_terms.tsv")
    (outdir / "99_rebuild_run_config.json").write_text(json.dumps({"script": "rebuild_mdd_taxonomy.py",
        "taxonomy_in": str(tax_path), "model": model, "seed": args.seed, "category_set_hash": cat_hash,
        "categories": MDD_DOMAIN_NAMES, "strict_categories": MDD_STRICT_DOMAINS, "n_input": len(tax),
        "n_strict_eligible": n_strict, "elapsed_seconds": round(time.time() - t0, 1)}, indent=2))
    log.info("Done. Next: finalize (relevance_tier re-key — ASD tier-5 leak affects MDD), then point mdd.disorder.json taxonomy_tsv here + run Stage 1->5.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
