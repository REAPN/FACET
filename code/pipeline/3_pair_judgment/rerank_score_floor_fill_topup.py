#!/usr/bin/env python3
"""Top-up pass for the score-floor fill. Judges ONLY the pairs that the fill mask selects and that still
carry no verdict in 03_reranked_pairs_filled.tsv, then overlays the new verdicts onto that file.
Existing verdicts are never touched. The prior table is backed up before anything is written.

Usage, from the project root:
    python3 rerank_score_floor_fill_topup.py --rerank_dir intellectualdisability_pair_rerank_v1 --dry_run
    python3 rerank_score_floor_fill_topup.py --rerank_dir intellectualdisability_pair_rerank_v1
"""
from __future__ import annotations
import argparse, json, logging, os, shutil, sys, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

from rerank_ambiguous_pairs_api_v3 import call_llm_bundle, clean
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("topup")

ACTION_DELTA = {"promote": 0.10, "keep": 0.0, "demote": -0.10, "abstain": -0.25}
OVERLAY = ["rerank_action", "comparable_observable", "evidence_scope",
           "behavioral_analog_type", "strict_eligible", "broad_eligible", "reason"]


def fill_mask(df: pd.DataFrame, floor: float) -> pd.Series:
    has_action = df["rerank_action"].astype(str).str.strip().ne("") & df["rerank_action"].notna()
    score = pd.to_numeric(df["transparent_score"], errors="coerce")
    chan = df["retrieval_channels"].astype(str).str.contains("inject", case=False, na=False) \
        if "retrieval_channels" in df.columns else pd.Series(False, index=df.index)
    md = df["matched_domain"].astype(str).str.strip().eq("injected") \
        if "matched_domain" in df.columns else pd.Series(False, index=df.index)
    return (~has_action) & ((score >= floor) | chan | md)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rerank_dir", required=True)
    ap.add_argument("--score_floor", type=float, default=0.57)
    ap.add_argument("--chunk_size", type=int, default=5)
    ap.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-5.4"))
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--max_retries", type=int, default=3)
    ap.add_argument("--dry_run", action="store_true", help="list the pool and exit, no API call")
    ap.add_argument("--allow_partial", action="store_true",
                    help="write the table even if some selected rows are still unjudged")
    args = ap.parse_args()

    rd = Path(args.rerank_dir)
    p_filled = rd / "03_reranked_pairs_filled.tsv"
    if not p_filled.exists():
        log.error("missing %s", p_filled); return 2
    base = pd.read_csv(p_filled, sep="\t", dtype=str, keep_default_na=False, na_values=[])
    base["rerank_action"] = base["rerank_action"].replace("", np.nan)
    n_rows = len(base)
    n_judged_before = int(base["rerank_action"].notna().sum())
    mask = fill_mask(base, args.score_floor)
    typed = pd.read_csv(p_filled, sep="\t", low_memory=False)
    assert len(typed) == n_rows
    pool = typed[mask.values].copy()
    log.info("table %s: %d rows, %d judged, %d selected by the fill mask and still unjudged",
             p_filled, n_rows, n_judged_before, len(pool))
    if not pool.empty:
        per = pool.groupby(["target_id", "hpo_label"]).size()
        for (tid, lab), n in per.items():
            log.info("  %s  %-45s %4d rows", tid, lab[:45], n)
    if args.dry_run or pool.empty:
        log.info("dry run or nothing to do; no file written"); return 0
    if OpenAI is None:
        log.error("openai package not importable"); return 2
    client = OpenAI()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak = rd / f"03_reranked_pairs_filled.tsv.bak_pre_topup_{stamp}"
    shutil.copy2(p_filled, bak)
    log.info("backed up prior table to %s", bak)

    raw_path = rd / "02_rerank_fill_topup_raw.jsonl"
    records: List[Dict] = []
    n_calls = n_fail = 0
    t0 = time.time()
    for tid, g in pool.groupby("target_id", sort=False):
        g = g.reset_index(drop=True)
        assert pd.to_numeric(g["transparent_score"], errors="coerce").notna().all(), \
            f"target {tid}: a pool row has no transparent_score"
        target_text = clean(g["target_text"].iloc[0])
        hpo_label = clean(g["hpo_label"].iloc[0])
        domain = clean(g["human_domain"].iloc[0])
        for start in range(0, len(g), args.chunk_size):
            chunk = g.iloc[start:start + args.chunk_size]
            obj = None
            for attempt in range(1, args.max_retries + 1):
                try:
                    obj = call_llm_bundle(client=client, model=args.model, target_id=str(tid),
                                          hpo_label=hpo_label, target_text=target_text,
                                          domain=domain, bundle=chunk, seed=args.seed)
                    break
                except Exception as e:
                    log.warning("target %s chunk %d attempt %d failed: %s", tid, start, attempt, e)
                    time.sleep(2.0 * attempt)
            if obj is None:
                n_fail += 1; continue
            n_calls += 1
            with open(raw_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"target_id": str(tid), "chunk_start": int(start),
                                    "stamp": stamp, "response": obj}) + "\n")
            for rec in obj.get("selected_candidates", []):
                ci = int(rec.get("candidate_index", 0))
                if ci < 1 or ci > len(chunk):
                    continue
                row = chunk.iloc[ci - 1]
                records.append({"target_id": str(tid), "mp_id": str(row["mp_id"]),
                                "mp_term": str(row.get("mp_term", "")),
                                **{k: rec.get(k) for k in OVERLAY}})
    log.info("top-up done: %d calls, %d failed chunks, %d decisions, %.1fs",
             n_calls, n_fail, len(records), time.time() - t0)

    key = ["target_id", "mp_id", "mp_term"]
    new = pd.DataFrame(records).drop_duplicates(subset=key, keep="last") if records else pd.DataFrame(columns=key + OVERLAY)
    merged = base.merge(new, on=key, how="left", suffixes=("", "_new"))
    assert len(merged) == n_rows, "B1: merge changed the row count"
    got = merged["rerank_action_new"].notna()
    for c in OVERLAY:
        merged.loc[got, c] = merged.loc[got, c + "_new"].map(lambda v: "" if v is None else str(v))
        merged.drop(columns=[c + "_new"], inplace=True)
    deltas = merged.loc[got, "rerank_action"].map(ACTION_DELTA).fillna(0.0)
    merged.loc[got, "rerank_delta"] = deltas.map(str)
    merged.loc[got, "final_pair_score"] = (pd.to_numeric(merged.loc[got, "transparent_score"],
                                                         errors="coerce") + deltas).clip(0.0, 1.0).map(repr)
    still = fill_mask(merged.assign(rerank_action=merged["rerank_action"].replace("", np.nan)),
                      args.score_floor).sum()
    n_judged_after = int(merged["rerank_action"].notna().sum())
    log.info("judged before %d, after %d, still unjudged in pool %d", n_judged_before, n_judged_after, still)
    if still and not args.allow_partial:
        log.error("%d selected rows still unjudged; not writing. Re-run to retry, or pass --allow_partial", still)
        return 3
    kc = [c for c in key[:2] + ["hpo_id"] if c in merged.columns]
    assert len(merged.drop_duplicates(subset=kc)) == len(merged), "B1: duplicate keys"
    merged["rerank_action"] = merged["rerank_action"].fillna("")
    merged.to_csv(p_filled, sep="\t", index=False)
    log.info("wrote %s", p_filled)

    strict_after = int(pd.to_numeric(merged["strict_eligible"].replace({"True": 1, "False": 0, "true": 1, "false": 0}),
                                     errors="coerce").fillna(0).sum())
    pd.DataFrame([{
        "n_total_pairs": n_rows, "score_floor": args.score_floor, "topup_pool": int(len(pool)),
        "n_llm_calls": n_calls, "n_failed_chunks": n_fail, "n_decisions": int(len(new)),
        "n_judged_before": n_judged_before, "n_judged_after": n_judged_after,
        "still_unjudged_in_pool": int(still), "post_topup_strict_eligible": strict_after,
    }]).to_csv(rd / "04_rerank_fill_topup_summary.tsv", sep="\t", index=False)
    (rd / "09_fill_topup_run_config.json").write_text(json.dumps({
        "rerank_dir": str(rd), "score_floor": args.score_floor, "chunk_size": args.chunk_size,
        "model": args.model, "seed": args.seed, "max_retries": args.max_retries, "stamp": stamp,
        "backup": bak.name, "elapsed_seconds": round(time.time() - t0, 1),
        "note": "Top-up of the score-floor fill: judged only pool rows that carried no verdict, "
                "same prompt, schema and mask as rerank_score_floor_fill.py. Existing verdicts untouched."}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
