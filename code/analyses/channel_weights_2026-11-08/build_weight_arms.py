#!/usr/bin/env python3
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path.cwd()
OUT = ROOT / "audit/channel_weights_2026-11-08"
REF = {"ASD": "asd_pair_rerank_v3_broad_v3", "SCZ": "scz_pair_rerank_v1",
       "ID": "intellectualdisability_pair_rerank_v1", "NCD": "neurocognitive_pair_rerank_v1_ncdB_cf"}
CH = ["embed", "lexical", "resnik", "jaccard"]
RECORD = {"embed": 0.45, "lexical": 0.25, "resnik": 0.20, "jaccard": 0.10, "lexf": 0.5}
ARMS = {
    "wequal": {"embed": 0.25, "lexical": 0.25, "resnik": 0.25, "jaccard": 0.25, "lexf": 1.0},
    "wlexf1": {**RECORD, "lexf": 1.0},
    "wnoemb": {**RECORD, "embed": 0.0},
    "wnolex": {**RECORD, "lexical": 0.0},
    "wnores": {**RECORD, "resnik": 0.0},
    "wnojac": {**RECORD, "jaccard": 0.0},
}
TOP_N, MARGIN, GRAY_LO, GRAY_HI, FLOOR = 5, 0.08, 0.35, 0.70, 0.57
BLANK = ["rerank_action", "comparable_observable", "evidence_scope", "behavioral_analog_type",
         "strict_eligible", "broad_eligible", "reason"]


def tscore(p, w):
    num = np.zeros(len(p)); den = np.zeros(len(p))
    smiss = (pd.to_numeric(p["resnik_norm"], errors="coerce").isna() & pd.to_numeric(p["jaccard_norm"], errors="coerce").isna()).to_numpy()
    for c in CH:
        v = pd.to_numeric(p[f"{c}_norm"], errors="coerce")
        m = v.notna().to_numpy()
        wc = np.full(len(p), w[c])
        if c == "lexical": wc = np.where(smiss, w[c] * w["lexf"], w[c])
        num[m] += wc[m] * v.to_numpy()[m]; den[m] += wc[m]
    return pd.Series(np.where(den > 0, num / np.where(den > 0, den, 1), 0.0), index=p.index)


def bundle_route(p, ts):
    q = p[["target_id"] + [f"{c}_norm" for c in CH]].copy()
    for c in CH: q[f"{c}_norm"] = pd.to_numeric(q[f"{c}_norm"], errors="coerce")
    q["ts"] = ts.to_numpy()
    cols = ["ts", "embed_norm", "lexical_norm", "resnik_norm", "jaccard_norm"]
    route = pd.Series(False, index=p.index); amb_targets = {}
    for t, g in q.groupby("target_id", sort=False):
        g = g.sort_values(cols, ascending=False, na_position="last", kind="mergesort")
        top = g.head(TOP_N)
        s1 = float(top.ts.iloc[0]); s2 = float(top.ts.iloc[1]) if len(top) > 1 else -1.0
        margin = s1 - s2 if s2 >= 0 else 1.0
        if margin <= MARGIN or GRAY_LO <= s1 <= GRAY_HI:
            route.loc[top.index] = True; amb_targets[t] = frozenset(top.index)
    return route, amb_targets


def routes(p, w, injected):
    ts = tscore(p, w)
    b, amb = bundle_route(p, ts)
    fill = ~b & ((ts >= FLOOR - 1e-12) | injected)
    return ts, b, fill, amb


log = {}
OUT.mkdir(parents=True, exist_ok=True)
for D, ref in REF.items():
    p = pd.read_csv(ROOT / f"_judgeswap/{D}_cached/03_reranked_pairs_filled.tsv", sep="\t", dtype=str, keep_default_na=False)
    rec = pd.read_csv(ROOT / ref / "03_reranked_pairs.tsv", sep="\t", dtype=str, keep_default_na=False)
    bundle_rec = set(zip(rec.target_id[rec.rerank_action.str.strip() != ""], rec.mp_id[rec.rerank_action.str.strip() != ""]))
    key = list(zip(p.target_id, p.mp_id))
    assert len(set(key)) == len(key), f"{D}: (target_id, mp_id) not unique"
    judged = p.rerank_action.str.strip() != ""
    injected = p.retrieval_channels.str.contains("inject") | p.get("matched_domain", pd.Series("", index=p.index)).eq("injected")
    in_bundle_rec = pd.Series([k in bundle_rec for k in key], index=p.index)
    delta = pd.to_numeric(p.rerank_delta, errors="coerce").fillna(0.0)

    ts0, b0, f0, amb0 = routes(p, RECORD, injected)
    ts_err = float((ts0 - pd.to_numeric(p.transparent_score, errors="coerce")).abs().max())
    assert ts_err < 1e-6, f"{D}: transparent score not reproduced from the normalized channels (max error {ts_err})"
    route0 = b0 | f0
    replay = dict(ts_max_abs_error=ts_err,
                  bundle_record=int(in_bundle_rec.sum()), bundle_replayed=int(b0.sum()),
                  bundle_record_not_replayed=int((in_bundle_rec & ~b0).sum()), bundle_replayed_not_record=int((b0 & ~in_bundle_rec).sum()),
                  judged_record=int(judged.sum()), judged_not_routed=int((judged & ~route0).sum()),
                  routed_not_judged=int((route0 & ~judged).sum()))
    fixed = judged & ~route0
    strict = p.strict_eligible.str.lower().eq("true")
    log[D] = {"replay": replay, "arms": {}}
    print(D, "replay", replay)

    for arm, w in ARMS.items():
        ts, b, f, amb = routes(p, w, injected)
        route = b | f | fixed
        drop = judged & ~route
        new = route & ~judged
        q = p.copy()
        q["transparent_score"] = ts.map(lambda x: repr(float(x)))
        for c in BLANK: q.loc[drop, c] = ""
        d = delta.where(~drop, 0.0)
        q["rerank_delta"] = d.map(lambda x: repr(float(x)))
        q["final_pair_score"] = (ts + d).clip(0.0, 1.0).map(lambda x: repr(float(x)))
        od = ROOT / f"_judgeswap/{D}_{arm}"; od.mkdir(parents=True, exist_ok=True)
        q.to_csv(od / "03_reranked_pairs_filled.tsv", sep="\t", index=False)
        strict_arm = strict & ~drop
        changed_bundles = sum(1 for t in set(amb0) | set(amb) if amb0.get(t) != amb.get(t))
        log[D]["arms"][arm] = dict(
            weights=w, judged_kept=int((judged & ~drop).sum()), unjudged=int(drop.sum()),
            unjudged_noninjected=int((drop & ~injected).sum()),
            need_new_judgment=int(new.sum()), need_new_judgment_bundle=int((new & b).sum()), need_new_judgment_fill=int((new & f & ~b).sum()),
            strict_record=int(strict.sum()), strict_arm=int(strict_arm.sum()), strict_lost=int((strict & drop).sum()),
            ambiguous_targets_record=len(amb0), ambiguous_targets_arm=len(amb), bundles_changed=changed_bundles,
            broad_autoadmit_record=int((~judged & (ts0 >= FLOOR)).sum()), broad_autoadmit_arm=int((~(judged & ~drop) & (ts >= FLOOR)).sum()),
            ts_spearman_vs_record=round(float(pd.Series(ts).rank().corr(pd.Series(ts0).rank())), 4))
        print(D, arm, {k: v for k, v in log[D]["arms"][arm].items() if k != "weights"})
(OUT / "build_weight_arms.json").write_text(json.dumps(log, indent=1))
