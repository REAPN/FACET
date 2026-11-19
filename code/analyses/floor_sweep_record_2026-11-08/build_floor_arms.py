#!/usr/bin/env python3
import json, sys
from pathlib import Path
import pandas as pd
ROOT = Path.cwd()
REF = {"ASD": "asd_pair_rerank_v3_broad_v3", "SCZ": "scz_pair_rerank_v1", "ID": "intellectualdisability_pair_rerank_v1", "NCD": "neurocognitive_pair_rerank_v1_ncdB_cf"}
FLOORS = [0.60, 0.65]
BLANK = ["rerank_action", "comparable_observable", "evidence_scope", "behavioral_analog_type", "strict_eligible", "broad_eligible"]
log = {}
for D, ref in REF.items():
    src = ROOT / f"_judgeswap/{D}_cached/03_reranked_pairs_filled.tsv"
    p = pd.read_csv(src, sep="\t", dtype=str, keep_default_na=False)
    b = pd.read_csv(ROOT / ref / "03_reranked_pairs.tsv", sep="\t", dtype=str, keep_default_na=False)
    bundle = set(zip(b.target_id[b.rerank_action.str.strip() != ""], b.mp_id[b.rerank_action.str.strip() != ""]))
    judged = p.rerank_action.str.strip() != ""
    injected = p.retrieval_channels.str.contains("inject") | p.get("matched_domain", pd.Series("", index=p.index)).eq("injected")
    infill = judged & ~injected & ~pd.Series([k in bundle for k in zip(p.target_id, p.mp_id)], index=p.index)
    ts = pd.to_numeric(p.transparent_score, errors="coerce")
    assert (ts[infill] >= 0.57 - 1e-9).all(), f"{D}: a fill pair sits below the floor of record"
    for F in FLOORS:
        q = p.copy(); drop = infill & (ts < F)
        for c in BLANK: q.loc[drop, c] = ""
        q.loc[drop, "rerank_delta"] = "0.0"; q.loc[drop, "final_pair_score"] = q.loc[drop, "transparent_score"]
        out = ROOT / f"_judgeswap/{D}_floor{int(round(F*100)):03d}"; out.mkdir(parents=True, exist_ok=True)
        q.to_csv(out / "03_reranked_pairs_filled.tsv", sep="\t", index=False)
        strict0 = int(p.strict_eligible.str.lower().eq("true").sum()); strict1 = int(q.strict_eligible.str.lower().eq("true").sum())
        log[f"{D}_{F}"] = dict(rows=len(p), judged=int(judged.sum()), fill_judged=int(infill.sum()), unjudged_now=int(drop.sum()), strict_record=strict0, strict_arm=strict1)
        print(D, F, log[f"{D}_{F}"])
(ROOT / "audit/floor_sweep_record_2026-11-08/build_floor_arms.json").write_text(json.dumps(log, indent=1))
