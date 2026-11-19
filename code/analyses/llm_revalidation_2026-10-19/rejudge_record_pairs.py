#!/usr/bin/env python3
import argparse, hashlib, json, random, re, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path.cwd()))
import rerank_ambiguous_pairs_api_v3 as R
sys.path.insert(0, str(Path(__file__).resolve().parent))
from errpolicy import classify
import llm_budget as LB
import rerank_independent_judge as RIJ
import judge_backends as JB
import openai_judge as OJ

REF = {"ASD": "asd_pair_rerank_v3_broad_v3", "SCZ": "scz_pair_rerank_v1",
       "ID": "intellectualdisability_pair_rerank_v1", "NCD": "neurocognitive_pair_rerank_v1_ncdB_cf"}
DIS = {"ASD": "asd", "SCZ": "scz", "ID": "id", "NCD": "neurocognitive"}
K = ["target_id", "mp_id", "mp_term"]
OVERLAY = ["rerank_action", "comparable_observable", "evidence_scope", "behavioral_analog_type",
           "strict_eligible", "broad_eligible", "reason"]
DELTA = {"promote": 0.10, "keep": 0.0, "demote": -0.10, "abstain": -0.25}
PERMANENT = ("insufficient_quota", "exceeded your current quota", "billing", "invalid_api_key", "invalid x-api-key",
             "authentication", "permission", "badrequest", "not_found", "model_not_found", "api key not valid")


