#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

STRICT_DOMAINS = [
    "social_interaction",
    "communication",
    "repetitive_restricted",
    "sensory_reactivity",
]
BROAD_EXTRA_DOMAINS = [
    "developmental_support",
    "cognitive_behavioral_support",
    "motor_support",
]
BROAD_DOMAINS = STRICT_DOMAINS + BROAD_EXTRA_DOMAINS

ALLOWED_EVIDENCE_SCOPE_STRICT = {"organism_behavior", "organism_sensory", "developmental_behavior"}
ALLOWED_EVIDENCE_SCOPE_BROAD = {"organism_behavior", "organism_sensory", "developmental_behavior", "unclear"}


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".tsv", ".txt"}:
        return pd.read_csv(path, sep="\t")
    return pd.read_csv(path)


def noisy_or(scores: Sequence[float]) -> float:
    vals = [float(x) for x in scores if pd.notna(x) and float(x) > 0]
    if not vals:
        return 0.0
    prod = 1.0
    for s in vals:
        s = max(0.0, min(1.0, float(s)))
        prod *= (1.0 - s)
    return 1.0 - prod


def prepare_pair_evidence(gen_pairs: pd.DataFrame) -> pd.DataFrame:
    gp = gen_pairs.copy()
    for c in ["strict_eligible", "broad_eligible", "comparable_observable"]:
        if c in gp.columns:
            gp[c] = pd.to_numeric(gp[c], errors="coerce").fillna(0).astype(bool)
    gp["evidence_scope"] = gp.get("evidence_scope", pd.Series(index=gp.index, dtype=object)).fillna("unclear")
    gp["strict_candidate"] = (
        gp.get("strict_eligible", False)
        & gp.get("comparable_observable", False)
        & gp["evidence_scope"].isin(ALLOWED_EVIDENCE_SCOPE_STRICT)
    )
    gp["broad_candidate"] = (
        gp.get("broad_eligible", False)
        & gp.get("comparable_observable", False)
        & gp["evidence_scope"].isin(ALLOWED_EVIDENCE_SCOPE_BROAD)
    )
    gp["strict_assessable"] = (
        gp.get("comparable_observable", False)
        & gp["evidence_scope"].isin(ALLOWED_EVIDENCE_SCOPE_STRICT)
    )
    gp["broad_assessable"] = (
        gp.get("comparable_observable", False)
        & gp["evidence_scope"].isin(ALLOWED_EVIDENCE_SCOPE_BROAD)
    )
    return gp


def _weighted_noisy_or(scores: Sequence[float], weights: Sequence[float]) -> float:
    pairs = [(float(s), float(w)) for s, w in zip(scores, weights) if pd.notna(s) and float(s) > 0 and pd.notna(w) and float(w) > 0]
    if not pairs:
        return 0.0
    prod = 1.0
    for s, w in pairs:
        s = max(0.0, min(1.0, s))
        prod *= (1.0 - (w * s))
    return 1.0 - prod


def _cluster_key(row: pd.Series) -> Tuple[str, str, str]:
    anc = str(row.get("ancestor_id") or "")
    if anc and anc.lower() != "nan":
        return ("anc", anc, "")
    mpid = str(row.get("mp_id") or "")
    if mpid and mpid.lower() != "nan":
        return ("mp", mpid, "")
    term = str(row.get("mp_term") or "")
    return ("txt", term.lower().strip(), "")


