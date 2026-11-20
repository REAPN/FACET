#!/usr/bin/env python3
import argparse, csv, hashlib, json, os, sys, time
from pathlib import Path

from criterion_prompt import build_developer_prompt, build_schema
from criterion_spec import load_spec, extract, item_directions

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from openai import (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)
    TRANSIENT = (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)
except Exception:
    TRANSIENT = ()

PROMPT_VERSION = "v5_paraphrased_2026-11-19"


def _is_permanent(e):
    s = f"{type(e).__name__} {e}".lower()
    for marker in ("insufficient_quota", "exceeded your current quota", "billing",
                   "invalid_api_key", "authenticationerror", "permissiondenied",
                   "badrequesterror", "model_not_found"):
        if marker in s:
            return marker
    return None

def call_with_retry(client, max_attempts=5, base_backoff=4.0, max_backoff=90.0, **kw):
    import random
    last = None
    for attempt in range(max_attempts):
        try:
            return client.chat.completions.create(**kw)
        except TRANSIENT as exc:
            last = exc
            if attempt == max_attempts - 1:
                raise
            nap = min(max_backoff, base_backoff * (2 ** attempt)) * (0.5 + 0.5 * random.random())
            print(f"    transient {type(exc).__name__} (attempt {attempt+1}/{max_attempts}), "
                  f"sleeping {nap:.1f}s", flush=True)
            time.sleep(nap)
    if last is not None:
        raise last
    raise RuntimeError("call_with_retry exhausted attempts without an exception")


def direction_ok(item_id, term_direction, directions):
    want = directions.get(item_id)
    if want is None or want == "either":
        return True
    if term_direction in ("unspecified", "not_directional", ""):
        return True
    if want == "deficit":
        return term_direction == "decrease"
    if want == "increase":
        return term_direction == "increase"
    return True


def build_user_prompt(row):
    return f"""
Classify this blinded MP term.

mp_id: {row.get('mp_id','')}
mp_label: {row.get('mp_label') or row.get('mp_term','')}
mp_definition: {row.get('mp_definition') or 'NA'}
parent_label: {row.get('parent_label') or 'NA'}
ancestor_label: {row.get('ancestor_label') or 'NA'}
""".strip()