def typed(df):
    for c in ("transparent_score", "embed_norm", "lexical_norm", "resnik_norm", "jaccard_norm", "transparent_rank"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "n_available_channels" in df.columns:
        df["n_available_channels"] = pd.to_numeric(df["n_available_channels"], errors="coerce").fillna(0).astype(int)
    if "structural_missing" in df.columns:
        df["structural_missing"] = df["structural_missing"].map(lambda v: str(v).strip().lower() in ("true", "1", "yes"))
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disorder", required=True, choices=list(REF))
    ap.add_argument("--backend", required=True, choices=["claude", "gemini", "openai", "cached"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--chunk", type=int, default=5)
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--dry_run", action="store_true", help="build every chunk and prompt hash, make no call")
    ap.add_argument("--emit_requests", default=None, help="write the chunks still to do as batch requests (JSONL) and stop")
    ap.add_argument("--ingest", default=None, help="results.jsonl from claude_batch.py to fold into raw.jsonl")
    ap.add_argument("--no_api", action="store_true", help="make no API call; merge what is in raw.jsonl")
    ap.add_argument("--budget_usd", type=float, default=None, help="spend cap for the backend, required for any API call")
    ap.add_argument("--max_calls", type=int, default=None, help="pilot: run only this many random chunks, then print the projection")
    a = ap.parse_args()
    D = a.disorder; ref = Path(REF[D]); out = Path(a.outdir or f"_judgeswap/{D}_{a.backend}"); out.mkdir(parents=True, exist_ok=True)

    text = pd.read_csv(ref / "03_reranked_pairs_filled.tsv", sep="\t", dtype=str, keep_default_na=False)
    tab = typed(pd.read_csv(ref / "03_reranked_pairs_filled.tsv", sep="\t", low_memory=False))
    assert len(text) == len(tab)
    judged = text["rerank_action"].str.strip().ne("").to_numpy()
    pre = pd.read_csv(ref / "03_reranked_pairs.tsv", sep="\t", dtype=str, keep_default_na=False)
    pre = pre[pre["rerank_action"].str.strip().ne("")]
    bundle_keys = set(map(tuple, pre[K].values))
    origin = np.array(["bundle" if tuple(r) in bundle_keys else "fill" for r in text[K].values])
    sys_prompt = {"bundle": RIJ.dev_prompt_for(DIS[D], Path(".")), "fill": RIJ.BASE_DEV_PROMPT}
    sha = {o: hashlib.sha256(s.encode()).hexdigest()[:16] for o, s in sys_prompt.items()}

    chunks = []
    for o in ("bundle", "fill"):
        sub = tab[judged & (origin == o)].copy()
        sub["_row"] = sub.index
        for tid, g in sub.groupby("target_id", sort=False):
            g = g.sort_values(["transparent_rank", "_row"]) if "transparent_rank" in g.columns else g
            for s in range(0, len(g), a.chunk):
                chunks.append((o, str(tid), s, g.iloc[s:s + a.chunk]))
    n_pairs = int(judged.sum())
    print(f"{D} {a.backend}: {n_pairs} record pairs ({int((judged & (origin=='bundle')).sum())} bundle, "
          f"{int((judged & (origin=='fill')).sum())} fill) in {len(chunks)} chunks; prompt sha bundle {sha['bundle']} fill {sha['fill']}", flush=True)
    if a.dry_run:
        return 0

    raw = out / "raw.jsonl"; done = {}
    if raw.exists():
        for line in raw.open(encoding="utf-8"):
            try:
                r = json.loads(line)
                if r.get("sha") == sha[r["origin"]]:
                    done[(r["origin"], r["target_id"], r["start"])] = r
            except Exception:
                pass
    todo = [c for c in chunks if (c[0], c[1], c[2]) not in done]
    print(f"  resume: {len(done)} chunks already done, {len(todo)} to run", flush=True)

    def cid(c):
        k = f"{c[0][0]}{c[2]:04d}_{c[1]}"
        assert re.fullmatch(r"[A-Za-z0-9_-]{1,64}", k), k
        return k

    def user_for(g, tid):
        first = g.iloc[0]
        return RIJ.build_user_prompt(tid, str(first.get("hpo_label", "")), str(first.get("target_text", "")),
                                     str(first.get("human_domain", "")), g)

    if a.emit_requests:
        tool = {"name": "record_bundle",
                "description": "Record the rerank judgments for every listed candidate in the bundle.",
                "input_schema": R.RERANK_SCHEMA.get("schema", R.RERANK_SCHEMA)}
        Path(a.emit_requests).parent.mkdir(parents=True, exist_ok=True)
        with open(a.emit_requests, "w", encoding="utf-8") as fh:
            for c in todo:
                o, tid, s, g = c
                fh.write(json.dumps({"cid": cid(c), "origin": o, "target_id": tid, "start": s, "sha": sha[o],
                                     "model": a.model, "max_tokens": 4096, "system": sys_prompt[o],
                                     "user": user_for(g, tid), "tool": tool}, ensure_ascii=False) + "\n")
        print(f"  wrote {len(todo)} requests to {a.emit_requests}", flush=True)
        return 0
    if a.ingest:
        got = {}
        for line in open(a.ingest, encoding="utf-8"):
            try:
                r = json.loads(line)
                if r.get("ok"): got[r["cid"]] = r
            except Exception:
                pass
        n_in = 0
        with raw.open("a", encoding="utf-8") as fh:
            for c in todo:
                r = got.get(cid(c))
                if r is None: continue
                o, tid, s, g = c
                rec = {"origin": o, "target_id": tid, "start": s, "sha": sha[o], "backend": a.backend, "model": a.model,
                       "response_model": r.get("model"), "transport": "batch",
                       "keys": [list(map(str, x)) for x in g[K].values], "response": r["response"]}
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n"); done[(o, tid, s)] = rec; n_in += 1
        todo = [c for c in todo if (c[0], c[1], c[2]) not in done]
        print(f"  ingested {n_in} chunks from {a.ingest}; {len(todo)} still without a verdict", flush=True)
    if a.no_api:
        todo = []
    if a.backend == "claude" and todo:
        print("REFUSED: synchronous Claude calls are disabled (llm_budget rule 4). Use claude_batch.py, then "
              "re-run with --ingest _batches/NAME/results.jsonl --no_api", flush=True)
        return 6
    led = None; pilot = False; n_todo_all = len(todo)
    if a.backend == "openai" and todo:
        led = LB.Ledger("openai", f"A_{D}", a.model, "sync", a.budget_usd)
        if a.max_calls:
            pilot = True; todo = random.Random(1).sample(todo, min(a.max_calls, len(todo)))
            print(f"  PILOT: {len(todo)} random chunks of {n_todo_all}", flush=True)
        else:
            led.gate_full_run(len(todo))
    if a.backend == "gemini" and todo:
        LB.install_gemini_usage_hook()
        led = LB.Ledger("gemini", f"A_{D}", a.model, "sync", a.budget_usd)
        if a.max_calls:
            pilot = True; todo = random.Random(1).sample(todo, min(a.max_calls, len(todo)))
            print(f"  PILOT: {len(todo)} random chunks of {n_todo_all}", flush=True)
        else:
            led.gate_full_run(len(todo))
    lock = threading.Lock(); stop = threading.Event(); t0 = time.time(); n_ok = [0]

    def run(c):
        o, tid, s, g = c
        if stop.is_set():
            return
        if a.backend == "cached":
            obj = {"selected_candidates": [{"candidate_index": i, **{k: g.iloc[i - 1][k] for k in OVERLAY}}
                                           for i in range(1, len(g) + 1)]}
            obj = json.loads(json.dumps(obj, default=lambda v: None if (isinstance(v, float) and np.isnan(v)) else (v.item() if hasattr(v, "item") else str(v))))
        else:
            first = g.iloc[0]
            user = RIJ.build_user_prompt(tid, str(first.get("hpo_label", "")), str(first.get("target_text", "")),
                                         str(first.get("human_domain", "")), g)
            obj = None; oj_usage = None
            for attempt in range(10):
                try:
                    if a.backend == "openai":
                        obj, oj_usage = OJ.call_openai_with_usage(a.model, sys_prompt[o], user, 1, R.RERANK_SCHEMA)
                    else:
                        obj = JB.bundle_judgment(a.backend, a.model, sys_prompt[o], user, seed=1, schema=R.RERANK_SCHEMA)
                    break
                except Exception as e:
                    if led is not None:
                        u = LB.take_gemini_usage()
                        if u: led.add(u[0], u[1], note=f"failed parse {o} {tid} {s}")
                    kind, short = classify(e)
                    if kind == "permanent":
                        print(f"PERMANENT API ERROR, stopping: {short}", flush=True); stop.set(); return
                    if attempt in (0, 4, 9):
                        print(f"  retry {attempt+1} ({kind}) {o} {tid} {s}: {short}", flush=True)
                    time.sleep(min(300, (30 if kind == "retry_long" else 5) * 2 ** min(attempt, 4)))
            if obj is None:
                print(f"  chunk failed after retries: {o} {tid} {s}", flush=True); return
        rmodel = None
        if a.backend == "openai" and led is not None and oj_usage is not None:
            led.add(oj_usage[0], oj_usage[1], note=f"{o} {tid} {s}"); rmodel = oj_usage[2]
            if led.exceeded():
                print(f"BUDGET STOP: openai ledger ${led.total():.2f} reached the cap ${led.cap:.2f}", flush=True); stop.set()
        elif led is not None:
            u = LB.take_gemini_usage()
            if u:
                led.add(u[0], u[1], note=f"{o} {tid} {s}"); rmodel = u[2]
            if led.exceeded():
                print(f"BUDGET STOP: gemini ledger ${led.total():.2f} reached the cap ${led.cap:.2f}", flush=True); stop.set()
        rec = {"origin": o, "target_id": tid, "start": s, "sha": sha[o], "backend": a.backend, "model": a.model,
               "response_model": rmodel, "keys": [list(map(str, x)) for x in g[K].values], "response": obj}
        with lock:
            with raw.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            done[(o, tid, s)] = rec; n_ok[0] += 1
            if n_ok[0] % 50 == 0:
                print(f"  {n_ok[0]}/{len(todo)} chunks, {time.time()-t0:.0f}s", flush=True)

    with ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
        for f in as_completed([ex.submit(run, c) for c in todo]):
            f.result()
    if pilot:
        n, c, per = LB.job_stats(a.backend, f"A_{D}")
        left = n_todo_all - n_ok[0]
        print(f"PILOT DONE: {n_ok[0]} chunks, measured ${per or 0:.4f} per chunk; {left} chunks left, projected "
              f"${(per or 0)*left:.2f}. {a.backend} ledger total ${LB.spent(a.backend):.2f}", flush=True)
        return 7
    if stop.is_set():
        return 5 if (led is not None and led.exceeded()) else 4

    newv = {}
    for r in done.values():
        sel = {int(x.get("candidate_index", 0)): x for x in (r["response"] or {}).get("selected_candidates", [])}
        for i, key in enumerate(r["keys"], start=1):
            if i in sel:
                newv[tuple(key)] = sel[i]
    res = text.copy()
    keys = [tuple(x) for x in res[K].values]
    missing = 0
    for idx in np.where(judged)[0]:
        v = newv.get(keys[idx])
        if v is None:
            missing += 1
            for c in OVERLAY: res.at[idx, c] = ""
            res.at[idx, "rerank_delta"] = "0.0"; res.at[idx, "final_pair_score"] = res.at[idx, "transparent_score"]
            continue
        for c in OVERLAY:
            x = v.get(c); res.at[idx, c] = "" if x is None else str(x)
        d = DELTA.get(str(v.get("rerank_action")), 0.0)
        res.at[idx, "rerank_delta"] = str(d)
        res.at[idx, "final_pair_score"] = repr(float(min(1.0, max(0.0, float(tab.at[idx, "transparent_score"]) + d))))
    res.to_csv(out / "03_reranked_pairs_filled.tsv", sep="\t", index=False)
    strict = int(res["strict_eligible"].str.lower().eq("true").sum()); strict_ref = int(text["strict_eligible"].str.lower().eq("true").sum())
    summ = {"disorder": D, "backend": a.backend, "model": a.model, "record_pairs": n_pairs, "chunks": len(chunks),
            "pairs_without_new_verdict": missing, "strict_pairs_new": strict, "strict_pairs_record": strict_ref,
            "prompt_sha": sha, "elapsed_s": round(time.time() - t0, 1)}
    (out / "summary.json").write_text(json.dumps(summ, indent=1))
    print(json.dumps(summ), flush=True)
    return 0 if missing == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
