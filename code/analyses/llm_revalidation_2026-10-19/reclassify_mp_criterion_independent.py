#!/usr/bin/env python3
import argparse, csv, hashlib, json, random, re, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from errpolicy import classify
import llm_budget as LB
from criterion_prompt import build_developer_prompt, build_schema
from criterion_spec import load_spec, extract, item_directions
import classify_mp_terms_criterion_grounded as C

RUNS = {"ASD": ("criterion_specs/ASD.json", "taxonomy_v2_full/run_ASD"),
        "SCZ": ("criterion_specs/SCZ_dsmdef.json", "taxonomy_v2_full/prod_SCZ_2026-07-28"),
        "ID": ("criterion_specs/ID.json", "taxonomy_v2_full/run_ID"),
        "NCD": ("criterion_specs/NCD_dsmdef.json", "taxonomy_v2_full/prod_NCD_2026-07-28")}
PERMANENT = ("insufficient_quota", "billing", "invalid_api_key", "invalid x-api-key", "authentication",
             "permission", "badrequest", "not_found", "api key not valid")


def call(backend, model, system, user, schema):
    if backend == "claude":
        import anthropic
        tool = {"name": "record_classification", "description": "Record the classification.", "input_schema": schema["schema"]}
        r = anthropic.Anthropic().messages.create(model=model, max_tokens=1500, system=system,
            messages=[{"role": "user", "content": user}], tools=[tool], tool_choice={"type": "tool", "name": "record_classification"})
        b = next((x.input for x in r.content if x.type == "tool_use"), None)
        if b is None: raise RuntimeError("no tool_use block")
        return b, getattr(r, "model", model)
    from google import genai
    from google.genai import types
    js = dict(schema["schema"]); js.pop("additionalProperties", None)
    try:
        cfg = types.GenerateContentConfig(system_instruction=system, temperature=0.0, seed=1,
                                          response_mime_type="application/json", response_json_schema=js)
    except Exception:
        cfg = types.GenerateContentConfig(system_instruction=system, temperature=0.0, seed=1,
                                          response_mime_type="application/json", response_schema=js)
    client = genai.Client()
    r = client.models.generate_content(model=model, contents=user, config=cfg)
    return json.loads(r.text), model


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disorder", required=True, choices=list(RUNS))
    ap.add_argument("--backend", required=True, choices=["claude", "gemini"])
    ap.add_argument("--model", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--dry_run", action="store_true")
    ap.add_argument("--terms_file", default=None, help="pre-registered sample (TSV with mp_label); restricts the run to it")
    ap.add_argument("--emit_requests", default=None)
    ap.add_argument("--ingest", default=None)
    ap.add_argument("--no_api", action="store_true")
    ap.add_argument("--budget_usd", type=float, default=None)
    ap.add_argument("--max_calls", type=int, default=None)
    ap.add_argument("--outdir", default=None)
    a = ap.parse_args()
    spec_p, run = RUNS[a.disorder]
    spec = load_spec(spec_p); criteria, stems, _ = extract(spec, ".")
    directions = item_directions(spec)
    dev = build_developer_prompt(spec, criteria, stems, mode="joint"); sha = hashlib.sha256(dev.encode()).hexdigest()
    schema = build_schema(spec, mode="joint")
    rec_sha = json.load(open(f"{run}/00_prompt_provenance.json"))["prompt_sha"]
    rows = list(csv.DictReader(open(f"{run}/03_taxonomy.tsv", encoding="utf-8"), delimiter="\t"))
    scope = {r["mp_label"]: r for r in csv.DictReader(open(f"taxonomy_v2_full/scope_main_{a.disorder}.tsv", encoding="utf-8"), delimiter="\t")} \
        if Path(f"taxonomy_v2_full/scope_main_{a.disorder}.tsv").exists() else {}
    terms = [dict(scope.get(r["mp_label"], {}), **{k: r[k] for k in ("mp_id", "mp_label")}) for r in rows]
    if a.terms_file:
        keep = [r["mp_label"] for r in csv.DictReader(open(a.terms_file, encoding="utf-8"), delimiter="\t")]
        have = {t["mp_label"] for t in terms}; miss_s = [k for k in keep if k not in have]
        if miss_s: sys.exit(f"{len(miss_s)} sample terms not in the record taxonomy, e.g. {miss_s[:3]}")
        keep = set(keep); terms = [t for t in terms if t["mp_label"] in keep]
        print(f"  sample: {len(terms)} terms from {a.terms_file}", flush=True)
    print(f"{a.disorder} {a.backend}: {len(terms)} terms, prompt sha now {sha[:16]}, record {rec_sha[:16]}"
          f"{'' if sha == rec_sha else ' (DIFFERENT: record built on an earlier prompt)'}; scope rows found {sum(1 for t in terms if 'mp_definition' in t)}", flush=True)
    if a.dry_run: return 0
    out = Path(a.outdir or f"_reclass/{a.disorder}_{a.backend}"); out.mkdir(parents=True, exist_ok=True)
    raw = out / "raw.jsonl"; done = {}
    if raw.exists():
        for ln in raw.open(encoding="utf-8"):
            try:
                r = json.loads(ln)
                if r.get("prompt_sha") == sha: done[r["mp_label"]] = r
            except Exception: pass
    todo = [t for t in terms if t["mp_label"] not in done]
    print(f"  resume: {len(done)} done, {len(todo)} to run", flush=True)
    ids = {}
    for t in terms:
        k = "t_" + re.sub(r"[^A-Za-z0-9_-]", "_", t.get("mp_id") or "")
        if len(k) < 4 or k in ids.values(): k = "h_" + hashlib.sha1(t["mp_label"].encode()).hexdigest()[:16]
        ids[t["mp_label"]] = k

    def make_rec(t, p, mdl, transport):
        dok = C.direction_ok(p.get("item_id", ""), p.get("term_direction", ""), directions)
        return {"disorder": spec["disorder"], "mp_id": t.get("mp_id", ""), "mp_label": t["mp_label"], **p,
                "item_direction": directions.get(p.get("item_id", ""), ""), "direction_ok": dok,
                "admissible_directionaware": bool(p.get("admissible")) and dok, "response_model": mdl,
                "backend": a.backend, "prompt_sha": sha, "spec_version": spec.get("spec_version", ""), "transport": transport}

    if a.emit_requests:
        tool = {"name": "record_classification", "description": "Record the classification.", "input_schema": schema["schema"]}
        Path(a.emit_requests).parent.mkdir(parents=True, exist_ok=True)
        with open(a.emit_requests, "w", encoding="utf-8") as fh:
            for t in todo:
                fh.write(json.dumps({"cid": ids[t["mp_label"]], "mp_label": t["mp_label"], "sha": sha, "model": a.model,
                                     "max_tokens": 1500, "system": dev, "user": C.build_user_prompt(t), "tool": tool},
                                    ensure_ascii=False) + "\n")
        print(f"  wrote {len(todo)} requests to {a.emit_requests}", flush=True); return 0
    if a.ingest:
        got = {}
        for ln in open(a.ingest, encoding="utf-8"):
            try:
                r = json.loads(ln)
                if r.get("ok"): got[r["cid"]] = r
            except Exception: pass
        n_in = 0
        with raw.open("a", encoding="utf-8") as fh:
            for t in todo:
                r = got.get(ids[t["mp_label"]])
                if r is None: continue
                rec = make_rec(t, r["response"], r.get("model"), "batch")
                fh.write(json.dumps(rec) + "\n"); done[t["mp_label"]] = rec; n_in += 1
        todo = [t for t in todo if t["mp_label"] not in done]
        print(f"  ingested {n_in} terms; {len(todo)} still without a verdict", flush=True)
    if a.no_api: todo = []
    if a.backend == "claude" and todo:
        print("REFUSED: synchronous Claude calls are disabled (llm_budget rule 4). Use claude_batch.py, then "
              "re-run with --ingest _batches/NAME/results.jsonl --no_api", flush=True); return 6
    led = None; pilot = False; n_todo_all = len(todo)
    if a.backend == "gemini" and todo:
        LB.install_gemini_usage_hook()
        led = LB.Ledger("gemini", f"C_{a.disorder}", a.model, "sync", a.budget_usd)
        if a.max_calls:
            pilot = True; todo = random.Random(1).sample(todo, min(a.max_calls, len(todo)))
            print(f"  PILOT: {len(todo)} random terms of {n_todo_all}", flush=True)
        else:
            led.gate_full_run(len(todo))
    lock = threading.Lock(); stop = threading.Event(); t0 = time.time(); n = [0]

    def run1(t):
        if stop.is_set(): return
        p = None
        for att in range(10):
            try:
                p, mdl = call(a.backend, a.model, dev, C.build_user_prompt(t), schema); break
            except Exception as e:
                if led is not None:
                    u = LB.take_gemini_usage()
                    if u: led.add(u[0], u[1], note="failed parse " + t["mp_label"][:40])
                kind, short = classify(e)
                if kind == "permanent":
                    print(f"PERMANENT API ERROR, stopping: {short}", flush=True); stop.set(); return
                if att in (0, 4, 9): print(f"  retry {att+1} ({kind}) {t['mp_label'][:40]}: {short}", flush=True)
                time.sleep(min(300, (30 if kind == "retry_long" else 4) * 2 ** min(att, 4)))
        if p is None:
            print(f"  failed after retries: {t['mp_label']}", flush=True); return
        if led is not None:
            u = LB.take_gemini_usage()
            if u:
                led.add(u[0], u[1], note=t["mp_label"][:40]); mdl = u[2] or mdl
            if led.exceeded():
                print(f"BUDGET STOP: gemini ledger ${led.total():.2f} reached the cap ${led.cap:.2f}", flush=True); stop.set()
        rec = make_rec(t, p, mdl, "sync")
        with lock:
            with raw.open("a", encoding="utf-8") as fh: fh.write(json.dumps(rec) + "\n")
            done[t["mp_label"]] = rec; n[0] += 1
            if n[0] % 100 == 0: print(f"  {n[0]}/{len(todo)} terms, {time.time()-t0:.0f}s", flush=True)

    with ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
        for f in as_completed([ex.submit(run1, t) for t in todo]): f.result()
    if pilot:
        n, c, per = LB.job_stats("gemini", f"C_{a.disorder}")
        left = n_todo_all - len([t for t in todo if t["mp_label"] in done])
        print(f"PILOT DONE: measured ${per or 0:.4f} per term; {left} terms left, projected ${(per or 0)*left:.2f}. "
              f"Gemini ledger total ${LB.spent('gemini'):.2f}", flush=True)
        return 7
    if stop.is_set(): return 5 if (led is not None and led.exceeded()) else 4
    cols = ["disorder", "mp_id", "mp_label", "item_id", "second_item_id", "component", "admissible", "term_direction",
            "item_direction", "direction_ok", "admissible_directionaware", "modality", "qualifier_absent",
            "construct_inadmissible", "confidence", "needs_manual_review", "reason", "response_model", "backend", "prompt_sha", "spec_version"]
    with (out / "03_taxonomy.tsv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter="\t", extrasaction="ignore"); w.writeheader()
        for t in terms:
            if t["mp_label"] in done: w.writerow(done[t["mp_label"]])
    miss = sum(1 for t in terms if t["mp_label"] not in done)
    print(f"wrote {out/'03_taxonomy.tsv'} ({len(terms)-miss} of {len(terms)} terms)", flush=True)
    return 0 if miss == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