def aggregate_from_pairs(gen_pairs: pd.DataFrame, support_threshold: float) -> Tuple[pd.DataFrame, pd.DataFrame]:
    gp = prepare_pair_evidence(gen_pairs)
    key_cols = ["genotype_id", "matched_sfari_genes", "target_id", "hpo_id", "hpo_label", "human_domain"]
    all_targets = gp[["target_id", "human_domain"]].drop_duplicates().copy()
    targets_by_domain = all_targets.groupby("human_domain")["target_id"].apply(list).to_dict()

    target_rows: List[Dict[str, object]] = []
    for mode in ["strict", "broad"]:
        cand_col = f"{mode}_candidate"
        assess_col = f"{mode}_assessable"
        universe = gp[key_cols + [assess_col]].groupby(key_cols, dropna=False)[assess_col].any().reset_index(name="assessable")
        for _, u in universe.iterrows():
            mask = np.ones(len(gp), dtype=bool)
            for c in key_cols:
                mask &= gp[c].astype(str).eq(str(u[c]))
            sub = gp.loc[mask].copy()
            supp = sub[sub[cand_col] == True].copy()
            if supp.empty:
                target_rows.append({
                    **{c: u[c] for c in key_cols},
                    "analysis_mode": mode,
                    "assessable": bool(u["assessable"]),
                    "n_support_pairs": 0,
                    "n_clusters": 0,
                    "clustered_support": 0.0,
                    "supported": False,
                })
                continue
            supp["cluster_key"] = supp.apply(_cluster_key, axis=1)
            cluster_sizes = supp.groupby("cluster_key").size().to_dict()
            top = (
                supp.sort_values(["cluster_key", "final_pair_score"], ascending=[True, False])
                .groupby("cluster_key", dropna=False)
                .head(1)
                .copy()
            )
            top["cluster_weight"] = top["cluster_key"].map(lambda k: 1.0 / math.sqrt(cluster_sizes.get(k, 1)))
            score = _weighted_noisy_or(top["final_pair_score"].tolist(), top["cluster_weight"].tolist())
            target_rows.append({
                **{c: u[c] for c in key_cols},
                "analysis_mode": mode,
                "assessable": bool(u["assessable"]),
                "n_support_pairs": int(len(supp)),
                "n_clusters": int(len(top)),
                "clustered_support": float(score),
                "supported": bool(float(score) >= support_threshold),
            })

    target_support = pd.DataFrame(target_rows)

    overall_rows: List[Dict[str, object]] = []
    for (gid, genes, mode), g in target_support.groupby(["genotype_id", "matched_sfari_genes", "analysis_mode"], dropna=False):
        doms = STRICT_DOMAINS if mode == "strict" else BROAD_DOMAINS
        dom_scores = []
        dom_fracs = []
        assessable_domains = 0
        supported_domains = 0
        for dom in doms:
            dom_targets = set(targets_by_domain.get(dom, []))
            if not dom_targets:
                continue
            sub = g[g["target_id"].isin(dom_targets)].copy()
            assess = sub[sub["assessable"] == True].copy()
            if assess.empty:
                continue
            assessable_domains += 1
            n_assess = len(assess)
            n_supported = int(assess["supported"].sum())
            dom_score = float(assess["clustered_support"].mean())
            frac = n_supported / n_assess if n_assess else np.nan
            if n_supported > 0:
                supported_domains += 1
            dom_scores.append(dom_score)
            dom_fracs.append(frac)
        overall_rows.append({
            "genotype_id": gid,
            "matched_sfari_genes": genes,
            "analysis_mode": mode,
            "assessable_domains": int(assessable_domains),
            "supported_domains": int(supported_domains),
            "overall_support_score": float(np.mean(dom_scores)) if dom_scores else np.nan,
            "mean_matched_targets_fraction": float(np.mean(dom_fracs)) if dom_fracs else np.nan,
        })
    overall = pd.DataFrame(overall_rows)
    return target_support, overall


def build_burden_profile(mouse_mp: pd.DataFrame, taxonomy: pd.DataFrame, exclude_tier5_from_total: bool = False) -> pd.DataFrame:
    tax = taxonomy.copy()
    if "relevance_tier" not in tax.columns:
        raise ValueError("taxonomy_tsv must contain relevance_tier")
    keep_tax = [c for c in ["mp_id", "mp_term", "relevance_tier", "primary_domain", "secondary_domain"] if c in tax.columns]
    tax = tax[keep_tax].drop_duplicates(subset=["mp_id"]).copy()
    merged = mouse_mp[[c for c in ["genotype_id", "matched_sfari_genes", "mp_id", "mp_term"] if c in mouse_mp.columns]].drop_duplicates().merge(
        tax, on="mp_id", how="left", suffixes=("_mouse", "_tax")
    )
    if exclude_tier5_from_total:
        merged = merged[merged["relevance_tier"].fillna(5).astype(float) != 5].copy()
    rows=[]
    for (gid, genes), g in merged.groupby(["genotype_id", "matched_sfari_genes"], dropna=False):
        tiers = g["relevance_tier"].fillna(5).astype(int)
        total = len(g)
        counts = {f"tier{i}_count": int((tiers==i).sum()) for i in range(1,6)}
        strict_fraction = counts["tier1_count"]/total if total else 0.0
        broad_support_fraction = (counts["tier1_count"]+counts["tier2_count"])/total if total else 0.0
        asd_focus_fraction = (counts["tier1_count"] + 0.5*counts["tier2_count"]) / total if total else 0.0
        mechanistic_fraction = counts["tier3_count"]/total if total else 0.0
        generic_fraction = counts["tier4_count"]/total if total else 0.0
        off_target_fraction = (counts["tier4_count"]+counts["tier5_count"])/total if total else 0.0
        rows.append({
            "genotype_id": gid,
            "matched_sfari_genes": genes,
            "total_retained_terms": int(total),
            **counts,
            "strict_fraction": strict_fraction,
            "broad_support_fraction": broad_support_fraction,
            "asd_focus_fraction": asd_focus_fraction,
            "mechanistic_fraction": mechanistic_fraction,
            "generic_fraction": generic_fraction,
            "off_target_fraction": off_target_fraction,
        })
    return pd.DataFrame(rows)


