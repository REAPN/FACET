#!/usr/bin/env python3
import csv, io, json, math, random, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
import _rating_analysis_v9 as RA

ROOT = Path.cwd(); OUT = ROOT / "audit/llm_revalidation_2026-10-19"
DIRS = {"ASD": "ASD", "SCZ": "SCZ", "ID": "ID", "IDD": "ID", "NCD": "NCD"}
ARMS = ["openai", "claude", "gemini"]; ALL = ["record"] + ARMS
G = {"direct_analog": 0, "close_support": 1, "weak_support": 2, "mechanistic_only": 3, "mismatch": 3, "": 3}
RG = {"direct": 0, "close": 1, "weak": 2, "unrelated": 3}
B = 4000; rng = random.Random(20261028)


def truthy(s): return (s or "").strip().lower() in ("true", "1", "yes")


def arm_fields(D, arm):
    f = ROOT / f"_judgeswap/{DIRS[D]}_{arm}/03_reranked_pairs_filled.tsv"; v = {}
    for r in csv.DictReader(io.open(f, encoding="utf-8", errors="replace"), delimiter="\t"):
        if not r["rerank_action"].strip(): continue
        k = (r["hpo_id"].strip(), r["mp_id"].strip())
        cur = v.get(k)
        new = dict(strict=truthy(r["strict_eligible"]), comp=truthy(r["comparable_observable"]), grade=G.get(r["behavioral_analog_type"].strip(), 3))
        if cur is None or (new["strict"] and not cur["strict"]): v[k] = new
    return v


def wkappa(a, b, k=4):
    n = len(a); O = [[0.0] * k for _ in range(k)]
    for x, y in zip(a, b): O[x][y] += 1
    rw = [sum(O[i]) for i in range(k)]; cw = [sum(O[i][j] for i in range(k)) for j in range(k)]
    num = den = 0.0
    for i in range(k):
        for j in range(k):
            w = ((i - j) / (k - 1.0)) ** 2; num += w * O[i][j]; den += w * rw[i] * cw[j] / n
    return float("nan") if den == 0 else 1 - num / den


def agree_stats(J, R):
    ag = [1.0 if (R[i] > 0.5) == J[i] else (0.5 if R[i] == 0.5 else 0.0) for i in range(len(J))]
    est = sum(ag) / len(ag); bs = []
    for _ in range(B):
        s = [rng.randrange(len(ag)) for _ in ag]; bs.append(sum(ag[i] for i in s) / len(s))
    bs.sort(); lo, hi = bs[int(0.025 * B)], bs[int(0.975 * B) - 1]
    adm = [i for i in range(len(J)) if J[i]]; ref = [i for i in range(len(J)) if not J[i]]
    conf = sum(R[i] for i in adm) / len(adm) if adm else float("nan")
    rej = sum(1 - R[i] for i in ref) / len(ref) if ref else float("nan")
    nt = [i for i in range(len(J)) if R[i] != 0.5]
    a = [J[i] for i in nt]; b = [R[i] > 0.5 for i in nt]; n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n; pa = sum(a) / n; pb = sum(b) / n; pe = pa * pb + (1 - pa) * (1 - pb)
    kp = float("nan") if pe == 1 else (po - pe) / (1 - pe)
    posw = sum(R); tp = sum(R[i] for i in adm); recall = tp / posw if posw else float("nan")
    return est, lo, hi, kp, len(adm), conf, rej, recall, posw


