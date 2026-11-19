import csv, math, sys, collections
RUNS = {"ASD": "taxonomy_v2_full/run_ASD", "SCZ": "taxonomy_v2_full/prod_SCZ_2026-07-28",
        "ID": "taxonomy_v2_full/run_ID", "NCD": "taxonomy_v2_full/prod_NCD_2026-07-28"}
OUT = "audit/llm_revalidation_2026-10-19"
def T(x): return str(x).strip().lower() == "true"
def wilson(k, n, z=1.96):
    if n == 0: return (float("nan"),) * 2
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(c - h, 3), round(c + h, 3)
L = ["# Part C results: mouse-side classification vs the taxonomy of record (sampled design, Amendment 2)", "",
     "Agreement on admissible_directionaware within each stratum, Wilson 95 percent interval. Whole-taxonomy agreement and Cohen kappa weight each stratum by N over n.", "",
     "| Disorder | Judge | Record-admitted kept (stratum 1) | Record-not-admitted kept out (stratum 2) | Weighted agreement | Weighted kappa | item_id agreement where both admit | Estimated extra admissions in the full taxonomy |",
     "|---|---|---|---|---|---|---|---|"]
review = []
for X in sys.argv[1:]:
    for D, run in RUNS.items():
        rec = {r["mp_label"]: r for r in csv.DictReader(open(f"{run}/03_taxonomy.tsv", encoding="utf-8"), delimiter="\t")}
        smp = list(csv.DictReader(open(f"_reclass/sample/partC_sample_{D}.tsv", encoding="utf-8"), delimiter="\t"))
        try: jd = {r["mp_label"]: r for r in csv.DictReader(open(f"_reclass/{D}_{X}/03_taxonomy.tsv", encoding="utf-8"), delimiter="\t")}
        except FileNotFoundError: L.append(f"| {D} | {X} | not available | | | | | |"); continue
        miss = [s["mp_label"] for s in smp if s["mp_label"] not in jd]
        st = {"record_admitted": [], "record_not_admitted": []}; NN = {}
        for s in smp:
            if s["mp_label"] in jd: st[s["stratum"]].append(s); NN[s["stratum"]] = int(s["stratum_N"])
        a1 = sum(T(jd[s["mp_label"]]["admissible_directionaware"]) for s in st["record_admitted"]); n1 = len(st["record_admitted"])
        a2 = sum(not T(jd[s["mp_label"]]["admissible_directionaware"]) for s in st["record_not_admitted"]); n2 = len(st["record_not_admitted"])
        N1, N2 = NN.get("record_admitted", 0), NN.get("record_not_admitted", 0); Nt = N1 + N2
        aa = a1 / n1 * N1; an = N1 - aa; nn_ = a2 / n2 * N2; na = N2 - nn_
        po = (aa + nn_) / Nt; pr = N1 / Nt; pj = (aa + na) / Nt; pe = pr * pj + (1 - pr) * (1 - pj); k = (po - pe) / (1 - pe)
        both = [s for s in st["record_admitted"] if T(jd[s["mp_label"]]["admissible_directionaware"])]
        it = sum(jd[s["mp_label"]]["item_id"] == rec[s["mp_label"]]["item_id"] for s in both)
        L.append(f"| {D} | {X} | {a1}/{n1} ({a1/n1:.1%}, {wilson(a1,n1)[0]} to {wilson(a1,n1)[1]}) | {a2}/{n2} ({a2/n2:.1%}, {wilson(a2,n2)[0]} to {wilson(a2,n2)[1]}) | {po:.3f} | {k:.3f} | {it}/{len(both)} | {na:.0f} of {N2} ({(n2-a2)} in sample) |"
                 + (f" missing {len(miss)}" if miss else ""))
        for s in smp:
            if s["mp_label"] not in jd: continue
            r, j = rec[s["mp_label"]], jd[s["mp_label"]]
            if T(r["admissible_directionaware"]) != T(j["admissible_directionaware"]) or (T(r["admissible_directionaware"]) and r["item_id"] != j["item_id"]):
                review.append([D, X, s["mp_id"], s["mp_label"], s["stratum"], r["item_id"], r["admissible_directionaware"], j["item_id"], j["admissible_directionaware"],
                               j.get("direction_ok", ""), (j.get("reason", "") or "")[:300], "", ""])
with open(f"{OUT}/PARTC_REVIEW_LIST.tsv", "w", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh, delimiter="\t"); w.writerow(["disorder", "judge", "mp_id", "mp_label", "stratum", "record_item", "record_admitted", "judge_item", "judge_admitted", "judge_direction_ok", "judge_reason", "an_decision", "an_note"]); w.writerows(review)
L += ["", f"Review list: {len(review)} sampled terms where the judge and the record differ on admission or on the unit. File PARTC_REVIEW_LIST.tsv."]
open(f"{OUT}/PARTC_RESULTS.md", "w", encoding="utf-8").write("\n".join(L) + "\n"); print("\n".join(L))
