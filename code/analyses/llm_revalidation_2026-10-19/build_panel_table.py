#!/usr/bin/env python3
import csv, io, json, sys
from collections import Counter
from pathlib import Path
import pandas as pd
sys.path.insert(0, "audit/llm_revalidation_2026-10-19")
import rejudge_record_pairs as RJ

ROOT = Path.cwd(); ARMS = ["openai", "claude", "gemini"]


def read(p): return pd.read_csv(p, sep="\t", dtype=str, keep_default_na=False)


def fleiss(cols):
    n = len(cols); N = len(cols[0]); cats = sorted({c for col in cols for c in col})
    P = []; pj = Counter()
    for i in range(N):
        cnt = Counter(col[i] for col in cols); pj.update(cnt)
        P.append((sum(v * v for v in cnt.values()) - n) / (n * (n - 1)))
    Pbar = sum(P) / N; Pe = sum((pj[c] / (N * n)) ** 2 for c in cats)
    return float("nan") if Pe == 1 else (Pbar - Pe) / (1 - Pe)


def main():
    res = {}
    for D in ("ASD", "SCZ", "ID", "NCD"):
        rec = read(ROOT / f"_judgeswap/{D}_cached/03_reranked_pairs_filled.tsv") if (ROOT / f"_judgeswap/{D}_cached/03_reranked_pairs_filled.tsv").exists() \
            else read(ROOT / RJ.REF[D] / "03_reranked_pairs_filled.tsv")
        arms = {a: read(ROOT / f"_judgeswap/{D}_{a}/03_reranked_pairs_filled.tsv") for a in ARMS}
        for a in ARMS:
            assert len(arms[a]) == len(rec) and (arms[a]["mp_id"].values == rec["mp_id"].values).all() and (arms[a]["target_id"].values == rec["target_id"].values).all(), (D, a)
        judged = rec["rerank_action"].str.strip().ne("").to_numpy()
        out = rec.copy(); n_unan = n_maj = n_split = 0
        for i in range(len(rec)):
            if not judged[i]: continue
            for c in RJ.OVERLAY:
                if c == "reason": out.at[i, c] = "panel: " + " | ".join(f"{a}: {arms[a].at[i, c][:80]}" for a in ARMS); continue
                vals = [arms[a].at[i, c].strip() for a in ARMS]
                cnt = Counter(vals).most_common()
                out.at[i, c] = cnt[0][0] if cnt[0][1] >= 2 else rec.at[i, c]
            s = [arms[a].at[i, "strict_eligible"].strip().lower() == "true" for a in ARMS]
            if sum(s) in (0, 3): n_unan += 1
            else: n_maj += 1
            d = RJ.DELTA.get(out.at[i, "rerank_action"], 0.0)
            out.at[i, "rerank_delta"] = str(d)
            out.at[i, "final_pair_score"] = repr(float(min(1.0, max(0.0, float(rec.at[i, "transparent_score"]) + d))))
        od = ROOT / f"_judgeswap/{D}_panel"; od.mkdir(exist_ok=True)
        out.to_csv(od / "03_reranked_pairs_filled.tsv", sep="\t", index=False)
        J = [i for i in range(len(rec)) if judged[i]]
        strict_cols = [[arms[a].at[i, "strict_eligible"].strip().lower() for i in J] for a in ARMS]
        type_cols = [[arms[a].at[i, "behavioral_analog_type"].strip() for i in J] for a in ARMS]
        n_strict = {a: int(sum(1 for i in J if arms[a].at[i, "strict_eligible"].strip().lower() == "true")) for a in ARMS}
        n_strict["record"] = int(sum(1 for i in J if rec.at[i, "strict_eligible"].strip().lower() == "true"))
        n_strict["panel"] = int(sum(1 for i in J if out.at[i, "strict_eligible"].strip().lower() == "true"))
        unan_adm = sum(1 for i in J if all(arms[a].at[i, "strict_eligible"].strip().lower() == "true" for a in ARMS))
        res[D] = dict(judged=len(J), fleiss_strict=round(fleiss(strict_cols), 3), fleiss_type=round(fleiss(type_cols), 3),
                      unanimous=n_unan, majority_only=n_maj, unanimous_admit=unan_adm, strict=n_strict)
        print(D, json.dumps(res[D]), flush=True)
    (ROOT / "_judgeswap/panel_build.json").write_text(json.dumps(res, indent=1))
    print("wrote _judgeswap/{D}_panel/03_reranked_pairs_filled.tsv and _judgeswap/panel_build.json")


if __name__ == "__main__":
    main()