def rarefy_support(gen_pairs: pd.DataFrame, taxonomy: pd.DataFrame, support_threshold: float, n_iter: int, rarefy_n: Optional[int], seed: int, exclude_tier5_from_total: bool=False) -> Tuple[pd.DataFrame, int]:
    gp = gen_pairs.copy()
    tax = taxonomy[[c for c in ["mp_id","relevance_tier"] if c in taxonomy.columns]].drop_duplicates(subset=["mp_id"]).copy()
    gp = gp.merge(tax, on="mp_id", how="left")
    if exclude_tier5_from_total:
        gp = gp[gp["relevance_tier"].fillna(5).astype(float) != 5].copy()
    counts = gp.groupby("genotype_id")["mp_id"].nunique()
    if counts.empty:
        return pd.DataFrame(), 0
    sample_n = int(rarefy_n) if rarefy_n is not None else int(counts.min())
    sample_n = max(1, sample_n)
    rng = np.random.default_rng(seed)
    rows=[]
    for gid, g in gp.groupby("genotype_id", dropna=False):
        genes = g["matched_sfari_genes"].iloc[0] if "matched_sfari_genes" in g.columns and not g.empty else ""
        unique_ids = g["mp_id"].dropna().astype(str).unique().tolist()
        if not unique_ids:
            continue
        local_n = min(sample_n, len(unique_ids))
        for i in range(n_iter):
            chosen = set(rng.choice(unique_ids, size=local_n, replace=False).tolist())
            sub = g[g["mp_id"].astype(str).isin(chosen)].copy()
            _, overall = aggregate_from_pairs(sub, support_threshold=support_threshold)
            if overall.empty:
                continue
            for _, r in overall.iterrows():
                rows.append({
                    "genotype_id": gid,
                    "matched_sfari_genes": genes,
                    "iteration": i+1,
                    **r.to_dict(),
                })
    sims = pd.DataFrame(rows)
    if sims.empty:
        return sims, sample_n
    sims = sims.loc[:, ~sims.columns.duplicated()].copy()
    return sims, sample_n


