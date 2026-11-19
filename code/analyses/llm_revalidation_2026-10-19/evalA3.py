#!/usr/bin/env python3
import sys, json, collections, csv
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / "audit/geneclust_2026-10-08"))
import common
common.U = ROOT; common.B = ROOT / "benchmark"
from common import GOLD, auc, load_gold, load_summary, cluster_keys, cluster_boot

N = {"ASD": "ASD", "SCZ": "SCZ", "IDD": "ID", "NCD": "NCD"}
REF = {"ASD": "asd_pair_rerank_v3_broad_v3", "SCZ": "scz_pair_rerank_v1",
       "ID": "intellectualdisability_pair_rerank_v1", "NCD": "neurocognitive_pair_rerank_v1_ncdB_cf"}
MARGIN = 0.05

POSC = collections.defaultdict(set)
for r in csv.DictReader(open(ROOT / "audit/geneclust_2026-10-08/labels_corrected_2026-10-08.tsv"), delimiter="\t"):
    if r["label_corrected"] == "1":
        POSC[r["disorder"]].add(r["genotype_id"])
key, _ = cluster_keys(load_summary())


def kappa(a, b):
    a = list(a); b = list(b); n = len(a); po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = collections.Counter(a), collections.Counter(b); pe = sum(ca[k] * cb.get(k, 0) for k in ca) / n / n
    return round(po, 3), round((po - pe) / (1 - pe), 3) if pe < 1 else float("nan")


def scores_for(D, arm):
    if arm == "record":
        return None
    p = pd.read_csv(ROOT / f"_judgeswap/runs/{N[D]}_{arm}_s4_poloff/04_per_genotype_pvalue.tsv", sep="\t")
    return p[p.analysis_mode == "strict"].set_index("genotype_id")["neg_log10_p"]


def pairs_for(D, arm):
    if arm == "record":
        d = ROOT / f"_judgeswap/{N[D]}_cached/03_reranked_pairs_filled.tsv"
        if not d.exists():
            d = ROOT / REF[N[D]] / "03_reranked_pairs_filled.tsv"
    else:
        d = ROOT / f"_judgeswap/{N[D]}_{arm}/03_reranked_pairs_filled.tsv"
    return pd.read_csv(d, sep="\t", dtype=str, keep_default_na=False)