def main(files):
    key, pop, meta, runs = RA.load("_rating_pilot_2026_v9", files)
    rated = {}
    for run in runs:
        for r in RA.first_pass(run["rows"]):
            e = rated.setdefault(r["iid"], {"comp": [], "q1": [], "g": []})
            if r["q1"] != RA.CANNOT:
                e["comp"].append(1.0 if RA.rater_composite(r) else 0.0); e["q1"].append(1.0 if r["q1"] == "yes" else 0.0)
            if r["q2"] in RG: e["g"].append(RG[r["q2"]])
    n_items = sum(1 for i in meta.values() if i["block"] != "anchor"); n_unrated = n_items - len(rated)
    cache = {}; rows = []
    for iid, e in rated.items():
        it = meta[iid]; D = it["disorder"]
        if D not in DIRS or not e["comp"]: continue
        if D not in cache: cache[D] = {a: arm_fields(D, a) for a in ARMS}
        k = (it["hpo_id"], it["mp_id"]); v = {a: cache[D][a].get(k) for a in ARMS}
        if any(x is None for x in v.values()): continue
        v["record"] = dict(strict=bool(it["strict"]), comp=bool(it["comparable"]), grade=G.get(it["grade"] if it["grade"] != "ungraded" else "", 3))
        gm = Counter(e["g"]).most_common() if e["g"] else []
        rows.append(dict(D=D, j=v, rater=sum(e["comp"]) / len(e["comp"]), q1=sum(e["q1"]) / len(e["q1"]),
                         grade=(max(x for x, c in gm if c == gm[0][1]) if gm else None), grade_mean=(sum(e["g"]) / len(e["g"]) if e["g"] else None)))
    L = ["# Panel rules against the interim expert ratings, by question (2026-10-28)", "",
         f"{len(rows)} rated pairs of the four powered disorders with a definite rating, from {len(rated)} rated in all; {n_unrated} of {n_items} instrument pairs are not yet rated by anyone and form the held-out set for any rule chosen on this file. Agreement = share of pairs whose rule verdict matches the rater majority (ties half), pair bootstrap 95 percent interval.", ""]
    out = {"n": len(rows), "n_unrated": n_unrated, "admission": {}, "q1": {}, "grade": {}}

    def kofn(judges, field):
        rules = {}
        for k in range(1, len(judges) + 1):
            name = f"at least {k} of {len(judges)} ({'+'.join(judges)})"
            rules[name] = lambda r, k=k, js=judges, f=field: sum(1 for a in js if r["j"][a][f]) >= k
        return rules

    for title, field, target, keyname in (("## Admission (strict eligibility) against the raters' composite verdict", "strict", "rater", "admission"),
                                           ("## Question 1 (belongs to the criterion) against the judges' comparable_observable", "comp", "q1", "q1"),
                                           ("## Question 1 (belongs to the criterion) against the judges' strict eligibility", "strict", "q1", "q1_strict")):
        L += [title, "", "| rule | admits | agreement (95 percent) | kappa | confirmation of admitted | rejection of refused |", "|---|---|---|---|---|---|"]
        rules = {a: (lambda r, a=a, f=field: r["j"][a][f]) for a in ALL}
        rules.update(kofn(ALL, field)); rules.update(kofn(ARMS, field))
        out.setdefault(keyname, {})
        for name, fn in rules.items():
            J = [bool(fn(r)) for r in rows]; R = [r[target] for r in rows]
            est, lo, hi, kp, nadm, conf, rej, recall, posw = agree_stats(J, R)
            out[keyname][name] = dict(admits=nadm, agreement=round(est, 3), ci=[round(lo, 3), round(hi, 3)], kappa=round(kp, 3), conf=round(conf, 3), rej=round(rej, 3))
            L.append(f"| {name} | {nadm} | {est:.3f} ({lo:.3f} to {hi:.3f}) | {kp:.3f} | {conf:.3f} | {rej:.3f} | recall {recall:.3f} of {posw:.1f} rater-admitted |")
        L.append("")
    gr = [r for r in rows if r["grade"] is not None]
    L += ["## Question 2 (analog grade) against the judges' grade", "", f"{len(gr)} pairs with at least one definite grade. Scale direct 0, close 1, weak 2, unrelated 3. Rater grade = majority (the weaker grade on a tie). Judge aggregation: mode (record breaks a split), strictest (highest step), most generous (lowest step). Mean step difference is judge minus rater (negative = judge grades stronger than the raters).", "",
          "| judge or rule | exact agreement | within one step | quadratic weighted kappa | mean step difference |", "|---|---|---|---|---|"]
    def mode3(gs, rec):
        c = Counter(gs).most_common(); return c[0][0] if c[0][1] >= 2 else rec
    rules = {a: (lambda r, a=a: r["j"][a]["grade"]) for a in ALL}
    rules["mode of the three independents"] = lambda r: mode3([r["j"][a]["grade"] for a in ARMS], r["j"]["record"]["grade"])
    rules["mode of all four"] = lambda r: (lambda c: c[0][0] if c[0][1] >= 3 else r["j"]["record"]["grade"])(Counter([r["j"][a]["grade"] for a in ALL]).most_common())
    rules["strictest of the three independents"] = lambda r: max(r["j"][a]["grade"] for a in ARMS)
    rules["strictest of all four"] = lambda r: max(r["j"][a]["grade"] for a in ALL)
    rules["most generous of the three independents"] = lambda r: min(r["j"][a]["grade"] for a in ARMS)
    rules["most generous of all four"] = lambda r: min(r["j"][a]["grade"] for a in ALL)
    for name, fn in rules.items():
        a = [fn(r) for r in gr]; b = [r["grade"] for r in gr]
        ex = sum(x == y for x, y in zip(a, b)) / len(a); w1 = sum(abs(x - y) <= 1 for x, y in zip(a, b)) / len(a)
        md = sum(x - r["grade_mean"] for x, r in zip(a, gr)) / len(a)
        out["grade"][name] = dict(exact=round(ex, 3), within1=round(w1, 3), wkappa=round(wkappa(a, b), 3), mean_diff=round(md, 3))
        L.append(f"| {name} | {ex:.3f} | {w1:.3f} | {wkappa(a, b):.3f} | {md:+.2f} |")
    L += ["", "Caveat: 73 pairs and three of twelve raters. A rule chosen on this file is a hypothesis for the held-out pairs, not a result."]
    (OUT / "PANEL_RULES_VS_RATERS_PR_ABCDEGH_2026-11-07.md").write_text("\n".join(L)); (OUT / "PANEL_RULES_VS_RATERS_PR_ABCDEGH_2026-11-07.json").write_text(json.dumps(out, indent=1))
    print("\n".join(L))


if __name__ == "__main__":
    main([a for a in sys.argv[1:] if not a.startswith("--")])
