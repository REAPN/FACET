import sys, json, collections, math
sys.path.insert(0, ".")
import importlib.util
spec = importlib.util.spec_from_file_location("v9", "_rating_analysis_v9.py"); v9 = importlib.util.module_from_spec(spec); spec.loader.exec_module(v9)
key, pop, meta, runs = v9.load("_rating_pilot_2026_v9", sys.argv[1:])
R = [dict(r, rater=run["code"], role=run["role"]) for run in runs for r in v9.first_pass(run["rows"])]
GR = {"direct_analog": "direct", "close_support": "close", "weak_support": "weak", "mismatch": "unrelated"}
ORD = {"unrelated": 1, "weak": 2, "close": 3, "direct": 4}
L = []; A = L.append
def wil(k, n):
    if n == 0: return ""
    lo, hi = v9.wilson(k, n, v9.Z); return f"{lo:.2f} to {hi:.2f}"
def cls(r): return "accepted" if r["positive"] else "refused"
def comp(r): return r["q1"] == "yes" and r["q2"] in ("direct", "close")
A("# Expert ratings decomposed, interim (raters B, C and E), 2026-10-20"); A("")
A(f"Ratings: {len(R)} on {len({r['iid'] for r in R})} distinct pairs. Unit is the rating unless a table says distinct pairs. Descriptive only: three raters, small cells."); A("")
A("## 1. What raters answered, by pipeline class"); A("")
A("| Pipeline class | Ratings | Q1 yes | Q1 no | Q1 cannot tell | Composite yes (Q1 yes and Q2 close or direct) |"); A("|---|---|---|---|---|---|")
for c in ("accepted", "refused"):
    s = [r for r in R if cls(r) == c]; n = len(s); q = collections.Counter(r["q1"] for r in s)
    A(f"| {c} | {n} | {q['yes']} ({q['yes']/n:.0%}) | {q['no']} ({q['no']/n:.0%}) | {q['cannot']} ({q['cannot']/n:.0%}) | {sum(comp(r) for r in s)} ({sum(comp(r) for r in s)/n:.0%}) |")
A("")
A("## 2. Accepted pairs: is disagreement about admission or about strength?"); A("")
s = [r for r in R if r["positive"]]; n = len(s)
c_adm = sum(r["q1"] == "no" for r in s); c_str = sum(r["q1"] == "yes" and r["q2"] in ("weak", "unrelated", "unsure") for r in s)
c_ok = sum(comp(r) for r in s); c_can = sum(r["q1"] == "cannot" for r in s)
A("| Outcome on a pair the pipeline accepted | Ratings | Share |"); A("|---|---|---|")
for lab, k in (("Agrees on both (criterion match and close or direct analog)", c_ok), ("Agrees it matches the criterion but grades the analog weak, unrelated or unsure (strength disagreement)", c_str),
               ("Says it does not match the criterion (admission disagreement)", c_adm), ("Cannot tell", c_can)):
    A(f"| {lab} | {k} | {k/n:.0%} |")
A("")
A("## 3. Analog strength: rater grade against pipeline grade (all ratings with both grades)"); A("")
cols = ["unrelated", "weak", "close", "direct", "unsure"]
A("| Pipeline grade | n | " + " | ".join(f"rater {c}" for c in cols) + " | mean rater minus pipeline (1 to 4 scale) |"); A("|---|---|" + "---|" * (len(cols) + 1))
for g in ("direct_analog", "close_support", "weak_support", "mismatch"):
    s = [r for r in R if r.get("grade") == g]
    if not s: continue
    q = collections.Counter(r["q2"] for r in s); d = [ORD[r["q2"]] - ORD[GR[g]] for r in s if r["q2"] in ORD]
    A(f"| {GR[g]} | {len(s)} | " + " | ".join(str(q[c]) for c in cols) + f" | {sum(d)/len(d):+.2f} (n {len(d)}) |")
A("")
def rate(s, f, mode):
    k = n = 0
    for r in s:
        if r["q1"] == "cannot":
            if mode == "exclude": continue
            agree = (not r["positive"]) if mode == "refusal" else True
        else:
            agree = f(r) == bool(r["positive"])
        n += 1; k += agree
    return k, n
