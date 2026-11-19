#!/usr/bin/env python3
import argparse, json, os, random, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import llm_budget as B

ROOT = Path(os.environ.get("FACET_BATCH_ROOT", "_batches"))
MODE = "batch"


def P(name): return ROOT / name
def load_reqs(name):
    f = P(name) / "requests.jsonl"
    if not f.exists(): sys.exit(f"{f} missing: run the job script with --emit_requests first")
    return [json.loads(l) for l in f.open(encoding="utf-8")]
def load_state(name):
    f = P(name) / "state.json"
    return json.loads(f.read_text()) if f.exists() else {"batches": []}
def save_state(name, st):
    f = P(name) / "state.json"; tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=1)); os.replace(tmp, f)
def results(name):
    f = P(name) / "results.jsonl"; out = {}
    if f.exists():
        for l in f.open(encoding="utf-8"):
            try: r = json.loads(l); out[r["cid"]] = r
            except Exception: pass
    return out
def done_ids(name): return {c for c, r in results(name).items() if r.get("ok")}
def pending_ids(st): return {c for b in st["batches"] if not b.get("collected") for c in b["cids"]}


def committed():
    tot = 0.0; pers = []
    for d in (ROOT.iterdir() if ROOT.exists() else []):
        if d.is_dir():
            n, c, per = B.job_stats("claude", d.name)
            pers.append(per)
    fallback = max([x for x in pers if x] or [0.05])
    for d in (ROOT.iterdir() if ROOT.exists() else []):
        if d.is_dir():
            n, c, per = B.job_stats("claude", d.name)
            tot += len(pending_ids(load_state(d.name))) * (per or fallback)
    return tot


def params(r):
    return {"model": r["model"], "max_tokens": r["max_tokens"], "system": r["system"],
            "messages": [{"role": "user", "content": r["user"]}], "tools": [r["tool"]],
            "tool_choice": {"type": "tool", "name": r["tool"]["name"]}}


def client():
    import anthropic
    return anthropic.Anthropic()


def create(name, chosen):
    lock = P(name) / ".submitting"
    if lock.exists():
        sys.exit(f"{lock} exists: a previous submit stopped between create and the state write. Check the "
                 f"Anthropic console Batches page for an unrecorded batch before removing this file.")
    st = load_state(name); c = client(); ids = []
    for i in range(0, len(chosen), 5000):
        part = chosen[i:i + 5000]
        lock.write_text(str(time.time()))
        b = c.messages.batches.create(requests=[{"custom_id": r["cid"], "params": params(r)} for r in part])
        st["batches"].append({"id": b.id, "cids": [r["cid"] for r in part], "submitted": int(time.time()), "collected": False})
        save_state(name, st); lock.unlink(); ids.append(b.id)
        print(f"  submitted batch {b.id} with {len(part)} requests", flush=True)
    return ids


def collect(name, wait=False, poll=30, max_wait=86400):
    st = load_state(name); c = client(); t0 = time.time()
    led = None
    while True:
        open_b = [b for b in st["batches"] if not b.get("collected")]
        if not open_b: break
        progressed = False
        for b in open_b:
            info = c.messages.batches.retrieve(b["id"])
            if info.processing_status != "ended":
                rc = info.request_counts
                print(f"  {b['id']}: {info.processing_status} (processing {rc.processing}, succeeded {rc.succeeded}, errored {rc.errored})", flush=True)
                continue
            if led is None:
                req0 = load_reqs(name)[0]
                led = B.Ledger("claude", name, req0["model"], MODE, cap_usd=1e9)
            n_ok = n_err = 0
            with (P(name) / "results.jsonl").open("a", encoding="utf-8") as fh:
                for e in c.messages.batches.results(b["id"]):
                    res = e.result
                    if res.type == "succeeded":
                        m = res.message
                        tool = next((x.input for x in m.content if x.type == "tool_use"), None)
                        u = m.usage; tin = (u.input_tokens or 0) + (getattr(u, "cache_creation_input_tokens", 0) or 0) + (getattr(u, "cache_read_input_tokens", 0) or 0)
                        led.add(tin, u.output_tokens or 0, note=e.custom_id)
                        ok = tool is not None
                        fh.write(json.dumps({"cid": e.custom_id, "ok": ok, "response": tool, "model": m.model,
                                             "stop_reason": m.stop_reason, "in": tin, "out": u.output_tokens,
                                             "error": None if ok else "no tool_use block"}, ensure_ascii=False) + "\n")
                        n_ok += ok; n_err += (not ok)
                    else:
                        err = getattr(res, "error", None)
                        fh.write(json.dumps({"cid": e.custom_id, "ok": False, "response": None, "model": None,
                                             "error": f"{res.type}: {str(err)[:300]}"}) + "\n")
                        n_err += 1
            b["collected"] = True; save_state(name, st); progressed = True
            print(f"  collected {b['id']}: {n_ok} ok, {n_err} not ok", flush=True)
        if not wait or not [b for b in st["batches"] if not b.get("collected")]:
            if not progressed and not wait: print("  nothing ended yet; re-run collect later (or add --wait)")
            if not wait: break
        if time.time() - t0 > max_wait: print("  stopped waiting"); break
        time.sleep(poll)
    return led


