#!/usr/bin/env python3
import argparse, csv, hashlib, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from errpolicy import classify
import llm_budget as LB
import decompose_targets_to_criterion_units as DT
from criterion_spec import load_spec, extract

TARGETS = {"ASD": "pilot_hpo_run_hybrid_v3", "SCZ": "pilot_hpo_run_scz_v1",
           "ID": "pilot_hpo_run_intellectualdisability_v1", "NCD": "pilot_hpo_run_neurocognitive_v1"}
PERMANENT = ("insufficient_quota", "billing", "invalid_api_key", "invalid x-api-key", "authentication",
             "permission", "badrequest", "not_found", "api key not valid")


def call(backend, model, system, user):
    if backend == "claude":
        import anthropic
        tool = {"name": "record_attribution", "description": "Record the unit attribution.",
                "input_schema": DT.SCHEMA["schema"]}
        r = anthropic.Anthropic().messages.create(model=model, max_tokens=1024, system=system,
            messages=[{"role": "user", "content": user}], tools=[tool],
            tool_choice={"type": "tool", "name": "record_attribution"})
        b = next((x.input for x in r.content if x.type == "tool_use"), None)
        if b is None: raise RuntimeError("no tool_use block")
        return b, getattr(r, "model", model)
    if backend == "gemini":
        from google import genai
        from google.genai import types
        from pydantic import BaseModel
        class Attr(BaseModel):
            item_id: str; second_item_id: str; attributable: bool; confidence: float
            needs_manual_review: bool; reason: str
        client = genai.Client()
        r = client.models.generate_content(model=model, contents=user,
            config=types.GenerateContentConfig(system_instruction=system, temperature=0.0, seed=1,
                response_mime_type="application/json", response_schema=Attr))
        return json.loads(r.text), model
    raise ValueError(backend)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disorder", required=True, choices=list(TARGETS))
    ap.add_argument("--backend", required=True, choices=["claude", "gemini"])
    ap.add_argument("--model", required=True)
    ap.add_argument("--dry_run", action="store_true")
    ap.add_argument("--budget_usd", type=float, default=None)
    a = ap.parse_args()
    D = a.disorder
    spec = load_spec(f"criterion_specs/{D}.json"); criteria, stems, _ = extract(spec, ".")
    dev = DT.build_prompt(spec, criteria, stems); sha = hashlib.sha256(dev.encode()).hexdigest()
    units = [i["item_id"] for i in spec["items"]]
    rows = list(csv.DictReader(open(f"{TARGETS[D]}/07_final_resolved_hpo_terms.tsv", encoding="utf-8"), delimiter="\t"))
    print(f"{D} {a.backend}: {len(rows)} anchors, units {units}, prompt sha {sha[:16]}", flush=True)
    if a.dry_run: return 0
    out = Path(f"_reassign/{D}_{a.backend}"); out.mkdir(parents=True, exist_ok=True)
    raw = out / "raw.jsonl"; done = {}
    if raw.exists():
        for line in raw.open(encoding="utf-8"):
            try:
                r = json.loads(line)
                if r.get("prompt_sha") == sha: done[r["hpo_id"]] = r
            except Exception: pass
    res = []
    if a.backend == "claude" and len(done) < len(rows):
        sys.exit("REFUSED: synchronous Claude calls are disabled (llm_budget rule 4); the Claude arm of part B is complete")
    led = None
    if a.backend == "gemini" and len(done) < len(rows):
        LB.install_gemini_usage_hook(); led = LB.Ledger("gemini", f"B_{D}", a.model, "sync", a.budget_usd)
    with raw.open("a", encoding="utf-8") as fh:
        for i, r in enumerate(rows, 1):
            if r["hpo_id"] in done: res.append(done[r["hpo_id"]]); continue
            user = (f"HPO term: {r.get('hpo_label','')}\n"
                    f"HPO id: {r.get('hpo_id','')}\n"
                    f"Normalized phenotype as extracted from the DSM text: {r.get('normalized_phenotype','')}\n"
                    f"Centrality recorded at stage 1: {r.get('centrality','')}\n"
                    f"Rationale recorded at stage 1: {(r.get('rationale','') or '')[:400]}")
            p = None
            for attempt in range(10):
                try:
                    p, mdl = call(a.backend, a.model, dev, user); break
                except Exception as e:
                    kind, short = classify(e)
                    if kind == "permanent":
                        sys.exit(f"PERMANENT API ERROR: {short}; {len(res)} rows saved, re-run resumes")
                    if attempt in (0, 4, 9): print(f"  retry {attempt+1} ({kind}): {short}", flush=True)
                    time.sleep(min(300, (30 if kind == "retry_long" else 4) * 2 ** min(attempt, 4)))
            if p is None: sys.exit("failed after retries; re-run resumes")
            if led is not None:
                u = LB.take_gemini_usage()
                if u: led.add(u[0], u[1], note=r["hpo_id"]); mdl = u[2] or mdl
                if led.exceeded(): sys.exit(f"BUDGET STOP: gemini ledger ${led.total():.2f} reached the cap; re-run resumes")
            if p.get("item_id") not in units + ["none"]:
                p["needs_manual_review"] = True; p["reason"] = f"INVALID item_id {p.get('item_id')!r}. " + str(p.get("reason", ""))
            rec = {"disorder": spec["disorder"], "hpo_id": r["hpo_id"], "hpo_label": r.get("hpo_label", ""),
                   "category": r.get("category", ""), "centrality": r.get("centrality", ""), **p,
                   "prompt_sha": sha, "spec_version": spec.get("spec_version", ""), "model": mdl, "backend": a.backend}
            fh.write(json.dumps(rec) + "\n"); fh.flush(); res.append(rec)
            print(f"  [{i}/{len(rows)}] {r.get('hpo_label','')[:44]:44s} -> {p.get('item_id')}", flush=True)
    cols = ["disorder", "hpo_id", "hpo_label", "category", "centrality", "item_id", "second_item_id", "attributable",
            "confidence", "needs_manual_review", "reason", "prompt_sha", "spec_version", "model", "backend"]
    with (out / "03_target_criterion_units.tsv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter="\t", extrasaction="ignore"); w.writeheader(); w.writerows(res)
    print(f"wrote {out/'03_target_criterion_units.tsv'} ({len(res)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
