#!/usr/bin/env python3
import csv, io, json, random, sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
import _rating_analysis_v9 as RA
ROOT = Path.cwd(); OUT = ROOT / "audit/retrieval_vs_llm_pairs_2026-11-08"
PAIRS = {"ASD": "ASD", "SCZ": "SCZ", "ID": "ID", "IDD": "ID", "NCD": "NCD"}
B = 4000; rng = random.Random(20261108)
def f(x):
    try: return float(x)
    except: return None
def scores(D):
    p = ROOT / f"FACET_release/data/pairs/{PAIRS[D]}_judged_pairs.tsv"; s = {}
    for r in csv.DictReader(io.open(p, encoding="utf-8", errors="replace"), delimiter="\t"):
        k = (r["hpo_id"].strip(), r["mp_id"].strip())
        v = dict(t=f(r["transparent_score"]), e=f(r["text_embed_cosine"]), l=f(r["lexical_score"]), fin=f(r["final_pair_score"]))
        cur = s.get(k)
        if cur is None or (v["t"] or -1) > (cur["t"] or -1): s[k] = v
    return s
def auroc(x, y):
    pos = [a for a, b in zip(x, y) if b]; neg = [a for a, b in zip(x, y) if not b]
    if not pos or not neg: return float("nan")
    w = sum((1.0 if p > n else 0.5 if p == n else 0.0) for p in pos for n in neg); return w / (len(pos) * len(neg))
def stats(J, R):
    ag = [1.0 if (R[i] > 0.5) == J[i] else (0.5 if R[i] == 0.5 else 0.0) for i in range(len(J))]
    adm = [i for i in range(len(J)) if J[i]]; ref = [i for i in range(len(J)) if not J[i]]
    nt = [i for i in range(len(J)) if R[i] != 0.5]; a = [J[i] for i in nt]; b = [R[i] > 0.5 for i in nt]; n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n; pa = sum(a) / n; pb = sum(b) / n; pe = pa * pb + (1 - pa) * (1 - pb)
    return dict(agree=sum(ag) / len(ag), kappa=(po - pe) / (1 - pe) if pe < 1 else float("nan"), admits=len(adm),
                conf=sum(R[i] for i in adm) / len(adm) if adm else float("nan"), rej=sum(1 - R[i] for i in ref) / len(ref) if ref else float("nan"),
                recall=sum(R[i] for i in adm) / sum(R) if sum(R) else float("nan")), ag
def topk(vals, k):
    order = sorted(range(len(vals)), key=lambda i: (-(vals[i] if vals[i] is not None else -9), i)); keep = set(order[:k])
    return [i in keep for i in range(len(vals))]
