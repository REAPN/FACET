"""Analyse rater files against the sealed key. FACET expert agreement, v9 instrument (every pair rated by three raters).

Usage:  python3 _rating_analysis_v9.py _rating_pilot_2026_v9 facet_rating_*.json [--drop-flagged] [--self=G]
"""
import json, sys, math, random
from pathlib import Path
from itertools import combinations

ANCHOR_FAIL_MAX = 0
CANNOT = "cannot"
BOOT = 2000
SEED = 20260911
Z1 = 1.644854
Z = 1.959964
HW_TARGET = 0.10
PROP_RATE_SUPPORT, PROP_RATE_FLOOR = 0.85, 0.70
PROP_AC1_SUPPORT, PROP_AC1_FLOOR = 0.6, 0.4
GRADE_ORD = {"direct_analog": 4, "close_support": 3, "weak_support": 2, "mismatch": 1}
RATER_ORD = {"direct": 4, "close": 3, "weak": 2, "unrelated": 1}


def cells(pairs, w=None):
    w = w or [1.0] * len(pairs)
    a = b = c = d = 0.0
    for (r, p), wi in zip(pairs, w):
        if r and p: a += wi
        elif r and not p: b += wi
        elif p: c += wi
        else: d += wi
    return a, b, c, d


def kappa(a, b, c, d):
    n = a + b + c + d
    if n == 0: return float("nan")
    po = (a + d) / n
    pe = ((a + b) * (a + c) + (c + d) * (b + d)) / (n * n)
    return float("nan") if abs(1 - pe) < 1e-12 else (po - pe) / (1 - pe)


def ac1(a, b, c, d):
    n = a + b + c + d
    if n == 0: return float("nan")
    po = (a + d) / n
    pi = ((a + b) + (a + c)) / (2 * n)
    pe = 2 * pi * (1 - pi)
    return float("nan") if abs(1 - pe) < 1e-12 else (po - pe) / (1 - pe)


def qwk(pairs):
    if not pairs: return float("nan")
    lv = sorted({x for p in pairs for x in p}); k = len(lv)
    if k < 2: return float("nan")
    idx = {v: i for i, v in enumerate(lv)}
    O = [[0.0] * k for _ in range(k)]
    for r, p in pairs: O[idx[r]][idx[p]] += 1
    n = len(pairs)
    rw = [sum(O[i]) for i in range(k)]; cw = [sum(O[i][j] for i in range(k)) for j in range(k)]
    num = den = 0.0
    for i in range(k):
        for j in range(k):
            w = ((i - j) / (k - 1.0)) ** 2
            num += w * O[i][j]; den += w * rw[i] * cw[j] / n
    return float("nan") if den == 0 else 1 - num / den


def f3(x): return "n/a" if x != x else f"{x:.3f}"
def pct(x): return "n/a" if x != x else f"{100*x:.1f} percent"
def rater_composite(a): return a["q1"] == "yes" and a["q2"] in ("direct", "close")


def load(pilot, files):
    d = Path(pilot)
    key = json.loads((d / "SEALED_KEY_do_not_open.json").read_text())
    pop = json.loads((d / "population.json").read_text())
    meta = {i["iid"]: i for i in key["items"]}
    p2i = key["pid_to_iid"]
    keep = ("iid", "block", "code", "positive", "stratum", "disorder", "cid", "tier", "grade")
    runs = []
    for f in files:
        o = json.loads(Path(f).read_text())
        rows, an_n, an_bad = [], 0, 0
        for a in o.get("answers", []):
            it = meta.get(p2i.get(a["pid"], ""), None)
            if it is None: continue
            if it["block"] == "anchor":
                an_n += 1
                if a["q1"] != CANNOT and (a["q1"] == "yes") != bool(it["expect"]): an_bad += 1
                continue
            rows.append(dict(a, **{k: it[k] for k in keep}))
        runs.append(dict(file=Path(f).name, code=o["rater"].get("code", "?"),
                         who=o["rater"].get("id", "anon"), role=o["rater"].get("role", ""),
                         rows=rows, an_n=an_n, an_bad=an_bad, flagged=an_bad > ANCHOR_FAIL_MAX))
    return key, pop, meta, runs


def first_pass(rows):
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: r.get("screen", 0)):
        if r["iid"] in seen: continue
        seen.add(r["iid"]); out.append(r)
    return out


