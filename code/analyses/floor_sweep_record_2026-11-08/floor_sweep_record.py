#!/usr/bin/env python3
import csv, io, json, sys
from collections import defaultdict
from pathlib import Path
ROOT = Path.cwd(); OUT = ROOT / "audit/floor_sweep_record_2026-11-08"
DIS = {"ASD": ("asd_pair_rerank_v3_broad_v3", "ASD"), "SCZ": ("scz_pair_rerank_v1", "SCZ"),
       "IDD": ("intellectualdisability_pair_rerank_v1", "ID"), "NCD": ("neurocognitive_pair_rerank_v1_ncdB_cf", "NCD")}
EXPORT = ROOT / "FACET_release/data/catalogue/match_export_criterion_strictonly_prev25_span1_k4_a2floor_ncdB_constructfiltered_idd20260910.tsv"
FLOORS_UP = [0.60, 0.65]; FLOORS_DOWN = [0.50, 0.55]; BASE = 0.57
def rd(p): return list(csv.DictReader(io.open(p, encoding="utf-8", errors="replace"), delimiter="\t"))
def f(x):
    try: return float(x)
    except: return None
def T(x): return (x or "").strip().lower() in ("true", "1", "yes")
export = defaultdict(set)
for r in rd(EXPORT):
    if r["source"] == "BASE": export[r["disorder"]].add((r["cid"], r["mp"]))
res = {}; L = ["# Judgment-floor sweep on the run of record (2026-11-08)", "",
               "Raising the floor removes the pairs judged by the floor route (non-injected pairs outside a bundle) below it. Injected descendants and bundle pairs are judged whatever their score. A catalogue match (criterion, admitted MP term) is affected only if every admitted pair behind it is removed.", "",
               "| Disorder | admitted pairs of record (strict, direct or close) | of them judged by the floor route | lost at 0.60 | lost at 0.65 | catalogue matches losing all pairs at 0.60 | at 0.65 | unjudged pairs in [0.50, 0.57) | in [0.55, 0.57) |",
               "|---|---|---|---|---|---|---|---|---|"]
for D, (folder, key) in DIS.items():
    units = {}
    for r in rd(ROOT / f"FACET_release/data/anchors/{key}_anchor_criterion_units.tsv"):
        if T(r.get("attributable")) and r["item_id"] not in ("", "none"): units[r["hpo_id"]] = f"{D if D != 'IDD' else 'IDD'}.{r['item_id']}"
    bundle = {(r["target_id"], r["mp_id"]) for r in rd(ROOT / folder / "03_reranked_pairs.tsv") if (r.get("rerank_action") or "").strip()}
    filled = rd(ROOT / folder / "03_reranked_pairs_filled.tsv")
    adm = []; unj_50 = unj_55 = 0
    for r in filled:
        k = (r["target_id"], r["mp_id"]); s = f(r.get("transparent_score")); judged = bool((r.get("rerank_action") or "").strip())
        if not judged and s is not None and not (("inject" in (r.get("retrieval_channels") or "")) or (r.get("matched_domain") or "") == "injected"):
            if 0.50 <= s < BASE: unj_50 += 1
            if 0.55 <= s < BASE: unj_55 += 1
        inj = ("inject" in (r.get("retrieval_channels") or "")) or (r.get("matched_domain") or "") == "injected"
        if judged and T(r.get("strict_eligible")) and (r.get("behavioral_analog_type") or "").strip() in ("direct_analog", "close_support"):
            adm.append(dict(k=k, hpo=r["hpo_id"], mp=r["mp_id"], s=s, fill=(k not in bundle) and not inj))
    ex = export.get(D, set()) | export.get(key, set())
    def support(pairs):
        sup = defaultdict(int)
        for a in pairs:
            cid = units.get(a["hpo"])
            if cid: sup[(cid, a["mp"])] += 1
        return sup
    sup0 = support(adm); ex_cids = {c for c, _ in ex}
    pref = next(iter(ex_cids)).split(".")[0] if ex_cids else D
    sup0 = {(pref + "." + c.split(".", 1)[1], m): n for (c, m), n in sup0.items()}
    unexplained = sum(1 for e in ex if e not in sup0)
    row = dict(admitted=len(adm), fill=sum(a["fill"] for a in adm), unexplained_export=unexplained, unjudged_50_57=unj_50, unjudged_55_57=unj_55)
    for F in FLOORS_UP:
        keep = [a for a in adm if not (a["fill"] and a["s"] is not None and a["s"] < F)]
        sup = {(pref + "." + c.split(".", 1)[1], m): n for (c, m), n in support(keep).items()}
        row[f"lost_{F}"] = len(adm) - len(keep)
        row[f"export_lost_{F}"] = sum(1 for e in ex if e in sup0 and e not in sup)
    res[D] = row
    L.append(f"| {D} | {row['admitted']} | {row['fill']} | {row['lost_0.6']} | {row['lost_0.65']} | {row['export_lost_0.6']} | {row['export_lost_0.65']} | {unj_50} | {unj_55} |")
L += ["", "Mapping check: catalogue matches of record with no admitted pair found in the rerank folder (descendant or injected terms resolved elsewhere): " + ", ".join(f"{D} {r['unexplained_export']}" for D, r in res.items()) + ".",
      "", "Lowering the floor to 0.55 or 0.50 adds the unjudged pairs counted in the last two columns, which need new LLM judgments under the prompt of record."]
(OUT / "RESULT_floor_sweep_record.md").write_text("\n".join(L) + "\n"); (OUT / "RESULT_floor_sweep_record.json").write_text(json.dumps(res, indent=1))
print("\n".join(L))
