import json, math
from scipy.stats import norm
O = "audit_outputs/open_items_2026-10-13/"
c1 = json.load(open("c1_headline.json")); c7 = json.load(open("c7_ladder.json")); c6 = json.load(open("c6_pr.json"))
sA = json.load(open(O + "item1_stageA_results.json"))["results"] if False else None
def p_ci(est, lo, hi, null):
    se = (hi - lo) / 3.92; return 2 * (1 - norm.cdf(abs(est - null) / se)) if se > 0 else 0.0
def floorp(p): return max(p, 1 / 2001)
fam = []
for r in c1["rows"]:
    if r["analysis"] == "headline universe" and r["disorder"] in ("ASD", "SCZ", "IDD", "NCD"):
        fam.append(("discrimination AUROC > 0.5, " + r["disorder"], "F51", round(r["auroc"], 4), p_ci(r["auroc"], *r["ci_gene"], 0.5), "interval-derived"))
for D in ("ASD", "SCZ", "IDD", "NCD"):
    v = c1["convergent_K4"][D]; fam.append((f"convergent AUROC > 0.5, {D}", "F51", v["auroc"], p_ci(v["auroc"], *v["ci_gene"], 0.5), "interval-derived"))
for r in c7["rows"]:
    if r["pool"].startswith("headline") and r["disorder"] in ("ASD", "SCZ", "IDD", "NCD"):
        a = r["arm4_behavioral"]; fam.append((f"FACET minus PhenoDigm arm 4, {r['disorder']}", "F58", a["delta"], floorp(a["p_gene"]), "bootstrap"))
for r in c6:
    if r["disorder"] == "ASD" and r["pool"].startswith("headline"):
        d = r["AP difference FACET minus threshold-removed PhenoDigm"]
        fam.append(("AP difference FACET minus arm 3, ASD", "F52", d["point"], p_ci(d["point"], *d["ci_gene"], 0.0), "interval-derived"))
A = json.load(open(__import__("os").environ.get("FACET_ROOT", ".") + "/audit/open_items_2026-10-13/item1_stageA_results.json"))["results"]
for D in ("ASD", "IDD"):
    x = A[f"{D} :: primary (MeSH explode, descriptors)"]["line paper flagged"]
    x1, n1, x2, n2 = x["case"]["flagged"], x["case"]["lines"], x["control A"]["flagged"], x["control A"]["lines"]
    p = (x1 + x2) / (n1 + n2); z = (x1 / n1 - x2 / n2) / math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    fam.append((f"Stage A line-paper difference, {D}", "F66", round(x1 / n1 - x2 / n2, 4), 2 * (1 - norm.cdf(abs(z))), "two-proportion z"))
I2 = json.load(open(O + "item2_same_source.json"))["ASD"]
a = I2["convergent AUROC :: as run"]; b = I2["convergent AUROC :: variant B with symmetric control"]
se = math.sqrt(((a["ci_gene"][1] - a["ci_gene"][0]) / 3.92) ** 2 + ((b["ci_gene"][1] - b["ci_gene"][0]) / 3.92) ** 2)
dlt = b["auroc"] - a["auroc"]
fam.append(("convergent AUROC drop under claim-paper removal, ASD", "F61", round(dlt, 4), 2 * (1 - norm.cdf(abs(dlt) / se)), "interval-derived, unpaired SE (conservative)"))
assert len(fam) == 16, len(fam)
m = len(fam); order = sorted(range(m), key=lambda i: fam[i][3])
holm = [None] * m; run = 0
for r, i in enumerate(order):
    run = max(run, min(1, (m - r) * fam[i][3])); holm[i] = run
bh = [None] * m; prev = 1
for r in range(m - 1, -1, -1):
    i = order[r]; prev = min(prev, fam[i][3] * m / (r + 1)); bh[i] = prev
out = [dict(claim=c, finding=f, estimate=float(e), p=float(p), p_kind=k, p_holm=holm[i], q_bh=bh[i], holm_sig_005=bool(holm[i] < 0.05)) for i, (c, f, e, p, k) in enumerate(fam)]
for o in out: print(f"{o['claim'][:55]:55s} {o['finding']} est {o['estimate']:+.4f} p {o['p']:.2e} Holm {o['p_holm']:.3g} {'*' if o['holm_sig_005'] else ''}")
json.dump(dict(note="Abstract family specified after results (Amendment 5). Multiplicity control, not a confirmatory test.", family=out),
          open(O + "item5c_abstract_family.json", "w"), indent=1)
print("survive Holm:", sum(o["holm_sig_005"] for o in out), "of", m)
