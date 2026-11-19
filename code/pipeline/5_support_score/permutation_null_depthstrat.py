#!/usr/bin/env python3
from __future__ import annotations

import argparse, json, sys, time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import permutation_null_per_genotype as P
import stage4_permutation_null as S

BEH_ROOT = "MP:0004924"


def behavioral_terms(obo: Path) -> set:
    par = defaultdict(set); cur = None
    for line in open(obo, encoding="utf-8", errors="replace"):
        line = line.rstrip("\n")
        if line == "[Term]": cur = None
        elif line.startswith("id: MP:"): cur = line[4:]
        elif line.startswith("is_a: MP:") and cur: par[cur].add(line[6:16])
    ch = defaultdict(set)
    for c, ps in par.items():
        for p in ps: ch[p].add(c)
    out = set(); stack = [BEH_ROOT]
    while stack:
        t = stack.pop()
        if t in out: continue
        out.add(t); stack.extend(ch[t])
    return out


def build_null_strat(beh_universe, other_universe, strata, mp_lookup, t_domain_arr, n_targets, n_perm, seed,
                     domains_strict, domains_broad):
    rng = np.random.default_rng(seed)
    out = {}
    for mode in ("strict", "broad"):
        P.log.info("Building stratified null for mode=%s over %d strata ...", mode, len(strata))
        for (k, b) in strata:
            if k <= 0 or b > beh_universe.size or (k - b) > other_universe.size: continue
            scores = np.zeros(n_perm, dtype=float)
            for i in range(n_perm):
                parts = []
                if b > 0: parts.append(rng.choice(beh_universe, size=b, replace=False))
                if k - b > 0: parts.append(rng.choice(other_universe, size=k - b, replace=False))
                sampled = np.concatenate(parts)
                s, _ = P.support_score(sampled.tolist(), mp_lookup, t_domain_arr, n_targets, mode,
                                       domains_strict=domains_strict, domains_broad=domains_broad)
                scores[i] = s
            out[(mode, k, b)] = scores
        P.log.info("  mode=%s done", mode)
    return out