def summarize_rarefied(sims: pd.DataFrame) -> pd.DataFrame:
    if sims.empty:
        return pd.DataFrame(columns=[
            "genotype_id","matched_sfari_genes","analysis_mode",
            "overall_support_score_mean","overall_support_score_sd",
            "mean_matched_targets_fraction_mean","mean_matched_targets_fraction_sd",
            "supported_domains_mean","supported_domains_sd",
            "assessable_domains_mean","assessable_domains_sd",
        ])
    num_cols = ["overall_support_score","mean_matched_targets_fraction","supported_domains","assessable_domains"]
    rows=[]
    for (gid, genes, mode), g in sims.groupby(["genotype_id","matched_sfari_genes","analysis_mode"], dropna=False):
        row={"genotype_id":gid,"matched_sfari_genes":genes,"analysis_mode":mode}
        for c in num_cols:
            vals = pd.to_numeric(g[c], errors="coerce")
            row[f"{c}_mean"] = float(vals.mean()) if vals.notna().any() else np.nan
            row[f"{c}_sd"] = float(vals.std(ddof=0)) if vals.notna().any() else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def apply_penalties(summary: pd.DataFrame, burden: pd.DataFrame,
                    strict_alpha: float, strict_beta: float,
                    broad_alpha: float, broad_beta: float,
                    min_supported_domains: int, min_asd_focus_fraction: float) -> Dict[str, pd.DataFrame]:
    merged = summary.merge(burden, on=["genotype_id","matched_sfari_genes"], how="left")
    strict = merged[merged["analysis_mode"] == "strict"].copy()
    broad = merged[merged["analysis_mode"] == "broad"].copy()

    def focused_penalty(df: pd.DataFrame, alpha: float, beta: float) -> pd.DataFrame:
        x = df.copy()
        x["penalty_factor"] = (
            np.sqrt(x["asd_focus_fraction"].fillna(0).clip(lower=0))
            * np.power((1 - x["off_target_fraction"].fillna(0).clip(0,1)), alpha)
            * np.power((1 - x["mechanistic_fraction"].fillna(0).clip(0,1)), beta)
        )
        return x

    def tolerant_penalty(df: pd.DataFrame, alpha: float, beta: float) -> pd.DataFrame:
        x = df.copy()
        sup = x["supported_domains_mean"].fillna(0)
        a = np.where(sup >= min_supported_domains, alpha/2.0, alpha)
        b = np.where(sup >= min_supported_domains, beta/2.0, beta)
        x["penalty_alpha_used"] = a
        x["penalty_beta_used"] = b
        x["penalty_factor"] = (
            np.sqrt(x["asd_focus_fraction"].fillna(0).clip(lower=0))
            * np.power((1 - x["off_target_fraction"].fillna(0).clip(0,1)), a)
            * np.power((1 - x["mechanistic_fraction"].fillna(0).clip(0,1)), b)
        )
        return x

    strict_f = focused_penalty(strict, strict_alpha, strict_beta)
    strict_f["rank_score"] = strict_f["overall_support_score_mean"].fillna(0) * strict_f["penalty_factor"].fillna(0)
    strict_f["gate_pass"] = (
        (strict_f["supported_domains_mean"].fillna(0) >= min_supported_domains)
        & (strict_f["asd_focus_fraction"].fillna(0) >= min_asd_focus_fraction)
        & (strict_f["rank_score"] > 0)
    )
    strict_f["gate_fail_reason"] = np.select([
        strict_f["supported_domains_mean"].fillna(0) < min_supported_domains,
        strict_f["asd_focus_fraction"].fillna(0) < min_asd_focus_fraction,
        strict_f["rank_score"] <= 0,
    ], [
        "insufficient_supported_domains",
        "low_asd_focus_fraction",
        "zero_rank_score",
    ], default="pass")
    strict_f = strict_f.sort_values(["rank_score","supported_domains_mean","overall_support_score_mean"], ascending=[False,False,False]).reset_index(drop=True)
    strict_f.insert(0, "strict_focused_rank", strict_f.index + 1)

    strict_t = tolerant_penalty(strict, strict_alpha, strict_beta)
    strict_t["rank_score"] = strict_t["overall_support_score_mean"].fillna(0) * strict_t["penalty_factor"].fillna(0)
    strict_t["gate_pass"] = (
        (strict_t["supported_domains_mean"].fillna(0) >= min_supported_domains)
        & (strict_t["rank_score"] > 0)
    )
    strict_t = strict_t.sort_values(["rank_score","supported_domains_mean","overall_support_score_mean"], ascending=[False,False,False]).reset_index(drop=True)
    strict_t.insert(0, "strict_tolerant_rank", strict_t.index + 1)

    broad_f = focused_penalty(broad, broad_alpha, broad_beta)
    broad_f["rank_score"] = broad_f["overall_support_score_mean"].fillna(0) * broad_f["penalty_factor"].fillna(0)
    broad_f = broad_f.sort_values(["rank_score","supported_domains_mean","overall_support_score_mean"], ascending=[False,False,False]).reset_index(drop=True)
    broad_f.insert(0, "broad_focused_rank", broad_f.index + 1)

    rec = strict_f[[c for c in strict_f.columns if c not in []]].copy()
    rec = rec.merge(strict_t[["genotype_id","rank_score"]].rename(columns={"rank_score":"strict_tolerant_score"}), on="genotype_id", how="left")
    rec = rec.merge(broad_f[["genotype_id","rank_score","overall_support_score_mean"]].rename(columns={"rank_score":"broad_focused_score","overall_support_score_mean":"broad_support_score_mean"}), on="genotype_id", how="left")
    rec["recommended_track"] = np.where(rec["gate_pass"], "strict_focused", np.where(rec["strict_tolerant_score"].fillna(0)>0, "strict_tolerant", "broad_focused"))
    rec["recommended_score"] = np.where(
        rec["gate_pass"], rec["rank_score"], np.where(rec["strict_tolerant_score"].fillna(0)>0, rec["strict_tolerant_score"], rec["broad_focused_score"].fillna(0))
    )
    rec = rec.sort_values(["recommended_track","recommended_score","supported_domains_mean"], ascending=[True,False,False]).reset_index(drop=True)
    rec.insert(0, "recommended_rank", rec.index + 1)

    return {
        "strict_focused": strict_f,
        "strict_tolerant": strict_t,
        "broad_focused": broad_f,
        "recommended": rec,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--genotype_pair_evidence_tsv", type=str, default="01_genotype_pair_evidence.tsv")
    ap.add_argument("--mouse_mp_csv", type=str, default="00_all_matching_autism_genotype_phenotypes_long.csv")
    ap.add_argument("--taxonomy_tsv", type=str, default="03_mp_term_taxonomy.tsv")
    ap.add_argument("--support_threshold", type=float, default=0.30)
    ap.add_argument("--rarefy_n", type=int, default=None)
    ap.add_argument("--n_iter", type=int, default=100)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--strict_alpha", type=float, default=1.0)
    ap.add_argument("--strict_beta", type=float, default=0.5)
    ap.add_argument("--broad_alpha", type=float, default=0.5)
    ap.add_argument("--broad_beta", type=float, default=0.25)
    ap.add_argument("--min_supported_domains", type=int, default=2)
    ap.add_argument("--min_asd_focus_fraction", type=float, default=0.05)
    ap.add_argument("--exclude_tier5_from_total", action="store_true")
    ap.add_argument("--outdir", type=str, default="asd_batch4_ranked")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    gen_pairs = read_table(Path(args.genotype_pair_evidence_tsv)).copy()
    mouse_mp = read_table(Path(args.mouse_mp_csv)).copy()
    taxonomy = read_table(Path(args.taxonomy_tsv)).copy()

    burden = build_burden_profile(mouse_mp, taxonomy, exclude_tier5_from_total=args.exclude_tier5_from_total)
    burden.to_csv(outdir / "01_burden_profile.tsv", sep="\t", index=False)

    sims, sample_n = rarefy_support(
        gen_pairs, taxonomy, support_threshold=args.support_threshold,
        n_iter=args.n_iter, rarefy_n=args.rarefy_n, seed=args.seed,
        exclude_tier5_from_total=args.exclude_tier5_from_total,
    )
    sims.to_csv(outdir / "02_rarefied_overall_long.tsv", sep="\t", index=False)

    summary = summarize_rarefied(sims)
    summary.to_csv(outdir / "03_rarefied_overall_support.tsv", sep="\t", index=False)

    rankings = apply_penalties(
        summary, burden,
        strict_alpha=args.strict_alpha, strict_beta=args.strict_beta,
        broad_alpha=args.broad_alpha, broad_beta=args.broad_beta,
        min_supported_domains=args.min_supported_domains,
        min_asd_focus_fraction=args.min_asd_focus_fraction,
    )
    rankings["strict_focused"].to_csv(outdir / "04_strict_focused_ranking.tsv", sep="\t", index=False)
    rankings["strict_tolerant"].to_csv(outdir / "05_strict_syndromic_tolerant_ranking.tsv", sep="\t", index=False)
    rankings["broad_focused"].to_csv(outdir / "06_broad_focused_ranking.tsv", sep="\t", index=False)
    rankings["recommended"].to_csv(outdir / "07_recommended_ranking.tsv", sep="\t", index=False)

    config = {
        "genotype_pair_evidence_tsv": args.genotype_pair_evidence_tsv,
        "mouse_mp_csv": args.mouse_mp_csv,
        "taxonomy_tsv": args.taxonomy_tsv,
        "support_threshold": args.support_threshold,
        "rarefy_n": args.rarefy_n,
        "resolved_rarefy_n": sample_n,
        "n_iter": args.n_iter,
        "seed": args.seed,
        "strict_alpha": args.strict_alpha,
        "strict_beta": args.strict_beta,
        "broad_alpha": args.broad_alpha,
        "broad_beta": args.broad_beta,
        "min_supported_domains": args.min_supported_domains,
        "min_asd_focus_fraction": args.min_asd_focus_fraction,
        "exclude_tier5_from_total": args.exclude_tier5_from_total,
        "note": "Rarefaction recomputes support from genotype_pair_evidence using cluster-weighted noisy-OR; rankings report focused and syndromic-tolerant penalty views.",
    }
    (outdir / "08_run_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    print(f"Done. Outputs written to: {outdir.resolve()}")
    print(f"Burden rows: {len(burden)}")
    print(f"Rarefied simulation rows: {len(sims)}")
    print(f"Rarefied summary rows: {len(summary)}")
    print(f"Strict focused ranking rows: {len(rankings['strict_focused'])}")


if __name__ == "__main__":
    main()