def by_pair(runs, rside, pside):
    pairs = {}
    for run in runs:
        for r in first_pass(run["rows"]):
            if r["q1"] == CANNOT: continue
            e = pairs.setdefault(r["iid"], {"cls": bool(pside(r)), "agree": [], "rows": []})
            e["agree"].append(1.0 if bool(rside(r)) == bool(pside(r)) else 0.0)
            e.setdefault("codes", []).append(run["code"])
            e["rows"].append(r)
    return pairs


def wilson(k, n, z):
    if n == 0: return float("nan"), float("nan")
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - h) / d, (c + h) / d


def rate_block(pairs, cls, rng):
    sel = {i: e for i, e in pairs.items() if e["cls"] == cls}
    v = [sum(e["agree"]) / len(e["agree"]) for e in sel.values()]
    m = len(v); nan = float("nan")
    if m == 0:
        return dict(m=0, est=nan, maj=nan, hw=nan, hw_emp=nan, hw_rater=nan, tau=nan, lb=nan,
                    wlo=nan, whi=nan, nrat=0, se_rule=nan)
    est = sum(v) / m
    maj = sum((1.0 if x > 0.5 else 0.5 if x == 0.5 else 0.0) for x in v) / m
    se_pair = math.sqrt(est * (1 - est) / m)
    se_emp = math.sqrt(sum((x - est) ** 2 for x in v) / (m - 1) / m) if m > 1 else se_pair
    per = {}
    for e in sel.values():
        for c, a in zip(e["codes"], e["agree"]): per.setdefault(c, []).append(a)
    tau2 = 0.0
    if len(per) >= 3:
        rates = [sum(x) / len(x) for x in per.values()]
        mu = sum(rates) / len(rates)
        obs = sum((x - mu) ** 2 for x in rates) / (len(rates) - 1)
        noise = sum(x * (1 - x) / len(y) for x, y in zip(rates, per.values())) / len(rates)
        tau2 = max(0.0, obs - noise)
    R = len(per)
    se_rater = math.sqrt(se_emp ** 2 + (tau2 / R if R else 0.0))
    wlo, whi = wilson(est * m, m, Z)
    lb = est - Z1 * se_rater
    nrat = sum(len(e["agree"]) for e in sel.values())
    return dict(m=m, est=est, maj=maj, hw=Z * se_pair, hw_emp=Z * se_emp, hw_rater=Z * se_rater,
                tau=math.sqrt(tau2), lb=lb, wlo=wlo, whi=whi, nrat=nrat, se_rule=se_rater)


def weighted_rows(runs, wmul=None):
    rows = [r for run in runs for r in first_pass(run["rows"]) if r["q1"] != CANNOT]
    n_by = {}
    for r in rows: n_by[r["iid"]] = n_by.get(r["iid"], 0) + 1
    out = []
    for r in rows:
        w = 1.0 / n_by[r["iid"]]
        if wmul: w *= wmul(r)
        out.append((r, w))
    return out


