#!/usr/bin/env python3
import argparse, json, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
CH = ["embed", "lexical", "resnik", "jaccard"]
RECORD = {"embed": 0.45, "lexical": 0.25, "resnik": 0.20, "jaccard": 0.10, "lexf": 0.5}
ARMS = {"wequal": {"embed": 0.25, "lexical": 0.25, "resnik": 0.25, "jaccard": 0.25, "lexf": 1.0},
        "wlexf1": {**RECORD, "lexf": 1.0}, "wnoemb": {**RECORD, "embed": 0.0}, "wnolex": {**RECORD, "lexical": 0.0},
        "wnores": {**RECORD, "resnik": 0.0}, "wnojac": {**RECORD, "jaccard": 0.0}}
TOP_N, MARGIN, GRAY_LO, GRAY_HI, FLOOR = 5, 0.08, 0.35, 0.70, 0.57
VERDICT = ["rerank_action", "comparable_observable", "evidence_scope", "behavioral_analog_type", "strict_eligible", "broad_eligible", "reason"]
DELTA = {"promote": 0.10, "keep": 0.0, "demote": -0.10, "abstain": -0.25}


def tscore(p, w):
    num = np.zeros(len(p)); den = np.zeros(len(p))
    smiss = (pd.to_numeric(p["resnik_norm"], errors="coerce").isna() & pd.to_numeric(p["jaccard_norm"], errors="coerce").isna()).to_numpy()
    for c in CH:
        v = pd.to_numeric(p[f"{c}_norm"], errors="coerce"); m = v.notna().to_numpy()
        wc = np.full(len(p), w[c])
        if c == "lexical": wc = np.where(smiss, w[c] * w["lexf"], w[c])
        num[m] += wc[m] * v.to_numpy()[m]; den[m] += wc[m]
    return pd.Series(np.where(den > 0, num / np.where(den > 0, den, 1), 0.0), index=p.index)