def main():
    want = [d for d in sys.argv[1:] if d in GOLD] or list(GOLD)
    arms = ["record", "openai", "claude", "gemini", "panel"]
    CONTRASTS = {"prompt_effect_openai_minus_record": ("openai", "record"),
                 "vendor_effect_claude_minus_openai": ("claude", "openai"),
                 "reference_claude_minus_record": ("claude", "record"),
                 "vendor_effect_gemini_minus_openai": ("gemini", "openai"),
                 "reference_gemini_minus_record": ("gemini", "record"),
                 "gemini_minus_claude": ("gemini", "claude"),
                 "panel_majority_minus_record": ("panel", "record"),
                 "panel_majority_minus_openai": ("panel", "openai")}
    out = {}; lines = ["# Amendment 3: judge arms on the pairs of record (corrected labels, strict, K4)", ""]
    for D in want:
        con, h, f, _, _ = GOLD[D]
        have = [a for a in arms if a == "record" or (ROOT / f"_judgeswap/runs/{N[D]}_{a}_s4_poloff/04_per_genotype_pvalue.tsv").exists()]
        res = {"arms_present": have}
        sc = {a: scores_for(D, a) for a in have}
        for pool, run in (("headline", h), ("full_pool", f)):
            g = load_gold(run, con); y = g.genotype_id.isin(POSC[D]).astype(int).to_numpy()
            cl = g.genotype_id.map(key).fillna("SINGLETON:x").to_numpy()
            S = {"record": g.score_a.to_numpy()}
            for a in have:
                if a != "record":
                    S[a] = g.genotype_id.map(sc[a]).fillna(0).to_numpy()
            draws, drop = cluster_boot(y, S, cl, 2000, 20261008)
            r = {"n": int(len(y)), "n_pos": int(y.sum()), "dropped": drop,
                 "auroc": {a: round(auc(y, S[a]), 4) for a in S}}
            for name, (x, z) in CONTRASTS.items():
                if x in S and z in S:
                    d = draws[x] - draws[z]; lo, hi = np.percentile(d, [5, 95])
                    r[name] = {"diff": round(auc(y, S[x]) - auc(y, S[z]), 4), "ci90": [round(lo, 4), round(hi, 4)],
                               "ci95": [round(v, 4) for v in np.percentile(d, [2.5, 97.5])],
                               "verdict": "equivalent" if (lo > -MARGIN and hi < MARGIN) else
                                          ("not equivalent" if (lo > MARGIN or hi < -MARGIN) else "inconclusive")}
            res[pool] = r
        P = {a: pairs_for(D, a) for a in have}
        base = P["record"]; j = base.rerank_action.str.strip().ne("").to_numpy()
        for a in have:
            assert len(P[a]) == len(base) and (P[a].mp_id.values == base.mp_id.values).all(), (D, a)
        pl = {}
        for a in have:
            pl[f"strict_{a}"] = int(P[a].strict_eligible[j].str.lower().eq("true").sum())
        for x, z in CONTRASTS.values():
            if x in P and z in P:
                sx = P[x].strict_eligible[j].str.lower().eq("true"); sz = P[z].strict_eligible[j].str.lower().eq("true")
                po, k = kappa(sx, sz); pot, kt = kappa(P[x].behavioral_analog_type[j], P[z].behavioral_analog_type[j])
                pl[f"{x}_vs_{z}"] = {"agree_strict": po, "kappa_strict": k, "agree_type": pot, "kappa_type": kt,
                                      "strict_both": int((sx & sz).sum()), f"strict_{x}_only": int((sx & ~sz).sum()),
                                      f"strict_{z}_only": int((~sx & sz).sum())}
        for arm in ("openai", "gemini"):
            raw = ROOT / f"_judgeswap/{N[D]}_{arm}/raw.jsonl"
            if arm in have and raw.exists():
                served = collections.Counter()
                for line in raw.open(encoding="utf-8"):
                    try: served[json.loads(line).get("response_model")] += 1
                    except Exception: pass
                pl[f"{arm}_served_models"] = dict(served)
        res["pairs"] = pl; out[D] = res
        hd = res["headline"]
        b0 = len(lines)
        lines += [f"## {D}", f"arms: {', '.join(have)}; headline n {hd['n']} (positives {hd['n_pos']})",
                  "| contrast | headline diff (90 percent interval) | verdict | full pool diff |", "|---|---|---|---|"]
        for name in CONTRASTS:
            if name in hd:
                fp = res["full_pool"].get(name, {}).get("diff", "")
                lines.append(f"| {name} | {hd[name]['diff']:+.4f} ({hd[name]['ci90'][0]:+.4f} to {hd[name]['ci90'][1]:+.4f}) | {hd[name]['verdict']} | {fp:+.4f} |" if fp != "" else f"| {name} | {hd[name]['diff']:+.4f} | {hd[name]['verdict']} | |")
        lines.append("AUROC per arm, headline: " + ", ".join(f"{a} {v}" for a, v in hd["auroc"].items()))
        lines.append("pair level: " + json.dumps(pl)); lines.append("")
        res["md_block"] = lines[b0:]; lines = lines[:b0]
        print(D, json.dumps(res), flush=True)
    jf = ROOT / "_judgeswap/evalA3.json"
    prev = json.loads(jf.read_text()) if jf.exists() else {}
    prev.update(out); out = {D: prev[D] for D in GOLD if D in prev}
    for D in out: lines += out[D].get("md_block", [])
    jf.write_text(json.dumps(out, indent=1))
    (ROOT / "_judgeswap/evalA3.md").write_text("\n".join(lines))
    print("wrote _judgeswap/evalA3.json and _judgeswap/evalA3.md")


if __name__ == "__main__":
    main()