def report(L, key, pop, runs, tag):
    A = L.append
    rng = random.Random(SEED)
    posN, negN = pop["positive_population"], pop["negative_population"]

    A(f"## 1. Human against the model, the two conditional rates{tag}")
    A("")
    A("Estimated over distinct pairs. Every pair is rated by three raters and contributes the share "
      "of them who agreed with the pipeline (mean rate) and whether more than half did (majority "
      "rate). The sized half-width is root p q over distinct pairs, the conservative basis the study "
      "was sized on. The empirical half-width is the standard error of the pair means, the "
      "design-based figure now that a pair's value averages three ratings. The rater half-width adds "
      "the between-rater spread (tau, the standard deviation of rater leniency after binomial noise "
      "is removed) divided by the rater count. The lower bound is one-sided 95 percent on the "
      "rater-adjusted empirical standard error and is the one the decision rule reads.")
    A("")
    A("| comparison | class | distinct pairs | ratings | mean rate | majority rate | Wilson 95 percent | "
      "sized half-width | empirical half-width | rater half-width | tau | one-sided lower bound |")
    A("|---|---|---|---|---|---|---|---|---|---|---|---|")
    verdict = {}
    for ci, (title, rside, pside) in enumerate(COMPARISONS):
        pairs = by_pair(runs, rside, pside)
        for cls, cname in [(True, "confirmation, pipeline accepted"), (False, "rejection, pipeline refuted")]:
            s = rate_block(pairs, cls, rng)
            if ci == 0: verdict[cls] = s
            A(f"| {title} | {cname} | {s['m']} | {s['nrat']} | {f3(s['est'])} | {f3(s['maj'])} | "
              f"{f3(s['wlo'])} to {f3(s['whi'])} | {f3(s['hw'])} | {f3(s['hw_emp'])} | {f3(s['hw_rater'])} | {f3(s['tau'])} | {f3(s['lb'])} |")
    A("")
    if verdict and all(v["m"] for v in verdict.values()):
        c, r = verdict[True], verdict[False]
        widest = max(x["hw"] for x in (c, r)); widest_r = max((x["hw_rater"] for x in (c, r)), default=float("nan"))
        A(f"Widest sized half-width on the primary comparison {f3(widest)} against the design target "
          f"{HW_TARGET:.2f}: {'met' if widest <= HW_TARGET else 'not met'}. Widest rater-adjusted "
          f"empirical half-width {f3(widest_r)}.")
        A("")
        pts_ok = c["est"] >= PROP_RATE_SUPPORT and r["est"] >= PROP_RATE_SUPPORT
        lbs_ok = c["lb"] >= PROP_RATE_FLOOR and r["lb"] >= PROP_RATE_FLOOR
        below = c["est"] < PROP_RATE_FLOOR or r["est"] < PROP_RATE_FLOOR
        if pts_ok and lbs_ok: verdict_txt = "expert-supported"
        elif below: verdict_txt = "not expert-confirmed"
        else: verdict_txt = "measured"
        A(f"Declared rule (both point rates at or above {PROP_RATE_SUPPORT:.2f} and both one-sided "
          f"lower bounds at or above {PROP_RATE_FLOOR:.2f} for expert-supported; either point rate "
          f"below {PROP_RATE_FLOOR:.2f} for not expert-confirmed; measured otherwise): "
          f"**{verdict_txt}**. Confirmation {f3(c['est'])} (lower bound {f3(c['lb'])}), rejection "
          f"{f3(r['est'])} (lower bound {f3(r['lb'])}).")
        A("")

    A(f"## 2. Chance-corrected agreement{tag}")
    A("")
    A("Kappa is reported on each rater's own set, built 21 accepted and 21 refuted, because "
      "kappa is sensitive to how rare a class is. AC1 is reported the same way and again with the two "
      f"classes weighted back to the population, {posN} accepted and {negN} refuted.")
    A("")
    for title, rside, pside in COMPARISONS:
        core_runs = []
        A(f"**{title}**")
        A("")
        A("| rater | items rated | kappa | AC1 |")
        A("|---|---|---|---|")
        ks = []
        for run in runs:
            rows = [r for r in first_pass(run["rows"]) if r["q1"] != CANNOT]
            if not rows: continue
            cp = [(bool(rside(r)), bool(pside(r))) for r in rows]
            k = kappa(*cells(cp))
            ks.append(k)
            A(f"| {run['code']} | {len(rows)} | {f3(k)} | {f3(ac1(*cells(cp)))} |")
        good = [k for k in ks if k == k]
        cw = weighted_rows(runs)
        cpool = [(bool(rside(r)), bool(pside(r))) for r, _ in cw]
        wpool = [w for r, w in cw]
        A(f"| pooled, pair-weighted | {int(round(sum(wpool))) if wpool else 0} | "
          f"{f3(kappa(*cells(cpool, wpool)))} | {f3(ac1(*cells(cpool, wpool)))} |")
        A("")
        cids = {r["iid"]: bool(pside(r)) for r, _ in cw}
        npos = sum(1 for v in cids.values() if v); nneg = len(cids) - npos
        if npos != nneg:
            A(f"Caution: on this comparison the core splits {npos} and {nneg}, not evenly, so the "
              "kappa above is not on a balanced margin and the 0.4 and 0.6 reading does not apply "
              "to it. The core is built evenly on the strict-gate class only.")
            A("")
        if good:
            A(f"Mean kappa across raters {f3(sum(good)/len(good))}, "
              f"range {f3(min(good))} to {f3(max(good))}.")
            A("")
        pairs = by_pair(runs, rside, pside)
        Mpos = sum(1 for e in pairs.values() if e["cls"])
        Mneg = sum(1 for e in pairs.values() if not e["cls"])
        if Mpos and Mneg:
            per = pop.get("per_disorder", {})
            drawn = {}
            for e in pairs.values():
                d0 = e["rows"][0]["disorder"]; k0 = (d0, e["cls"])
                drawn[k0] = drawn.get(k0, 0) + 1
            def wm(r):
                d0 = r["disorder"]; c0 = bool(pside(r))
                if d0 in per and drawn.get((d0, c0)):
                    return (per[d0]["positive"] if c0 else per[d0]["negative"]) / drawn[(d0, c0)]
                return (posN / Mpos) if c0 else (negN / Mneg)
            aw = weighted_rows(runs, wm)
            allp = [(bool(rside(r)), bool(pside(r))) for r, _ in aw]
            allw = [w for _, w in aw]
            A(f"Population-weighted AC1 {f3(ac1(*cells(allp, allw)))}, "
              f"population-weighted kappa {f3(kappa(*cells(allp, allw)))}, weights carry each "
              "disorder and class back to its population count, descriptive only.")
            A("")

    A(f"## 3. Expert against expert{tag}")
    A("")
    core = {}
    for run in runs:
        for r in first_pass(run["rows"]):
            core.setdefault(run["code"], {})[r["iid"]] = r
    if len(core) < 2:
        A("Fewer than two runs, so this is not computable yet.")
    else:
        tot = cnt = 0; tri = {}
        for cd, rows in core.items():
            for iid, r in rows.items():
                if r["q1"] != CANNOT: tri.setdefault(iid, []).append(rater_composite(r))
        npairs3 = 0
        for iid, vs in tri.items():
            if len(vs) >= 2:
                npairs3 += 1
                for x, y in combinations(vs, 2): tot += (x == y); cnt += 1
        if cnt:
            pa = tot / cnt
            keys = [i for i, vs in tri.items() if len(vs) >= 2]; bs = []
            for _ in range(BOOT):
                t2 = c2 = 0
                for _k in range(len(keys)):
                    vs = tri[keys[rng.randrange(len(keys))]]
                    for x, y in combinations(vs, 2): t2 += (x == y); c2 += 1
                bs.append(t2 / c2)
            bs.sort()
            A(f"Mean agreement between two experts on the same pair, over every dyad of every pair rated by "
              f"at least two raters: {f3(pa)} on {npairs3} pairs ({cnt} dyads), pair bootstrap 95 percent "
              f"{f3(bs[int(0.025*BOOT)])} to {f3(bs[int(0.975*BOOT)-1])}. On an even class mixture this "
              f"corresponds to kappa {f3(2*pa-1)}. This is the ceiling any automated judge can be held to; "
              "no line attached.")
            A("")
        A("| rater dyad | shared items | agreement | kappa composite | AC1 composite |")
        A("|---|---|---|---|---|")
        cps = []
        for x, y in combinations(sorted(core), 2):
            sh = sorted(set(core[x]) & set(core[y]))
            sh = [i for i in sh if core[x][i]["q1"] != CANNOT and core[y][i]["q1"] != CANNOT]
            if not sh: continue
            cp = [(rater_composite(core[x][i]), rater_composite(core[y][i])) for i in sh]
            ag = sum(1 for a, b in cp if a == b) / len(cp)
            cps.append(kappa(*cells(cp)))
            A(f"| {x} and {y} | {len(sh)} | {f3(ag)} | {f3(kappa(*cells(cp)))} | {f3(ac1(*cells(cp)))} |")
        mp = [v for v in cps if v == v]
        if mp:
            A("")
            A(f"Mean dyad kappa {f3(sum(mp)/len(mp))} over {len(mp)} rater dyads sharing at least one block "
              "of 14 pairs; each dyad is small, so read the pair-level figure above.")
    A("")

    A(f"## 4. Descriptive breakdowns{tag}")
    A("")
    pairs = by_pair(runs, rater_composite, lambda r: bool(r["positive"]))
    for field, label in [("disorder", "disorder"), ("stratum", "stratum, S1 is the accepted class")]:
        A(f"| {label} | distinct pairs | mean agreement |")
        A("|---|---|---|")
        buckets = {}
        for e in pairs.values():
            for r in e["rows"][:1]:
                buckets.setdefault(r[field], []).append(sum(e["agree"]) / len(e["agree"]))
        for kk in sorted(buckets):
            v = buckets[kk]
            A(f"| {kk} | {len(v)} | {pct(sum(v)/len(v))} |")
        A("")

    A(f"## 5. Q2 analog grade{tag}")
    A("")
    op = [(RATER_ORD[r["q2"]], GRADE_ORD[r["grade"]]) for run in runs
          for r in first_pass(run["rows"])
          if r["q2"] in RATER_ORD and r["grade"] in GRADE_ORD]
    A(f"Quadratic weighted kappa {f3(qwk(op))} on {len(op)} ratings where both scales apply. "
      "Ratings, not distinct pairs, and secondary.")
    A("")


