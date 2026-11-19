#!/usr/bin/env python3
import csv, io, json, math, random, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
import _rating_analysis_v9 as RA

ROOT = Path.cwd(); OUT = ROOT / "audit/llm_revalidation_2026-10-19"
DIRS = {"ASD": "ASD", "SCZ": "SCZ", "ID": "ID", "IDD": "ID", "NCD": "NCD"}
ARMS = ["openai", "claude", "gemini"]
B = 4000; rng = random.Random(20261028)


def truthy(s): return (s or "").strip().lower() in ("true", "1", "yes")


def arm_verdicts(D, arm):
    f = ROOT / f"_judgeswap/{DIRS[D]}_{arm}/03_reranked_pairs_filled.tsv"
    v = {}
    for r in csv.DictReader(io.open(f, encoding="utf-8", errors="replace"), delimiter="\t"):
        k = (r["hpo_id"].strip(), r["mp_id"].strip())
        v[k] = v.get(k, False) or truthy(r.get("strict_eligible"))
    return v


def kappa(a, b):
    n = len(a); po = sum(x == y for x, y in zip(a, b)) / n
    pa = sum(a) / n; pb = sum(b) / n; pe = pa * pb + (1 - pa) * (1 - pb)
    return po, (float("nan") if pe == 1 else (po - pe) / (1 - pe))


