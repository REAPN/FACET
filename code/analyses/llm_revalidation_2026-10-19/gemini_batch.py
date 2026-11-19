#!/usr/bin/env python3
import argparse, json, os, random, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent)); sys.path.insert(0, str(Path.cwd()))
import llm_budget as B

ROOT = Path(os.environ.get("FACET_GBATCH_ROOT", "_gbatches"))
MODE = "batch"; MODEL = "gemini-2.5-pro"
MAX_QUEUED_TOKENS = int(os.environ.get("FACET_GEMINI_MAX_QUEUED", "4000000"))
MAX_BATCH_CHARS = 8_000_000; POLL = int(os.environ.get("FACET_GEMINI_POLL", "60"))


def P(n): return ROOT / n
def load_reqs(n):
    f = P(n) / "requests.jsonl"
    if not f.exists(): sys.exit(f"{f} missing: run the job script with --backend gemini --emit_requests {f}")
    return [json.loads(l) for l in f.open(encoding="utf-8")]
def load_state(n):
    f = P(n) / "state.json"
    return json.loads(f.read_text()) if f.exists() else {"batches": []}
def save_state(n, st):
    f = P(n) / "state.json"; t = f.with_suffix(".tmp"); t.write_text(json.dumps(st, indent=1)); os.replace(t, f)
def results(n):
    f = P(n) / "results.jsonl"; out = {}
    if f.exists():
        for l in f.open(encoding="utf-8"):
            try: r = json.loads(l); out[r["cid"]] = r
            except Exception: pass
    return out
def done_ids(n): return {c for c, r in results(n).items() if r.get("ok")}
def pending(st): return [b for b in st["batches"] if not b.get("collected")]
def pending_ids(st): return {c for b in pending(st) for c in b["cids"]}
def est_tokens(r): return (len(r["system"]) + len(r["user"])) // 3 + 50
MAX_ATTEMPTS = 3
def attempts(st, since=0):
    a = {}
    for b in st["batches"]:
        if b.get("submitted", 0) < since: continue
        for c in b["cids"]: a[c] = a.get(c, 0) + 1
    return a


def _alive(pid):
    try: os.kill(pid, 0); return True
    except OSError: return False
def take_lock():
    ROOT.mkdir(parents=True, exist_ok=True); f = ROOT / ".run.lock"
    while True:
        try:
            fd = os.open(f, os.O_CREAT | os.O_EXCL | os.O_WRONLY); os.write(fd, str(os.getpid()).encode()); os.close(fd)
            import atexit; atexit.register(lambda: f.exists() and f.read_text().strip() == str(os.getpid()) and f.unlink()); return
        except FileExistsError:
            try: pid = int(f.read_text().strip() or 0)
            except Exception: pid = 0
            if pid and not _alive(pid): f.unlink(); continue
            sys.exit(f"another gemini_batch.py (pid {pid}) is running")


def config_for(name, r):
    from google.genai import types
    if name.startswith("A_"):
        import judge_backends as JB
        return types.GenerateContentConfig(system_instruction=r["system"], temperature=0.0, seed=1,
                                           response_mime_type="application/json", response_schema=JB._bundle_pydantic())
    js = dict(r["tool"]["input_schema"]); js.pop("additionalProperties", None)
    try:
        return types.GenerateContentConfig(system_instruction=r["system"], temperature=0.0, seed=1,
                                           response_mime_type="application/json", response_json_schema=js)
    except Exception:
        return types.GenerateContentConfig(system_instruction=r["system"], temperature=0.0, seed=1,
                                           response_mime_type="application/json", response_schema=js)


def client():
    from google import genai
    return genai.Client()