COMPARISONS = [
    ("composite against the strict-gate analog decision", rater_composite,
     lambda r: bool(r["positive"])),
    ("Q1 against the criterion-match tier", lambda r: r["q1"] == "yes",
     lambda r: r["tier"] == "1"),
]


def main(pilot, files, drop_flagged, self_code=None):
    key, pop, meta, runs = load(pilot, files)
    key_pid = {i["iid"]: i["pid"] for i in key["items"]}
    L = []; A = L.append
    A("# Expert agreement, computed from the sealed key (v9)")
    A("")
    A(f"Build {key['build']}, {key.get('pairs', 0)} pairs each rated by {key.get('k_per_pair', 0)} raters, "
      f"{key['n_codes']} codes, {key['n_anchor']} anchors. Positive prevalence {pct(pop['positive_prevalence'])} in the "
      f"population of {pop['rateable']} rateable pairs.")
    A("")
    A("## Runs")
    A("")
    A("| file | code | rater | anchors missed | part one rated | part two rated | status |")
    A("|---|---|---|---|---|---|---|")
    for r in runs:
        fp = first_pass(r["rows"])
        p1 = set(key["runs"].get(r["code"], {}).get("core", []))
        nc = sum(1 for x in fp if key_pid.get(x["iid"]) in p1)
        nu = len(fp) - nc
        A(f"| {r['file']} | {r['code']} | {r['who']} | {r['an_bad']} of {r['an_n']} | {nc} | {nu} | "
          f"{'FLAGGED, inattentive' if r['flagged'] else 'clean'} |")
    A("")
    codes = sorted({r["code"] for r in runs})
    dup = len(codes) != len(runs)
    if dup:
        A("Warning: two runs share a rater code, so they rated the same 42 pairs and the coverage "
          "per pair is uneven.")
        A("")
    if not runs:
        print("\n".join(L)); return

    clean = [r for r in runs if not r["flagged"]]
    primary = clean if drop_flagged else runs
    tag_p = " (flagged runs excluded)" if drop_flagged else ""
    if not primary:
        A("Every run was flagged by the anchors and --drop-flagged is set, so nothing is computed.")
        print("\n".join(L)); return
    report(L, key, pop, primary, tag_p)

    n_cannot = sum(1 for r in primary for x in first_pass(r["rows"]) if x["q1"] == CANNOT)
    if n_cannot:
        A("---")
        A("")
        A(f"# Sensitivity, {n_cannot} cannot-tell answers counted as refusals")
        A("")
        asno = [dict(r, rows=[dict(x, q1="no", q2="unrelated") if x["q1"] == CANNOT else x
                              for x in r["rows"]]) for r in primary]
        report(L, key, pop, asno, ", cannot-tell as refusal")

    if self_code:
        ext = [r for r in primary if r["code"] != self_code]
        if ext and len(ext) != len(primary):
            A("---")
            A("")
            A(f"# Sensitivity, the first author's block (code {self_code}) removed")
            A("")
            report(L, key, pop, ext, ", the first author's block removed")

    if len(clean) != len(runs) and not drop_flagged and clean:
        A("---")
        A("")
        A("# Sensitivity, flagged runs removed")
        A("")
        report(L, key, pop, clean, ", flagged removed")

    A("---")
    A("")
    A("## The declared decision rule")
    A("")
    A(f"Expert-supported when both point rates are at or above {PROP_RATE_SUPPORT:.2f} and both "
      f"one-sided 95 percent lower bounds are at or above {PROP_RATE_FLOOR:.2f}; measured when either "
      f"rate falls between {PROP_RATE_FLOOR:.2f} and {PROP_RATE_SUPPORT:.2f}; not expert-confirmed "
      f"when either falls below {PROP_RATE_FLOOR:.2f}. The lower bound reads the pair-level standard "
      "error with the between-rater component added. AC1 carries no line and is descriptive.")
    print("\n".join(L))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2: sys.exit(__doc__)
    self_code = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--self=")), None)
    main(args[0], args[1:], "--drop-flagged" in sys.argv, self_code)