for title, f in (("composite (criterion match and close or direct analog)", comp), ("Q1 only (criterion match)", lambda r: r["q1"] == "yes")):
    A(f"## 4. Agreement with the pipeline by disorder and class, {title}"); A("")
    A("Three treatments of cannot-tell: excluded, counted as a refusal, counted as agreement with the pipeline (the most favorable bound). Ratings, Wilson 95 percent."); A("")
    A("| Disorder | Class | Excluded | As refusal | As agreement |"); A("|---|---|---|---|---|")
    for D in sorted({r["disorder"] for r in R}):
        for c in ("accepted", "refused"):
            s = [r for r in R if r["disorder"] == D and cls(r) == c]
            if not s: continue
            cells = []
            for m in ("exclude", "refusal", "agree"):
                k, n = rate(s, f, m); cells.append(f"{k}/{n} ({k/n:.0%})" if n else "none")
            A(f"| {D} | {c} | " + " | ".join(cells) + " |")
    A("")
A("## 5. Refused pairs by rejection stratum (composite, cannot-tell excluded and as its own column)"); A("")
A("S2 broad-eligible only, S3 criterion-match tier without eligibility, S4 graded analog without tier or eligibility. S1 is the accepted class."); A("")
A("| Stratum | Ratings | Agree with pipeline (excluded) | Cannot tell |"); A("|---|---|---|---|")
for st in ("S1", "S2", "S3", "S4"):
    s = [r for r in R if r["stratum"] == st]
    if not s: continue
    k, n = rate(s, comp, "exclude"); cn = sum(r["q1"] == "cannot" for r in s)
    A(f"| {st} | {len(s)} | {k}/{n} ({k/n:.0%}, {wil(k, n)}) | {cn} ({cn/len(s):.0%}) |")
A("")
A("## 6. By rater"); A("")
A("| Rater | Role | Ratings | Cannot tell | Accepted confirmed (excluded) | Refused agreed (excluded) | Mean Q2 on accepted pairs (1 to 4) |"); A("|---|---|---|---|---|---|---|")
for code in sorted({r["rater"] for r in R}):
    s = [r for r in R if r["rater"] == code]; acc = [r for r in s if r["positive"]]; ref = [r for r in s if not r["positive"]]
    k1, n1 = rate(acc, comp, "exclude"); k2, n2 = rate(ref, comp, "exclude"); cn = sum(r["q1"] == "cannot" for r in s)
    q2 = [ORD[r["q2"]] for r in acc if r["q2"] in ORD]
    A(f"| {code} | {s[0]['role']} | {len(s)} | {cn} ({cn/len(s):.0%}) | {k1}/{n1} ({k1/n1:.0%}) | {k2}/{n2} ({k2/n2:.0%}) | {sum(q2)/len(q2):.2f} |")
A("")
A("## 7. Cannot-tell as its own outcome"); A("")
cn = [r for r in R if r["q1"] == "cannot"]
A(f"{len(cn)} of {len(R)} ratings ({len(cn)/len(R):.0%}). The LLM judge has no such option: it must admit or refuse every pair."); A("")
A("| Split | Group | Cannot tell / ratings |"); A("|---|---|---|")
for lab, fn in (("class", cls), ("disorder", lambda r: r["disorder"]), ("pipeline grade", lambda r: GR.get(r.get("grade"), "none")), ("rater", lambda r: r["rater"])):
    for gname in sorted({fn(r) for r in R}):
        s = [r for r in R if fn(r) == gname]; k = sum(r["q1"] == "cannot" for r in s)
        A(f"| {lab} | {gname} | {k}/{len(s)} ({k/len(s):.0%}) |")
q = collections.Counter(r["q2"] for r in cn)
A(""); A("Q2 given alongside a cannot-tell on Q1: " + ", ".join(f"{k} {v}" for k, v in q.most_common()) + ".")
open("audit/rater_breakdown_2026-10-20/RATER_BREAKDOWN_BCE_2026-10-20.md", "w").write("\n".join(L) + "\n"); print("\n".join(L))