def read_tsv(p):
    with open(p, encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True, help="criterion_specs/<DISORDER>.json")
    ap.add_argument("--mp_terms", help="term table to classify (usually a scope TSV)")
    ap.add_argument("--pilot", help="pilot term TSV carrying an `expected` column")
    ap.add_argument("--outdir")
    ap.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-5.4"))
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--print_prompt", action="store_true",
                    help="print the developer prompt and exit, no API call")
    ap.add_argument("--allow_prompt_drift", action="store_true",
                    help="permit resuming from rows produced by a DIFFERENT developer prompt. Off by "
                         "default. Turning it on means the taxonomy mixes prompt versions and that MUST "
                         "be disclosed in methods.")
    a = ap.parse_args()
    root = os.environ.get("FACET_ROOT", ".")

    spec = load_spec(a.spec)
    criteria, stems, _ = extract(spec, root)
    directions = item_directions(spec)
    dev = build_developer_prompt(spec, criteria, stems, mode="joint")
    prompt_sha = hashlib.sha256(dev.encode("utf-8")).hexdigest()

    if a.print_prompt:
        print(dev)
        print(f"\n[disorder {spec['disorder']}  prompt_version {PROMPT_VERSION}  "
              f"spec_version {spec.get('spec_version')}  prompt_sha {prompt_sha}]", file=sys.stderr)
        return

    if not a.outdir:
        sys.exit("--outdir is required unless --print_prompt")
    out = Path(root) / a.outdir
    out.mkdir(parents=True, exist_ok=True)
    (out / "00_developer_prompt.txt").write_text(dev, encoding="utf-8")
    (out / "00_criteria_parsed.json").write_text(
        json.dumps({"items": criteria, "stems": stems}, indent=1), encoding="utf-8")
    (out / "00_prompt_provenance.json").write_text(
        json.dumps({"prompt_version": PROMPT_VERSION, "prompt_sha": prompt_sha,
                    "spec": str(a.spec), "spec_version": spec.get("spec_version"),
                    "disorder": spec["disorder"], "scored_grain": spec["scored_grain"],
                    "breadth_denominator": spec.get("breadth_denominator"),
                    "extra_rules": spec.get("extra_rules", []),
                    "model": a.model, "seed": a.seed,
                    "criteria_txt": spec["criteria_txt"]}, indent=1), encoding="utf-8")
    print(f"{spec['disorder']}  prompt {PROMPT_VERSION}  spec {spec.get('spec_version')}  "
          f"sha {prompt_sha[:16]}  units {len(spec['items'])} ({spec['scored_grain']})")

    if a.pilot:
        pilot = read_tsv(os.path.join(root, a.pilot))
        full = {r.get("mp_label", ""): r for r in read_tsv(os.path.join(root, a.mp_terms))} \
            if a.mp_terms else {}
        rows = []
        for r in pilot:
            base = dict(full.get(r["mp_label"], {}))
            base.update({k: v for k, v in r.items() if v})
            base.setdefault("mp_label", r["mp_label"])
            rows.append(base)
    elif a.mp_terms:
        rows = read_tsv(os.path.join(root, a.mp_terms))
    else:
        sys.exit("give --mp_terms or --pilot")
    if a.limit:
        rows = rows[: a.limit]

    if OpenAI is None:
        sys.exit("openai package not installed")
    client = OpenAI()
    schema = build_schema(spec, mode="joint")

    raw_path = out / "02_raw.jsonl"
    done, drift = {}, []
    if raw_path.exists():
        for ln in raw_path.open(encoding="utf-8"):
            rec = json.loads(ln)
            if rec.get("prompt_sha", "") != prompt_sha:
                drift.append(rec.get("mp_label", ""))
                if not a.allow_prompt_drift:
                    continue
            done[rec.get("mp_label", "")] = rec
    if drift:
        msg = (f"PROMPT DRIFT: {len(drift)} cached rows in {raw_path} came from a different developer "
               f"prompt. Current is {PROMPT_VERSION} sha {prompt_sha[:16]}. Examples: {drift[:5]}")
        print(msg + ("\n  --allow_prompt_drift is set, so they are being REUSED. The taxonomy mixes "
                     "prompt versions and this must be disclosed in methods."
                     if a.allow_prompt_drift else
                     "\n  They are being IGNORED and will be reclassified. Move 02_raw.jsonl aside for a "
                     "clean single-version file."))

    results = []
    with raw_path.open("a", encoding="utf-8") as fh:
        for i, row in enumerate(rows, 1):
            lab = row.get("mp_label", "")
            if lab in done:
                results.append(done[lab])
                continue
            resp = call_with_retry(
                client,
                model=a.model, temperature=0, seed=a.seed,
                messages=[{"role": "developer", "content": dev},
                          {"role": "user", "content": build_user_prompt(row)}],
                response_format={"type": "json_schema", "json_schema": schema},
            )
            parsed = json.loads(resp.choices[0].message.content)
            dok = direction_ok(parsed.get("item_id", ""), parsed.get("term_direction", ""), directions)
            rec = {"disorder": spec["disorder"],
                   "mp_id": row.get("mp_id", ""), "mp_label": lab,
                   "expected": row.get("expected", ""), "expected_item": row.get("expected_item", ""),
                   "expected_direction": row.get("expected_direction", ""),
                   "expect_review": row.get("expect_review", ""),
                   "pilot_note": row.get("pilot_note", ""), "scope_source": row.get("scope_source", ""),
                   "old_tier": row.get("old_tier", ""), "old_admissible": row.get("old_admissible", ""),
                   **parsed,
                   "item_direction": directions.get(parsed.get("item_id", ""), ""),
                   "direction_ok": dok,
                   "admissible_directionaware": bool(parsed.get("admissible")) and dok,
                   "response_model": getattr(resp, "model", a.model),
                   "prompt_version": PROMPT_VERSION, "prompt_sha": prompt_sha,
                   "spec_version": spec.get("spec_version", "")}
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            results.append(rec)
            print(f"  [{i}/{len(rows)}] {lab[:48]:48s} -> {parsed['item_id']:4s} "
                  f"admissible={parsed['admissible']} comp={parsed.get('component','')[:22]}", flush=True)

    cols = ["disorder", "mp_id", "mp_label", "expected", "expected_item", "expected_direction",
            "expect_review", "item_id", "second_item_id", "component", "admissible", "term_direction",
            "item_direction", "direction_ok", "admissible_directionaware", "modality",
            "qualifier_absent", "construct_inadmissible", "confidence", "needs_manual_review", "reason",
            "pilot_note", "scope_source", "old_tier", "old_admissible",
            "prompt_version", "prompt_sha", "spec_version"]
    with (out / "03_taxonomy.tsv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        for r in results:
            w.writerow(r)
    print(f"\nwrote {out/'03_taxonomy.tsv'} ({len(results)} terms)")


if __name__ == "__main__":
    main()
