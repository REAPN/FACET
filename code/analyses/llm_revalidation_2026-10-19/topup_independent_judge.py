#!/usr/bin/env python3
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
import rerank_score_floor_fill_topup_v3 as T
import rerank_independent_judge as RIJ
import bundle_independent_judge as B

ap = argparse.ArgumentParser()
ap.add_argument("--rerank_dir", required=True)
ap.add_argument("--backend", required=True, choices=["claude", "gemini", "cached"])
ap.add_argument("--model", default=None)
ap.add_argument("--gpt_ref_dir", default=None, help="needed for --backend cached")
ap.add_argument("--dry_run", action="store_true")
a = ap.parse_args()
miss = []
if a.backend == "cached":
    store = B.gpt_verdict_store(Path(a.gpt_ref_dir) / "03_reranked_pairs_filled.tsv")
    T.call_llm_bundle = B.make_bundle_call("cached", a.model, RIJ.BASE_DEV_PROMPT, store, miss)
else:
    T.call_llm_bundle = B.make_bundle_call(a.backend, a.model, RIJ.BASE_DEV_PROMPT)
T.OpenAI = (lambda *x, **k: None)
argv = ["topup", "--rerank_dir", a.rerank_dir, "--allow_partial"] + (["--model", a.model] if a.model else []) + (["--dry_run"] if a.dry_run else [])
old = sys.argv; sys.argv = argv
try:
    rc = T.main()
finally:
    sys.argv = old
print(f"[topup {a.backend}] rc={rc} dir={a.rerank_dir}" + (f" cached misses {len(miss)}" if a.backend == "cached" else ""))
sys.exit(rc or 0)
