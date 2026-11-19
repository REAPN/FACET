#!/usr/bin/env python3
import argparse, json, sys
from pathlib import Path
import pandas as pd

import rerank_ambiguous_pairs_api_v3 as R
import rerank_independent_judge as RIJ
import judge_backends as JB

_VERDICT_COLS = ["rerank_action", "comparable_observable", "evidence_scope",
                 "behavioral_analog_type", "strict_eligible", "broad_eligible", "reason"]


def gpt_raw_targets(gpt_ref_dir: Path):
    out, seen = [], set()
    for line in (gpt_ref_dir / "02_rerank_raw.jsonl").open("r", encoding="utf-8"):
        if line.strip():
            t = json.loads(line).get("target_id")
            if t is not None and t not in seen:
                seen.add(t); out.append(t)
    return out


def gpt_verdict_store(filled_tsv: Path):
    d = pd.read_csv(filled_tsv, sep="\t")
    d = d[d["rerank_action"].notna()]
    store = {}
    for _, r in d.iterrows():
        store[(str(r["target_id"]), str(r["mp_id"]), str(r.get("mp_term", "")))] = {c: r.get(c) for c in _VERDICT_COLS}
    return store


def make_bundle_call(backend, model, system, store=None, miss=None):
    def _call(client=None, model=model, target_id="", hpo_label="", target_text="", domain="", bundle=None, seed=1):
        if backend == "cached":
            sel = []
            for i, (_, r) in enumerate(bundle.iterrows(), start=1):
                key = (str(target_id), str(r["mp_id"]), str(r.get("mp_term", "")))
                v = store.get(key)
                if v is None:
                    miss.append(key); continue
                sel.append({"candidate_index": i, **{c: v[c] for c in _VERDICT_COLS}})
            return {"target_id": target_id, "selected_candidates": sel}
        if backend == "stub":
            return RIJ.stub_bundle(target_id, bundle)
        user = RIJ.build_user_prompt(target_id, hpo_label, target_text, domain, bundle)
        obj = JB.bundle_judgment(backend, model, system, user, seed=seed, schema=R.RERANK_SCHEMA)
        obj["target_id"] = target_id
        return obj
    return _call


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--disorder", required=True)
    ap.add_argument("--candidate_feature_tsv", required=True)
    ap.add_argument("--gpt_ref_dir", required=True, help="gpt run dir; 02_rerank_raw.jsonl = judged target set; 03_reranked_pairs_filled.tsv = cached verdict store")
    ap.add_argument("--backend", required=True, choices=["openai", "gemini", "claude", "stub", "cached"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--config_dir", default=".")
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    gpt_ref = Path(args.gpt_ref_dir)
    targets = set(gpt_raw_targets(gpt_ref))
    system = RIJ.dev_prompt_for(args.disorder, Path(args.config_dir))
    store = gpt_verdict_store(gpt_ref / "03_reranked_pairs_filled.tsv") if args.backend == "cached" else None
    miss = []

    _orig_iab = R.identify_ambiguous_bundles
    def _patched_iab(feat, **kw):
        bundles, all_ranked = _orig_iab(feat, **kw)
        bundles = bundles.copy()
        bundles["ambiguous"] = bundles["target_id"].isin(targets)
        return bundles, all_ranked
    R.identify_ambiguous_bundles = _patched_iab
    R.call_llm_bundle = make_bundle_call(args.backend, args.model, system, store, miss)
    if args.backend != "openai":
        R.OpenAI = (lambda *a, **k: None)

    argv = ["rerank_ambiguous_pairs_api_v3.py",
            "--candidate_feature_tsv", args.candidate_feature_tsv,
            "--outdir", args.outdir, "--seed", str(args.seed)]
    if args.model:
        argv += ["--model", args.model]
    old = sys.argv; sys.argv = argv
    try:
        R.main()
    finally:
        sys.argv = old
    extra = f" | cached MISSES (pairs gpt never judged): {len(miss)}" if args.backend == "cached" else ""
    print(f"[bundle {args.backend}/{args.disorder}] judged {len(targets)} gpt targets -> {Path(args.outdir)/'03_reranked_pairs.tsv'}{extra}")


if __name__ == "__main__":
    main()