def bundle_route(p, ts):
    q = p[["target_id"]].copy()
    for c in CH: q[f"{c}_norm"] = pd.to_numeric(p[f"{c}_norm"], errors="coerce")
    q["ts"] = ts.to_numpy()
    cols = ["ts", "embed_norm", "lexical_norm", "resnik_norm", "jaccard_norm"]
    route = pd.Series(False, index=p.index)
    for t, g in q.groupby("target_id", sort=False):
        g = g.sort_values(cols, ascending=False, na_position="last", kind="mergesort"); top = g.head(TOP_N)
        s1 = float(top.ts.iloc[0]); s2 = float(top.ts.iloc[1]) if len(top) > 1 else -1.0
        margin = s1 - s2 if s2 >= 0 else 1.0
        if margin <= MARGIN or GRAY_LO <= s1 <= GRAY_HI: route.loc[top.index] = True
    return route


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disorder", required=True, choices=["ASD", "SCZ", "ID", "NCD"])
    ap.add_argument("--arm", required=True, choices=list(ARMS))
    ap.add_argument("--model", default="gpt-5.4"); ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--chunk_size", type=int, default=5); ap.add_argument("--dry_run", action="store_true")
    a = ap.parse_args()
    D, arm, w = a.disorder, a.arm, ARMS[a.arm]
    src = ROOT / f"_judgeswap/{D}_{arm}/03_reranked_pairs_filled.tsv"
    p = pd.read_csv(src, sep="\t", dtype=str, keep_default_na=False)
    ts = tscore(p, w)
    assert (ts - pd.to_numeric(p.transparent_score, errors="coerce")).abs().max() < 1e-6, "arm table scores do not match the arm weights"
    injected = p.retrieval_channels.str.contains("inject") | p.get("matched_domain", pd.Series("", index=p.index)).eq("injected")
    judged = p.rerank_action.str.strip() != ""
    b = bundle_route(p, ts); fill = ~b & ((ts >= FLOOR - 1e-12) | injected)
    new = (b | fill) & ~judged
    out = ROOT / f"_judgeswap/{D}_{arm}_topup"; out.mkdir(parents=True, exist_ok=True)
    print(f"{D} {arm}: {int(new.sum())} pairs to judge ({int((new & b).sum())} bundle route, {int((new & fill).sum())} fill route) over {p.target_id[new].nunique()} anchors")
    if a.dry_run:
        p.loc[new, ["target_id", "hpo_label", "mp_id", "mp_label", "transparent_score"]].to_csv(out / "00_pairs_to_judge.tsv", sep="\t", index=False)
        print("dry run, list written to", out / "00_pairs_to_judge.tsv"); return
    from rerank_ambiguous_pairs_api_v3 import call_llm_bundle, clean
    from openai import OpenAI
    client = OpenAI()
    raw = out / "02_rerank_topup_raw.jsonl"; raw.write_text("")
    recs = []; n_calls = 0; t0 = time.time()
    todo = p[new].copy()
    for c in ["transparent_score", "embed_norm", "lexical_norm", "resnik_norm", "jaccard_norm", "n_available_channels"]:
        todo[c] = pd.to_numeric(todo[c], errors="coerce")
    todo["n_available_channels"] = todo["n_available_channels"].fillna(0).astype(int)
    todo["structural_missing"] = todo["structural_missing"].astype(str).str.lower().eq("true")
    for tid, g in todo.groupby("target_id", sort=False):
        g = g.sort_values("transparent_score", ascending=False).reset_index(drop=True)
        for s in range(0, len(g), a.chunk_size):
            chunk = g.iloc[s:s + a.chunk_size]
            try:
                obj = call_llm_bundle(client=client, model=a.model, target_id=str(tid), hpo_label=clean(g.hpo_label.iloc[0]),
                                      target_text=clean(g.target_text.iloc[0]), domain=clean(g.human_domain.iloc[0]), bundle=chunk, seed=a.seed)
            except Exception as e:
                print("call failed", tid, s, repr(e)[:200]); continue
            n_calls += 1
            with raw.open("a", encoding="utf-8") as f: f.write(json.dumps(obj) + "\n")
            for rec in obj.get("selected_candidates", []):
                ci = int(rec.get("candidate_index", 0))
                if 1 <= ci <= len(chunk):
                    row = chunk.iloc[ci - 1]
                    recs.append({"target_id": str(tid), "mp_id": str(row.mp_id), **{k: rec.get(k) for k in VERDICT}})
    v = pd.DataFrame(recs).drop_duplicates(subset=["target_id", "mp_id"], keep="last") if recs else pd.DataFrame(columns=["target_id", "mp_id"] + VERDICT)
    q = p.copy(); key = pd.MultiIndex.from_arrays([q.target_id, q.mp_id]); v = v.set_index(["target_id", "mp_id"])
    hit = key.isin(v.index)
    for c in VERDICT: q.loc[hit, c] = v.loc[key[hit], c].astype(str).to_numpy()
    d = pd.to_numeric(q.rerank_delta, errors="coerce").fillna(0.0)
    d[hit] = q.loc[hit, "rerank_action"].map(DELTA).fillna(0.0)
    q["rerank_delta"] = d.map(lambda x: repr(float(x)))
    q["final_pair_score"] = (pd.to_numeric(q.transparent_score) + d).clip(0, 1).map(lambda x: repr(float(x)))
    assert len(q.drop_duplicates(subset=["target_id", "mp_id"])) == len(q)
    q.to_csv(out / "03_reranked_pairs_filled.tsv", sep="\t", index=False)
    strict_new = int(q.loc[hit, "strict_eligible"].astype(str).str.lower().eq("true").sum())
    summ = dict(disorder=D, arm=arm, to_judge=int(new.sum()), judged=int(hit.sum()), calls=n_calls, seconds=round(time.time() - t0, 1),
                strict_before=int(p.strict_eligible.str.lower().eq("true").sum()), strict_after=int(q.strict_eligible.str.lower().eq("true").sum()),
                strict_among_new=strict_new, model=a.model, seed=a.seed)
    (out / "04_topup_summary.json").write_text(json.dumps(summ, indent=1)); print(summ)


if __name__ == "__main__":
    main()