def run(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reranked_pairs_tsv", required=True); ap.add_argument("--overall_support_tsv", required=True)
    ap.add_argument("--mouse_mp_csv", required=True); ap.add_argument("--n_permutations", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=1); ap.add_argument("--max_depth_cap", type=int, default=200)
    ap.add_argument("--outdir", required=True); ap.add_argument("--mp_obo", default="MPheno_OBO.ontology")
    ap.add_argument("--strict_domains", default=None); ap.add_argument("--broad_domains", default=None)
    ap.add_argument("--allowed_evidence_scope_strict", default=None); ap.add_argument("--allowed_evidence_scope_broad", default=None)
    ap.add_argument("--n_permutations_strat", type=int, default=None, help="draws per stratum (overrides --n_permutations)")
    args, _ = ap.parse_known_args(argv[1:])
    n_perm = args.n_permutations_strat or args.n_permutations
    csvs = lambda s: [x.strip() for x in s.split(",") if x.strip()]
    domains_strict = set(csvs(args.strict_domains)) if args.strict_domains else P.DEFAULT_STRICT_DOMAINS
    domains_broad = set(csvs(args.broad_domains)) if args.broad_domains else P.DEFAULT_BROAD_DOMAINS
    scope_strict = set(csvs(args.allowed_evidence_scope_strict)) if args.allowed_evidence_scope_strict else P.DEFAULT_ALLOWED_EVIDENCE_SCOPE_STRICT
    scope_broad = set(csvs(args.allowed_evidence_scope_broad)) if args.allowed_evidence_scope_broad else P.DEFAULT_ALLOWED_EVIDENCE_SCOPE_BROAD
    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True); t0 = time.time()

    rer = pd.read_csv(args.reranked_pairs_tsv, sep="\t", low_memory=False)
    mp_lookup, target_domain, t_to_idx, t_domain_arr, targets, rer = P.build_lookups(rer, scope_strict=scope_strict, scope_broad=scope_broad)
    n_targets = len(targets)

    mlong = pd.read_csv(args.mouse_mp_csv, sep="," if args.mouse_mp_csv.endswith(".csv") else "\t",
                        usecols=["genotype_id", "mp_id"], low_memory=False)
    beh = behavioral_terms(Path(args.mp_obo))
    universe = mlong["mp_id"].astype(str).unique()
    is_beh = np.array([m in beh for m in universe])
    beh_universe, other_universe = universe[is_beh], universe[~is_beh]
    P.log.info("universe %d MP ids: %d behavioral, %d other", universe.size, beh_universe.size, other_universe.size)
    per = mlong.drop_duplicates(["genotype_id", "mp_id"])
    k_all = per.groupby("genotype_id")["mp_id"].nunique()
    b_all = per[per["mp_id"].isin(beh)].groupby("genotype_id")["mp_id"].nunique().reindex(k_all.index).fillna(0).astype(int)
    k_cap = k_all.clip(upper=args.max_depth_cap)
    b_cap = np.minimum(b_all, k_cap).astype(int)
    depths = pd.DataFrame({"depth_k": k_cap, "depth_b": b_cap})
    depths.to_csv(outdir / "02_genotype_depths.tsv", sep="\t")
    strata = sorted(set(zip(depths["depth_k"].tolist(), depths["depth_b"].tolist())))
    P.log.info("%d (k, b) strata, %d draws each", len(strata), n_perm)

    null = build_null_strat(beh_universe, other_universe, strata, mp_lookup, t_domain_arr, n_targets, n_perm, args.seed,
                            domains_strict, domains_broad)
    rows = [dict(analysis_mode=m, depth_k=k, depth_b=b, n_perm=len(s), null_mean=float(s.mean()), null_sd=float(s.std(ddof=0)),
                 null_p95=float(np.percentile(s, 95)), null_p99=float(np.percentile(s, 99)), null_max=float(s.max()),
                 null_pct_zero=float(100 * (s == 0).mean())) for (m, k, b), s in null.items()]
    pd.DataFrame(rows).to_csv(outdir / "03_null_distribution_per_stratum.tsv", sep="\t", index=False)

    ov = pd.read_csv(args.overall_support_tsv, sep="\t", low_memory=False)
    ov["depth_k"] = ov["genotype_id"].map(depths["depth_k"]).fillna(0).astype(int)
    ov["depth_b"] = ov["genotype_id"].map(depths["depth_b"]).fillna(0).astype(int)
    if "matched_sfari_genes" in ov.columns:
        hm = ov["matched_sfari_genes"].notna() & ov["matched_sfari_genes"].astype(str).str.strip().ne("")
        ov = ov.assign(_has_match=hm.astype(int))
    else:
        ov = ov.assign(_has_match=0)
    ov = (ov.sort_values(["_has_match", "overall_support_score"], ascending=[False, False], na_position="last")
            .drop_duplicates(subset=["genotype_id", "analysis_mode"], keep="first").drop(columns=["_has_match"]))
    out_rows = []
    for _, r in ov.iterrows():
        k, b, mode = int(r["depth_k"]), int(r["depth_b"]), r["analysis_mode"]
        if k == 0: continue
        arr = null.get((mode, k, b))
        if arr is None: continue
        obs = 0.0 if pd.isna(r["overall_support_score"]) else float(r["overall_support_score"])
        n_ge = int((arr >= obs).sum()); p = (1 + n_ge) / (len(arr) + 1)
        out_rows.append(dict(genotype_id=r["genotype_id"], matched_sfari_genes=r.get("matched_sfari_genes", ""), analysis_mode=mode,
                             depth_k=k, depth_b=b, observed_score=obs, p_value=p, neg_log10_p=-float(np.log10(p)),
                             percentile_rank=100.0 * (1.0 - n_ge / len(arr)), null_p95=float(np.percentile(arr, 95)), null_max=float(arr.max())))
    pd.DataFrame(out_rows).to_csv(outdir / "04_per_genotype_pvalue.tsv", sep="\t", index=False)
    (outdir / "05_run_config.json").write_text(json.dumps(dict(
        reranked_pairs_tsv=args.reranked_pairs_tsv, overall_support_tsv=args.overall_support_tsv, mouse_mp_csv=args.mouse_mp_csv,
        n_permutations=n_perm, seed=args.seed, max_depth_cap=args.max_depth_cap, strict_domains=sorted(domains_strict),
        broad_domains=sorted(domains_broad), allowed_evidence_scope_strict=sorted(scope_strict), allowed_evidence_scope_broad=sorted(scope_broad),
        n_strata=len(strata), behavioral_universe=int(beh_universe.size), other_universe=int(other_universe.size),
        method="Permutation null stratified by (total depth k, behavioral depth b): b terms drawn from the behavioral vocabulary and k minus b from the rest. Score function of record (permutation_null_per_genotype.support_score).",
        elapsed_seconds=round(time.time() - t0, 1)), indent=2))
    P.log.info("Done in %.1fs, %d rows", time.time() - t0, len(out_rows))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True); ap.add_argument("--regime", default="off")
    ap.add_argument("--outdir_template", default=None); ap.add_argument("--n_permutations", type=int, default=2000)
    ap.add_argument("--reranked_pairs_tsv", default=None); ap.add_argument("--overall_support_tsv", default=None)
    ap.add_argument("--mouse_mp_csv", default=None)
    args = ap.parse_args()
    cfg = S.load_config(Path(args.config))
    overrides = dict(outdir_template=args.outdir_template, reranked_pairs_tsv=args.reranked_pairs_tsv,
                     overall_support_tsv=args.overall_support_tsv, mouse_mp_csv=args.mouse_mp_csv, stage3_baseline=None)
    argv = S.build_argv_for_regime(cfg, args.regime, overrides) + ["--n_permutations_strat", str(args.n_permutations)]
    print("overall_support_tsv:", argv[argv.index("--overall_support_tsv") + 1]); print("outdir:", argv[argv.index("--outdir") + 1])
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