def main(files):
    key, pop, meta, runs = RA.load("_rating_pilot_2026_v9", files)
    pairs = {}
    for run in runs:
        for r in RA.first_pass(run["rows"]):
            if r["q1"] == RA.CANNOT: continue
            e = pairs.setdefault(r["iid"], {"comp": [], "q1": []})
            e["comp"].append(1.0 if RA.rater_composite(r) else 0.0); e["q1"].append(1.0 if r["q1"] == "yes" else 0.0)
    rows = []
    cache = {}
    for iid, e in pairs.items():
        it = meta[iid]; D = it["disorder"]
        if D not in DIRS: continue
        k = (it["hpo_id"], it["mp_id"])
        if D not in cache: cache[D] = {a: arm_verdicts(D, a) for a in ARMS}
        v = {a: cache[D][a].get(k) for a in ARMS}
        if any(x is None for x in v.values()): print(f"  unmatched pair in {D}: {k}"); continue
        rows.append(dict(iid=iid, D=D, record=bool(it["strict"]), stratum=it["stratum"], **v,
                         rater=sum(e["comp"]) / len(e["comp"]), rater_q1=sum(e["q1"]) / len(e["q1"]), k=len(e["comp"])))
    n_mdd = sum(1 for iid in pairs if meta[iid]["disorder"] not in DIRS)
    configs = {"record": lambda r: r["record"],
               "gpt-5.4 designed prompt": lambda r: r["openai"],
               "claude-opus-4-8": lambda r: r["claude"],
               "gemini-2.5-pro": lambda r: r["gemini"],
               "majority of the three independents": lambda r: (r["openai"] + r["claude"] + r["gemini"]) >= 2,
               "all three independents": lambda r: r["openai"] and r["claude"] and r["gemini"],
               "any independent": lambda r: r["openai"] or r["claude"] or r["gemini"],
               "majority of four (record included)": lambda r: (r["record"] + r["openai"] + r["claude"] + r["gemini"]) >= 3,
               "record and majority of the three": lambda r: r["record"] and (r["openai"] + r["claude"] + r["gemini"]) >= 2}
    L = ["# Panel of judges against the interim expert ratings (2026-10-28)", "",
         f"Rated pairs with at least one definite rating: {len(pairs)}, of which {len(rows)} in the four powered disorders "
         f"({n_mdd} MDD pairs have no judge-swap arm). Rater verdict per pair = majority of the composite "
         f"(criterion match and analog direct or close), ties count half. Agreement = share of pairs whose judge verdict matches the rater verdict, "
         f"pair bootstrap 95 percent interval ({B} resamples). kappa = Cohen kappa against the rater majority (ties dropped).", ""]
    out = {"n_pairs": len(rows), "configs": {}}
    L += ["| configuration | admits (of rated pairs) | agreement with raters (95 percent) | kappa | confirmation of its admitted pairs | rejection of its refused pairs |", "|---|---|---|---|---|---|"]
    for name, fn in configs.items():
        J = [bool(fn(r)) for r in rows]; R = [r["rater"] for r in rows]
        ag = [1.0 if (R[i] > 0.5) == J[i] else (0.5 if R[i] == 0.5 else 0.0) for i in range(len(rows))]
        est = sum(ag) / len(ag)
        bs = []
        for _ in range(B):
            s = [rng.randrange(len(ag)) for _ in ag]; bs.append(sum(ag[i] for i in s) / len(s))
        bs.sort(); lo, hi = bs[int(0.025 * B)], bs[int(0.975 * B) - 1]
        nt = [i for i in range(len(rows)) if R[i] != 0.5]
        po, kp = kappa([J[i] for i in nt], [R[i] > 0.5 for i in nt])
        adm = [i for i in range(len(rows)) if J[i]]; ref = [i for i in range(len(rows)) if not J[i]]
        conf = sum(R[i] for i in adm) / len(adm) if adm else float("nan")
        rej = sum(1 - R[i] for i in ref) / len(ref) if ref else float("nan")
        out["configs"][name] = dict(admits=len(adm), agreement=round(est, 3), ci=[round(lo, 3), round(hi, 3)], kappa=round(kp, 3),
                                    confirmation=round(conf, 3), rejection=round(rej, 3))
        L.append(f"| {name} | {len(adm)} | {est:.3f} ({lo:.3f} to {hi:.3f}) | {kp:.3f} | {conf:.3f} (n {len(adm)}) | {rej:.3f} (n {len(ref)}) |")
    L += ["", "## Record admissions by panel support", "", "Among the rated pairs the record admitted, the raters' mean composite confirmation by the number of independent judges that also admit the pair.", "",
          "| independents admitting | pairs | mean rater confirmation | pairs with rater majority confirming |", "|---|---|---|---|"]
    out["record_admitted_by_support"] = {}
    for s in (3, 2, 1, 0):
        sel = [r for r in rows if r["record"] and (r["openai"] + r["claude"] + r["gemini"]) == s]
        if not sel: L.append(f"| {s} | 0 | | |"); continue
        m = sum(r["rater"] for r in sel) / len(sel); mj = sum(1 for r in sel if r["rater"] > 0.5)
        out["record_admitted_by_support"][s] = dict(n=len(sel), mean=round(m, 3), majority=mj)
        L.append(f"| {s} | {len(sel)} | {m:.3f} | {mj} |")
    L += ["", "## Record refusals by panel support", "", "Among the rated pairs the record refused, the raters' mean composite confirmation (a high value means the raters would admit) by the number of independent judges that admit the pair.", "",
          "| independents admitting | pairs | mean rater confirmation | pairs with rater majority confirming |", "|---|---|---|---|"]
    out["record_refused_by_support"] = {}
    for s in (3, 2, 1, 0):
        sel = [r for r in rows if not r["record"] and (r["openai"] + r["claude"] + r["gemini"]) == s]
        if not sel: L.append(f"| {s} | 0 | | |"); continue
        m = sum(r["rater"] for r in sel) / len(sel); mj = sum(1 for r in sel if r["rater"] > 0.5)
        out["record_refused_by_support"][s] = dict(n=len(sel), mean=round(m, 3), majority=mj)
        L.append(f"| {s} | {len(sel)} | {m:.3f} | {mj} |")
    L += ["", "## By disorder", "", "| disorder | rated pairs | record agreement | majority-of-three agreement | all-three agreement |", "|---|---|---|---|---|"]
    out["by_disorder"] = {}
    for D in ("ASD", "SCZ", "ID", "NCD"):
        sel = [r for r in rows if r["D"] == D]
        if not sel: continue
        def agr(fn):
            a = [1.0 if (r["rater"] > 0.5) == bool(fn(r)) else (0.5 if r["rater"] == 0.5 else 0.0) for r in sel]
            return sum(a) / len(a)
        v = (agr(configs["record"]), agr(configs["majority of the three independents"]), agr(configs["all three independents"]))
        out["by_disorder"][D] = dict(n=len(sel), record=round(v[0], 3), majority3=round(v[1], 3), all3=round(v[2], 3))
        L.append(f"| {D} | {len(sel)} | {v[0]:.3f} | {v[1]:.3f} | {v[2]:.3f} |")
    L += ["", "Caveat: the 168 pairs were drawn by the record's own class (84 admitted, 84 refused), so the panel's admissions outside the record's admitted class are rated only where they fall among the 84 refused pairs sampled, and three of twelve raters have returned."]
    (OUT / "PANEL_VS_RATERS_2026-10-28.md").write_text("\n".join(L)); (OUT / "PANEL_VS_RATERS_2026-10-28.json").write_text(json.dumps(out, indent=1))
    print("\n".join(L))


if __name__ == "__main__":
    main([a for a in sys.argv[1:] if not a.startswith("--")])