def report(name):
    reqs = load_reqs(name); st = load_state(name); res = results(name)
    ok = {c for c, r in res.items() if r.get("ok")}
    models = sorted({r.get("model") for r in res.values() if r.get("model")})
    n, cost, per = B.job_stats("claude", name)
    left = len([r for r in reqs if r["cid"] not in ok])
    print(f"{name}: {len(reqs)} requests, {len(ok)} done, {len(pending_ids(st))} pending, {left} not done; "
          f"models returned {models}; ledger {n} calls ${cost:.2f}" + (f", ${per:.4f} per call" if per else ""))
    bad = [m for m in models if m != reqs[0]["model"]]
    if bad: print(f"  WARNING: returned model differs from the requested {reqs[0]['model']}: {bad}")
    return reqs, ok, per, left


def _alive(pid):
    try:
        os.kill(pid, 0); return True
    except OSError:
        return False


def take_lock(wait):
    ROOT.mkdir(parents=True, exist_ok=True); f = ROOT / ".run.lock"; said = False
    while True:
        try:
            fd = os.open(f, os.O_CREAT | os.O_EXCL | os.O_WRONLY); os.write(fd, str(os.getpid()).encode()); os.close(fd)
            import atexit; atexit.register(lambda: f.exists() and f.read_text().strip() == str(os.getpid()) and f.unlink())
            return
        except FileExistsError:
            try: pid = int(f.read_text().strip() or 0)
            except Exception: pid = 0
            if pid and not _alive(pid):
                f.unlink(); continue
            if not wait: sys.exit(f"another claude_batch.py (pid {pid}) is running; use --wait_lock to queue behind it")
            if not said: print(f"  waiting for claude_batch.py pid {pid} to finish", flush=True); said = True
            time.sleep(20)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["pilot", "submit", "collect", "status"])
    ap.add_argument("names", nargs="*")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--budget_usd", type=float, default=None)
    ap.add_argument("--wait", action="store_true")
    ap.add_argument("--wait_lock", action="store_true")
    a = ap.parse_args()
    if a.cmd != "status": take_lock(a.wait_lock)
    if a.cmd == "status":
        for nm in (a.names or sorted(p.name for p in ROOT.iterdir() if p.is_dir())): report(nm)
        print(f"claude ledger total since 2026-10-20: ${B.spent('claude'):.2f}")
        return 0
    if not a.names: sys.exit("name the job(s)")
    for name in a.names:
        if a.cmd == "collect":
            collect(name, wait=a.wait); report(name); continue
        if a.budget_usd is None: sys.exit("--budget_usd is required (no default, by design)")
        reqs = load_reqs(name); st = load_state(name)
        skip = done_ids(name) | pending_ids(st)
        todo = [r for r in reqs if r["cid"] not in skip]
        if a.cmd == "pilot":
            if B.spent("claude") + committed() + 0.05 * a.n >= a.budget_usd: sys.exit("REFUSED: the claude ledger plus pending batches would exceed the cap")
            pick = random.Random(1).sample(todo, min(a.n, len(todo)))
            print(f"{name}: pilot of {len(pick)} of {len(todo)} remaining requests", flush=True)
            create(name, pick); collect(name, wait=True)
            reqs, ok, per, left = report(name)
            if per: print(f"  projection for the {left} left: ${per*left:.2f} at the batch price")
        else:
            n, cost, per = B.job_stats("claude", name)
            if per is None: sys.exit(f"REFUSED: no measured cost for {name}; run: pilot {name}")
            proj = per * len(todo); left_cap = a.budget_usd - B.spent("claude") - committed()
            print(f"{name}: {len(todo)} to submit, measured ${per:.4f} per call, projected ${proj:.2f}; "
                  f"claude spent ${B.spent('claude'):.2f} plus ${committed():.2f} pending, of cap ${a.budget_usd:.2f}", flush=True)
            if proj > left_cap: sys.exit(f"REFUSED: projected ${proj:.2f} exceeds the ${left_cap:.2f} left under the cap")
            if todo: create(name, todo)
            print("  now run: collect " + name + " --wait")
    return 0


if __name__ == "__main__":
    sys.exit(main())