def create(c, name, part):
    from google.genai import types
    lock = P(name) / ".submitting"
    if lock.exists(): sys.exit(f"{lock} exists: a submit stopped between create and the state write; check AI Studio batches first")
    src = [types.InlinedRequest(contents=r["user"], config=config_for(name, r)) for r in part]
    lock.write_text(str(time.time()))
    try:
        job = c.batches.create(model=MODEL, src=src, config={"display_name": f"facet_{name}_{int(time.time())}"})
    except Exception as e:
        lock.unlink()
        msg = " ".join(str(e).split())[:300]
        sys.exit(f"STOP: batch create refused for {name}: {msg}")
    st = load_state(name)
    st["batches"].append({"id": job.name, "cids": [r["cid"] for r in part], "tokens_est": sum(est_tokens(r) for r in part),
                          "submitted": int(time.time()), "collected": False})
    save_state(name, st); lock.unlink()
    print(f"  {name}: submitted {job.name} with {len(part)} requests (about {sum(est_tokens(r) for r in part):,} input tokens)", flush=True)


def collect_one(c, name, b, led):
    job = c.batches.get(name=b["id"]); s = job.state.name if hasattr(job.state, "name") else str(job.state)
    if s in ("JOB_STATE_PENDING", "JOB_STATE_RUNNING", "JOB_STATE_QUEUED", "BATCH_STATE_PENDING", "BATCH_STATE_RUNNING"):
        return s
    resp = list(getattr(getattr(job, "dest", None), "inlined_responses", None) or [])
    n_ok = n_err = 0
    with (P(name) / "results.jsonl").open("a", encoding="utf-8") as fh:
        for i, cid in enumerate(b["cids"]):
            ir = resp[i] if i < len(resp) else None
            rec = {"cid": cid, "ok": False, "response": None, "model": None, "error": None}
            if ir is None:
                rec["error"] = f"no response ({s})"
            elif getattr(ir, "error", None):
                rec["error"] = str(ir.error)[:300]
            else:
                r = ir.response; u = getattr(r, "usage_metadata", None)
                tin = getattr(u, "prompt_token_count", 0) or 0
                tout = (getattr(u, "candidates_token_count", 0) or 0) + (getattr(u, "thoughts_token_count", 0) or 0)
                tout = max(tout, (getattr(u, "total_token_count", 0) or 0) - tin)
                led.add(tin, tout, note=cid); rec.update(model=getattr(r, "model_version", None), **{"in": tin, "out": tout})
                try: rec["response"] = json.loads(r.text); rec["ok"] = True
                except Exception as e: rec["error"] = f"unparsable: {type(e).__name__}"
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n"); n_ok += rec["ok"]; n_err += (not rec["ok"])
    st = load_state(name)
    for x in st["batches"]:
        if x["id"] == b["id"]: x["collected"] = True; x["final_state"] = s
    save_state(name, st)
    print(f"  {name}: collected {b['id']} ({s}): {n_ok} ok, {n_err} not ok", flush=True)
    return (s, n_ok, n_err, b.get("submitted", 0))


def committed():
    tot = 0.0; per_all = []
    for d in (ROOT.iterdir() if ROOT.exists() else []):
        if d.is_dir(): per_all.append(B.job_stats("gemini", "gb_" + d.name)[2])
    fb = max([x for x in per_all if x] or [0.03])
    for d in (ROOT.iterdir() if ROOT.exists() else []):
        if d.is_dir():
            per = B.job_stats("gemini", "gb_" + d.name)[2] or fb
            tot += len(pending_ids(load_state(d.name))) * per
    return tot


def queued_tokens():
    return sum(b.get("tokens_est", 0) for d in (ROOT.iterdir() if ROOT.exists() else []) if d.is_dir() for b in pending(load_state(d.name)))


