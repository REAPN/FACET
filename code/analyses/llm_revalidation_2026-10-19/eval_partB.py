import csv, os, collections
DS = ["ASD", "SCZ", "ID", "NCD"]
BACKENDS = ["claude", "gemini"]
OUT = "audit/llm_revalidation_2026-10-19"

def load(p):
    if not os.path.exists(p): return None
    return {r["hpo_id"]: r for r in csv.DictReader(open(p, encoding="utf-8"), delimiter="\t")}

def lab(r):
    a = str(r.get("attributable", "")).strip().lower() == "true"
    return (r.get("item_id") or "none") if a else "none"

def kappa(x, y):
    n = len(x)
    if n == 0: return float("nan")
    po = sum(a == b for a, b in zip(x, y)) / n
    cx, cy = collections.Counter(x), collections.Counter(y)
    pe = sum(cx[k] * cy.get(k, 0) for k in cx) / n / n
    return float("nan") if pe == 1 else (po - pe) / (1 - pe)

lines = ["# Part B results: independent anchor reassignment vs production", "",
         "Label compared = item_id when attributable is True, else none. Second unit reported separately.", "",
         "| Disorder | Judge | Anchors prod / judge / both | Primary-label agreement | Kappa | Attributable agreement | Second-unit agreement |",
         "|---|---|---|---|---|---|---|"]
review = collections.OrderedDict()
uni = {}
for D in DS:
    prod = load(f"target_units_{D}/03_target_criterion_units.tsv")
    judges = {}
    for B in BACKENDS:
        j = load(f"_reassign/{D}_{B}/03_target_criterion_units.tsv")
        if j is None or not j: lines.append(f"| {D} | {B} | not available | | | | |"); continue
        judges[B] = j
        both = [h for h in prod if h in j]
        x = [lab(prod[h]) for h in both]; y = [lab(j[h]) for h in both]
        att = sum((prod[h]["attributable"].lower() == "true") == (j[h]["attributable"].lower() == "true") for h in both)
        sec = sum((prod[h].get("second_item_id") or "none") == (j[h].get("second_item_id") or "none") for h in both)
        agree = sum(a == b for a, b in zip(x, y))
        lines.append(f"| {D} | {B} | {len(prod)} / {len(j)} / {len(both)} | {agree}/{len(both)} ({agree/len(both):.1%}) | {kappa(x,y):.3f} | {att}/{len(both)} | {sec}/{len(both)} |")
        for h in both:
            if lab(prod[h]) != lab(j[h]) or (prod[h].get("second_item_id") or "none") != (j[h].get("second_item_id") or "none"):
                review.setdefault((D, h), {"prod": prod[h]})[B] = j[h]
        only = [h for h in j if h not in prod]
        if only:
            lines.append(f"|  | {B}: anchors without production attribution | {', '.join(only)} | | | | |")
    if len(judges) == len(BACKENDS):
        both = [h for h in prod if all(h in judges[B] for B in BACKENDS)]
        u = sum(len({lab(prod[h])} | {lab(judges[B][h]) for B in BACKENDS}) == 1 for h in both)
        uni[D] = (u, len(both))
lines += ["", "Unanimity of all three (production + both judges): " + (", ".join(f"{D} {u}/{n}" for D, (u, n) in uni.items()) or "pending second judge"), ""]
cols = ["disorder", "hpo_id", "hpo_label", "scored_disagreement", "prod_item", "prod_second", "prod_attributable", "prod_reason"]
for B in BACKENDS: cols += [f"{B}_item", f"{B}_second", f"{B}_attributable", f"{B}_confidence", f"{B}_reason"]
cols += ["an_decision", "an_note"]
with open(f"{OUT}/PARTB_REVIEW_LIST.tsv", "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f, delimiter="\t"); w.writerow(cols)
    for (D, h), d in review.items():
        p = d["prod"]; scored = any(lab(p) != lab(d[B]) for B in BACKENDS if B in d)
        row = [D, h, p["hpo_label"], scored, p["item_id"], p.get("second_item_id"), p["attributable"], p["reason"]]
        for B in BACKENDS:
            r = d.get(B)
            row += [r["item_id"], r.get("second_item_id"), r["attributable"], r["confidence"], r["reason"]] if r else [""] * 5
        w.writerow(row + ["", ""])
ns = sum(1 for (D, h), d in review.items() if any(lab(d["prod"]) != lab(d[B]) for B in BACKENDS if B in d))
lines += [f"Review list: {len(review)} anchors ({ns} with a scored-unit or attributable disagreement, {len(review)-ns} second-unit only). File PARTB_REVIEW_LIST.tsv.", "",
          "| Disorder | HPO | Label | Production | " + " | ".join(BACKENDS) + " |", "|---|---|---|---|" + "---|" * len(BACKENDS)]
for (D, h), d in review.items():
    p = d["prod"]
    f = lambda r: f"{lab(r)} (2nd {r.get('second_item_id') or 'none'})" if r else ""
    lines.append(f"| {D} | {h} | {p['hpo_label']} | {f(p)} | " + " | ".join(f(d.get(B)) for B in BACKENDS) + " |")
open(f"{OUT}/PARTB_RESULTS.md", "w", encoding="utf-8").write("\n".join(lines) + "\n")
print("\n".join(lines))
