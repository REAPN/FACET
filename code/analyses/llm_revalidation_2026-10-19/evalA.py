import sys, json
sys.path.insert(0, __import__("os").environ.get("FACET_ROOT", ".") + "/audit/geneclust_2026-10-08")
exec(open(__import__("os").environ.get("FACET_ROOT", ".") + "/audit/geneclust_2026-10-08/run_geneclust.py").read().split("which = sys.argv")[0])
POSC = collections.defaultdict(set)
for r in csv.DictReader(open(__import__("os").environ.get("FACET_ROOT", ".") + "/audit/geneclust_2026-10-08/labels_corrected_2026-10-08.tsv"), delimiter="\t"):
    if r["label_corrected"] == "1": POSC[r["disorder"]].add(r["genotype_id"])
N = {"ASD": "ASD", "SCZ": "SCZ", "IDD": "ID", "NCD": "NCD"}
def kappa(a, b):
    a = list(a); b = list(b); n = len(a); po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = collections.Counter(a), collections.Counter(b); pe = sum(ca[k] * cb.get(k, 0) for k in ca) / n / n
    return po, (po - pe) / (1 - pe) if pe < 1 else float("nan")
out = {}
for X in sys.argv[1:]:
    for D, (con, h, f, pil, _) in GOLD.items():
        p = pd.read_csv(U / f"_judgeswap/runs/{N[D]}_{X}_s4_poloff/04_per_genotype_pvalue.tsv", sep="\t")
        p = p[p.analysis_mode == "strict"].set_index("genotype_id")["neg_log10_p"]
        res = {}
        for pool, run in (("headline", h), ("full_pool", f)):
            g = load_gold(run, con); y = g.genotype_id.isin(POSC[D]).astype(int).to_numpy()
            cl = g.genotype_id.map(key).fillna("SINGLETON:x").to_numpy()
            rec_s = g.score_a.to_numpy(); new_s = g.genotype_id.map(p).fillna(0).to_numpy()
            draws, drop = cluster_boot(y, {"rec": rec_s, "new": new_s}, cl, 2000, 20261008)
            d = draws["new"] - draws["rec"]; lo, hi = np.percentile(d, [5, 95])
            res[pool] = dict(auroc_record=round(auc(y, rec_s), 4), auroc_judge=round(auc(y, new_s), 4),
                             diff=round(auc(y, new_s) - auc(y, rec_s), 4), ci90=[round(lo, 4), round(hi, 4)],
                             ci95=[round(x, 4) for x in np.percentile(d, [2.5, 97.5])],
                             equivalent=bool(lo > -0.05 and hi < 0.05), dropped=drop, n_pos=int(y.sum()), n=len(y))
        a = pd.read_csv(U / f"_judgeswap/{N[D]}_cached/03_reranked_pairs_filled.tsv", sep="\t", dtype=str, keep_default_na=False)
        b = pd.read_csv(U / f"_judgeswap/{N[D]}_{X}/03_reranked_pairs_filled.tsv", sep="\t", dtype=str, keep_default_na=False)
        assert len(a) == len(b) and (a.target_id.values == b.target_id.values).all() and (a.mp_id.values == b.mp_id.values).all()
        j = a.rerank_action.str.strip().ne("").to_numpy()
        sa = a.strict_eligible[j].str.lower().eq("true"); sb = b.strict_eligible[j].str.lower().eq("true")
        po_s, k_s = kappa(sa, sb); po_t, k_t = kappa(a.behavioral_analog_type[j], b.behavioral_analog_type[j])
        res["pairs"] = dict(judged=int(j.sum()), strict_record=int(sa.sum()), strict_judge=int(sb.sum()),
                            strict_both=int((sa & sb).sum()), strict_record_only=int((sa & ~sb).sum()), strict_judge_only=int((~sa & sb).sum()),
                            agree_strict=round(po_s, 3), kappa_strict=round(k_s, 3), agree_type=round(po_t, 3), kappa_type=round(k_t, 3))
        out[f"{D}_{X}"] = res; print(D, X, json.dumps(res), flush=True)
json.dump(out, open(__import__("os").environ.get("FACET_ROOT", ".") + "/audit/geneclust_2026-10-08/judgeswap/evalA_" + "_".join(sys.argv[1:]) + ".json", "w"), indent=1)