def main(files):
    key, pop, meta, runs = RA.load("_rating_pilot_2026_v9", files)
    rated = {}
    for run in runs:
        for r in RA.first_pass(run["rows"]):
            e = rated.setdefault(r["iid"], [])
            if r["q1"] != RA.CANNOT: e.append(1.0 if RA.rater_composite(r) else 0.0)
    cache = {}; rows = []; miss = 0
    for iid, e in rated.items():
        it = meta[iid]; D = it["disorder"]
        if D not in PAIRS or not e: continue
        if D not in cache: cache[D] = scores(D)
        s = cache[D].get((it["hpo_id"], it["mp_id"]))
        if s is None or s["t"] is None: miss += 1; continue
        rows.append(dict(D=D, llm=bool(it["strict"]), R=sum(e) / len(e), stratum=it.get("stratum"), **s))
    R = [r["R"] for r in rows]; LLM = [r["llm"] for r in rows]; k = sum(LLM)
    rules = {"LLM admission of record": LLM,
             "retrieval alone (transparent score), top k pooled": topk([r["t"] for r in rows], k),
             "embedding alone, top k pooled": topk([r["e"] for r in rows], k)}
    within = [False] * len(rows); within_e = [False] * len(rows)
    for D in sorted(set(r["D"] for r in rows)):
        idx = [i for i, r in enumerate(rows) if r["D"] == D]; kd = sum(LLM[i] for i in idx)
        for flag, col in ((within, "t"), (within_e, "e")):
            sel = topk([rows[i][col] for i in idx], kd)
            for j, i in enumerate(idx): flag[i] = sel[j]
    rules["retrieval alone, top k within each disorder"] = within
    rules["embedding alone, top k within each disorder"] = within_e
    res = {}; ags = {}
    for name, J in rules.items():
        st, ag = stats(J, R); res[name] = st; ags[name] = ag
    n = len(rows); diffs = {}
    for name in rules:
        if name.startswith("LLM"): continue
        bs = []
        for _ in range(B):
            s = [rng.randrange(n) for _ in range(n)]
            bs.append(sum(ags["LLM admission of record"][i] - ags[name][i] for i in s) / n)
        bs.sort(); d = sum(ags["LLM admission of record"][i] - ags[name][i] for i in range(n)) / n
        diffs[name] = (d, bs[int(0.025 * B)], bs[int(0.975 * B) - 1])
    nt = [i for i in range(n) if R[i] != 0.5]; y = [R[i] > 0.5 for i in nt]
    au = {"LLM admission (binary)": auroc([1.0 if LLM[i] else 0.0 for i in nt], y),
          "retrieval transparent score": auroc([rows[i]["t"] for i in nt], y),
          "embedding cosine": auroc([rows[i]["e"] or 0 for i in nt], y),
          "final pair score (retrieval plus LLM adjustment)": auroc([rows[i]["fin"] or 0 for i in nt], y)}
    au_adm = auroc([rows[i]["t"] for i in nt if LLM[i]], [R[i] > 0.5 for i in nt if LLM[i]])
    au_ref = auroc([rows[i]["t"] for i in nt if not LLM[i]], [R[i] > 0.5 for i in nt if not LLM[i]])
    def med(v): v = sorted(v); return v[len(v) // 2] if v else float("nan")
    t_adm = med([r["t"] for r in rows if r["llm"]]); t_ref = med([r["t"] for r in rows if not r["llm"]])
    sep = auroc([r["t"] for r in rows], LLM)
    L = ["# What the LLM adds at the level of pairs (2026-11-08)", "",
         f"{n} rated pairs of the four powered disorders with a definite rating ({miss} without a retrieval score skipped). Rater verdict = majority of composite ratings, ties half. The LLM of record admits {k}; each retrieval rule admits the same number. Pair bootstrap, {B} replicates.", "",
         "| Rule | admits | agreement with raters | kappa | confirmation of admitted | rejection of refused | recall of rater-admitted |", "|---|---|---|---|---|---|---|"]
    for name, st in res.items():
        L.append(f"| {name} | {st['admits']} | {st['agree']:.3f} | {st['kappa']:.3f} | {st['conf']:.3f} | {st['rej']:.3f} | {st['recall']:.3f} |")
    L += ["", "Agreement difference, LLM minus retrieval rule (95% pair-bootstrap interval):", ""]
    for name, (d, lo, hi) in diffs.items(): L.append(f"- {name}: {d:+.3f} ({lo:+.3f} to {hi:+.3f})")
    L += ["", f"Threshold-free AUROC against the rater majority ({len(nt)} pairs, ties dropped):", ""]
    for name, v in au.items(): L.append(f"- {name}: {v:.3f}")
    L += [f"- retrieval transparent score within LLM-admitted pairs: {au_adm:.3f}; within LLM-refused pairs: {au_ref:.3f}", "",
          f"Sampling caveat: the instrument was drawn by stratum from the record's verdicts. Retrieval score separates the record's admitted from refused rated pairs at AUROC {sep:.3f} (median transparent score {t_adm:.3f} admitted against {t_ref:.3f} refused), so the instrument is not neutral between the two rules."]
    (OUT / "RESULT_retrieval_vs_llm.md").write_text("\n".join(L) + "\n")
    (OUT / "RESULT_retrieval_vs_llm.json").write_text(json.dumps(dict(n=n, k=k, rules=res, diffs={a: list(b) for a, b in diffs.items()}, auroc=au, au_within_admitted=au_adm, au_within_refused=au_ref, sampling_sep=sep), indent=1))
    print("\n".join(L))
if __name__ == "__main__":
    main([a for a in sys.argv[1:] if not a.startswith("--")])
