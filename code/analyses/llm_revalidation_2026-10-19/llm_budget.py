import glob, json, threading, time
from pathlib import Path

PRICES = {
    ("claude-opus-4-8", "batch"): (2.50, 12.50),
    ("claude-opus-4-8", "sync"): (5.00, 25.00),
    ("gemini-2.5-pro", "sync"): (1.25, 10.00),
    ("gemini-2.5-pro", "batch"): (0.625, 5.00),
}
import os
LEDGER = Path(os.environ.get("FACET_LEDGER_DIR", "_judgeswap/ledger"))
if os.environ.get("OPENAI_PRICE_IN_PER_M") and os.environ.get("OPENAI_PRICE_OUT_PER_M"):
    PRICES[("gpt-5.4", "sync")] = (float(os.environ["OPENAI_PRICE_IN_PER_M"]), float(os.environ["OPENAI_PRICE_OUT_PER_M"]))
    OPENAI_PRICE_ASSUMED = False
else:
    PRICES[("gpt-5.4", "sync")] = (2.50, 15.00)
    OPENAI_PRICE_ASSUMED = True


def usd(model, mode, tin, tout):
    if (model, mode) not in PRICES and str(model).startswith("gpt-5.4") and ("gpt-5.4", mode) in PRICES:
        PRICES[(model, mode)] = PRICES[("gpt-5.4", mode)]
    if (model, mode) not in PRICES:
        raise SystemExit(f"no price for {model} ({mode}); add it to llm_budget.PRICES before running")
    pi, po = PRICES[(model, mode)]
    return (tin * pi + tout * po) / 1e6


def _lines(pattern):
    for f in glob.glob(str(LEDGER / pattern)):
        for ln in open(f, encoding="utf-8"):
            try:
                yield json.loads(ln)
            except Exception:
                pass


def spent(backend):
    return sum(r.get("usd", 0.0) for r in _lines(f"{backend}__*.jsonl"))


def job_stats(backend, job):
    rows = list(_lines(f"{backend}__{job}.jsonl"))
    n = len(rows); c = sum(r.get("usd", 0.0) for r in rows)
    return n, c, (c / n if n else None)


class Ledger:
    def __init__(self, backend, job, model, mode, cap_usd):
        if cap_usd is None or cap_usd <= 0:
            raise SystemExit("--budget_usd is required for any API run (no default, by design)")
        usd(model, mode, 0, 0)
        LEDGER.mkdir(parents=True, exist_ok=True)
        self.f = LEDGER / f"{backend}__{job}.jsonl"
        self.backend, self.job, self.model, self.mode, self.cap = backend, job, model, mode, cap_usd
        self.lock = threading.Lock(); self.mine = 0.0; self.n = 0
        self.base = spent(backend); self.t = time.time()

    def add(self, tin, tout, note=""):
        c = usd(self.model, self.mode, tin, tout)
        with self.lock:
            with self.f.open("a", encoding="utf-8") as fh:
                mode_tag = self.mode + ("_assumed_price" if (self.backend == "openai" and OPENAI_PRICE_ASSUMED) else "")
                fh.write(json.dumps({"t": int(time.time()), "model": self.model, "mode": mode_tag,
                                     "in": int(tin), "out": int(tout), "usd": round(c, 6), "note": note}) + "\n")
            self.mine += c; self.n += 1
            if time.time() - self.t > 30:
                self.base = spent(self.backend) - self.mine; self.t = time.time()
        return c

    def total(self):
        return self.base + self.mine

    def exceeded(self):
        return self.total() >= self.cap

    def gate_full_run(self, calls_left, allow_unmeasured=False):
        n, c, per = job_stats(self.backend, self.job)
        if per is None:
            if allow_unmeasured:
                return None
            raise SystemExit(f"no measured cost for job {self.job}: run its pilot first (--max_calls 20)")
        proj = per * calls_left
        left = self.cap - self.total()
        print(f"  budget: {self.backend} spent ${self.total():.2f} of cap ${self.cap:.2f}; this job measured "
              f"${per:.4f} per call over {n} calls; {calls_left} calls left, projected ${proj:.2f}", flush=True)
        if proj > left:
            raise SystemExit(f"REFUSED: projected ${proj:.2f} exceeds the ${left:.2f} left under the cap. "
                             f"Raise --budget_usd deliberately or change the design.")
        return proj


_tl = threading.local()


def install_gemini_usage_hook():
    from google.genai import models
    orig = models.Models.generate_content
    if getattr(orig, "_facet_hooked", False):
        return

    def wrapped(self, *a, **k):
        r = orig(self, *a, **k)
        u = getattr(r, "usage_metadata", None)
        tin = getattr(u, "prompt_token_count", 0) or 0
        tout = (getattr(u, "candidates_token_count", 0) or 0) + (getattr(u, "thoughts_token_count", 0) or 0)
        tot = getattr(u, "total_token_count", 0) or 0
        tout = max(tout, tot - tin)
        _tl.last = (int(tin), int(tout), getattr(r, "model_version", None))
        return r
    wrapped._facet_hooked = True
    models.Models.generate_content = wrapped


def take_gemini_usage():
    u = getattr(_tl, "last", None); _tl.last = None
    return u


if __name__ == "__main__":
    import collections
    per = collections.defaultdict(lambda: [0, 0.0])
    for f in sorted(glob.glob(str(LEDGER / "*.jsonl"))):
        name = Path(f).stem
        for r in _lines(Path(f).name):
            per[name][0] += 1; per[name][1] += r.get("usd", 0.0)
    for name, (n, c) in sorted(per.items()):
        print(f"{name:24s} {n:6d} calls  ${c:8.2f}  ${c/n if n else 0:.4f} per call")
    for b in ("claude", "gemini", "openai"):
        print(f"{b} total since 2026-10-20: ${spent(b):.2f}")