def report(name):
    reqs = load_reqs(name); st = load_state(name); res = results(name); ok = {c for c, r in res.items() if r.get("ok")}
    models = sorted({r.get("model") for r in res.values() if r.get("model")})
    n, cost, per = B.job_stats("gemini", "gb_" + name)
    print(f"{name}: {len(reqs)} requests, {len(ok)} done, {len(pending_ids(st))} pending, {len([r for r in reqs if r['cid'] not in ok])} not done; "
          f"models {models}; ledger {n} calls ${cost:.2f}" + (f", ${per:.4f} per call" if per else ""))
    return reqs, ok, per


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["pilot", "run", "status"]); ap.add_argument("names", nargs="*")
    ap.add_argument("--n", type=int, default=20); ap.add_argument("--budget_usd", type=float, default=None)
    a = ap.parse_args()
    if a.cmd == "status":
        for nm in (a.names or sorted(p.name for p in ROOT.iterdir() if p.is_dir())): report(nm)
        print(f"gemini ledger total since 2026-10-20: ${B.spent('gemini'):.2f}"); return 0
    if not a.names: sys.exit("name the job(s)")
    if a.budget_usd is None: sys.exit("--budget_usd is required (no default, by design)")
    take_lock(); c = client()
    leds = {n: B.Ledger("gemini", "gb_" + n, MODEL, MODE, cap_usd=a.budget_usd) for n in a.names}
    if a.cmd == "pilot":
        for name in a.names:
            reqs = load_reqs(name); st = load_state(name); skip = done_ids(name) | pending_ids(st)
            todo = [r for r in reqs if r["cid"] not in skip]
            if B.spent("gemini") + committed() + 0.05 * a.n >= a.budget_usd: sys.exit("REFUSED: gemini ledger plus pending would exceed the cap")
            create(c, name, random.Random(1).sample(todo, min(a.n, len(todo))))
        while any(pending(load_state(n)) for n in a.names):
            for name in a.names:
                for b in pending(load_state(name)): collect_one(c, name, b, leds[name])
            if any(pending(load_state(n)) for n in a.names): time.sleep(POLL)
        for name in a.names:
            reqs, ok, per = report(name)
            if per: print(f"  projection for the {len(reqs) - len(ok)} left: ${per * (len(reqs) - len(ok)):.2f} at the batch price")
        return 0
    for name in a.names:
        if B.job_stats("gemini", "gb_" + name)[2] is None: sys.exit(f"REFUSED: no measured cost for {name}; run: pilot {name}")
    proj = 0.0
    for name in a.names:
        reqs = load_reqs(name); left = [r for r in reqs if r["cid"] not in done_ids(name) | pending_ids(load_state(name))]
        proj += B.job_stats("gemini", "gb_" + name)[2] * len(left)
    room = a.budget_usd - B.spent("gemini") - committed()
    print(f"projected ${proj:.2f} for what is left; gemini spent ${B.spent('gemini'):.2f} plus ${committed():.2f} pending, cap ${a.budget_usd:.2f}", flush=True)
    if proj > room: sys.exit(f"REFUSED: projected ${proj:.2f} exceeds the ${room:.2f} left under the cap")
    t_run = int(time.time())
    while True:
        for name in a.names:
            for b in pending(load_state(name)):
                res = collect_one(c, name, b, leds[name])
                if isinstance(res, tuple):
                    s_, ok_, err_, sub_ = res
                    if sub_ >= t_run and err_ > 0 and err_ >= ok_:
                        sys.exit(f"STOP: {name} batch {b['id']} came back with {err_} errors and {ok_} ok. Not resubmitting. "
                                 f"Check results.jsonl errors (billing, quota or a request defect) before re-running.")
        busy = False
        for name in a.names:
            reqs = load_reqs(name); st = load_state(name); skip = done_ids(name) | pending_ids(st)
            att = attempts(st, since=t_run); spent_out = [r["cid"] for r in reqs if r["cid"] not in skip and att.get(r["cid"], 0) >= MAX_ATTEMPTS]
            if spent_out: print(f"  {name}: {len(spent_out)} requests reached {MAX_ATTEMPTS} attempts and are skipped", flush=True)
            todo = [r for r in reqs if r["cid"] not in skip and att.get(r["cid"], 0) < MAX_ATTEMPTS]
            if todo or pending(st): busy = True
            if not todo: continue
            part, tok, ch = [], 0, 0; q0 = queued_tokens()
            for r in todo:
                t = est_tokens(r); s = len(r["system"]) + len(r["user"])
                if q0 + tok + t > MAX_QUEUED_TOKENS or (part and ch + s > MAX_BATCH_CHARS): break
                part.append(r); tok += t; ch += s
            if part:
                if B.spent("gemini") + committed() > a.budget_usd: print("BUDGET STOP"); return 5
                create(c, name, part)
        if not busy: break
        time.sleep(POLL)
    for name in a.names: report(name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
