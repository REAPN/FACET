#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

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

STOP = {
    "abnormal", "impaired", "reduced", "increased", "decreased", "behavior", "response",
    "of", "the", "and", "to", "in", "for", "with", "a", "an", "phenotype", "deviation",
}


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".tsv", ".txt"}:
        return pd.read_csv(path, sep="\t")
    return pd.read_csv(path)


def clean_text(x: str) -> str:
    return re.sub(r"\s+", " ", str(x or "")).strip()


def norm_tokens(x: str) -> set[str]:
    toks = re.findall(r"[a-z0-9]+", clean_text(x).lower())
    return {t for t in toks if len(t) > 2 and t not in STOP}


def token_jaccard(a: str, b: str) -> float:
    ta = norm_tokens(a)
    tb = norm_tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def cluster_support_rows(g: pd.DataFrame, lexical_threshold: float = 0.65) -> pd.DataFrame:
    if g.empty:
        out = g.copy()
        out["cluster_id"] = []
        return out

    rows = g.copy().reset_index(drop=True)
    parent = list(range(len(rows)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    mp_groups = rows.groupby("mp_id", dropna=False).indices
    for idxs in mp_groups.values():
        idxs = list(idxs)
        for i in range(1, len(idxs)):
            union(idxs[0], idxs[i])

    anc_ok = rows["ancestor_id"].notna() & rows["ancestor_id"].astype(str).ne("")
    if anc_ok.any():
        anc_groups = rows.loc[anc_ok].groupby("ancestor_id", dropna=False).indices
        for idxs in anc_groups.values():
            idxs = list(idxs)
            for i in range(1, len(idxs)):
                union(idxs[0], idxs[i])

    texts = (rows["mp_term"].fillna("") + "; " + rows.get("mp_definition", "").fillna("")).tolist()
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            if find(i) == find(j):
                continue
            if token_jaccard(texts[i], texts[j]) >= lexical_threshold:
                union(i, j)

    cluster_labels: Dict[int, int] = {}
    next_id = 1
    assigned = []
    for i in range(len(rows)):
        root = find(i)
        if root not in cluster_labels:
            cluster_labels[root] = next_id
            next_id += 1
        assigned.append(cluster_labels[root])
    rows["cluster_id"] = assigned
    return rows


def noisy_or(scores: Sequence[float]) -> float:
    vals = [float(x) for x in scores if pd.notna(x) and float(x) > 0]
    if not vals:
        return 0.0
    prod = 1.0
    for s in vals:
        prod *= (1.0 - max(0.0, min(1.0, s)))
    return 1.0 - prod


def _bool_series(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0).astype(bool)


def prepare_genotype_pair_evidence(reranked_pairs: pd.DataFrame, mouse_mp: pd.DataFrame) -> pd.DataFrame:
    keep_mouse = [
        "genotype_id", "allelic_composition", "allele_symbols", "genetic_background",
        "matched_sfari_genes", "matched_marker_names", "autism_disease_terms", "mp_id", "mp_term", "pubmed_ids"
    ]
    keep_mouse = [c for c in keep_mouse if c in mouse_mp.columns]
    gen = mouse_mp[keep_mouse].drop_duplicates().copy()
    merged = gen.merge(reranked_pairs, on=["mp_id", "mp_term"], how="inner", suffixes=("_gen", ""))

    merged["comparable_observable"] = merged["comparable_observable"].fillna(False).astype(bool)
    merged["strict_eligible"] = merged["strict_eligible"].fillna(False).astype(bool)
    merged["broad_eligible"] = merged["broad_eligible"].fillna(False).astype(bool)
    merged["evidence_scope"] = merged["evidence_scope"].fillna("unclear")

    merged["strict_candidate"] = (
        merged["strict_eligible"]
        & merged["comparable_observable"]
        & merged["evidence_scope"].isin(ALLOWED_EVIDENCE_SCOPE_STRICT)
    )
    merged["broad_candidate"] = (
        merged["broad_eligible"]
        & merged["comparable_observable"]
        & merged["evidence_scope"].isin(ALLOWED_EVIDENCE_SCOPE_BROAD)
    )

    merged["strict_assessable"] = (
        merged["comparable_observable"] & merged["evidence_scope"].isin(ALLOWED_EVIDENCE_SCOPE_STRICT)
    )
    merged["broad_assessable"] = (
        merged["comparable_observable"] & merged["evidence_scope"].isin(ALLOWED_EVIDENCE_SCOPE_BROAD)
    )

    return merged


def aggregate_target_support(gen_pairs: pd.DataFrame, support_threshold: float, lexical_cluster_threshold: float) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    raw_rows: List[Dict[str, object]] = []
    clustered_rows: List[Dict[str, object]] = []
    audit_rows: List[Dict[str, object]] = []

    key_cols = ["genotype_id", "matched_sfari_genes", "target_id", "hpo_id", "hpo_label", "human_domain"]

    for mode in ["strict", "broad"]:
        cand_col = f"{mode}_candidate"
        assess_col = f"{mode}_assessable"

        universe = gen_pairs[key_cols + [assess_col]].groupby(key_cols, dropna=False)[assess_col].any().reset_index(name="assessable")

        for _, u in universe.iterrows():
            mask = np.ones(len(gen_pairs), dtype=bool)
            for c in key_cols:
                mask &= gen_pairs[c].astype(str).eq(str(u[c]))
            g_all = gen_pairs.loc[mask].copy()
            g_sup = g_all[g_all[cand_col] == True].copy()

            raw_scores = g_sup["final_pair_score"].astype(float).tolist() if not g_sup.empty else []
            raw_support = noisy_or(raw_scores)

            raw_rows.append({
                **{c: u[c] for c in key_cols},
                "analysis_mode": mode,
                "assessable": bool(u["assessable"]),
                "n_support_pairs": int(len(g_sup)),
                "raw_support": float(raw_support),
                "supported_raw": bool(float(raw_support) >= support_threshold),
            })

            if g_sup.empty:
                clustered_rows.append({
                    **{c: u[c] for c in key_cols},
                    "analysis_mode": mode,
                    "assessable": bool(u["assessable"]),
                    "n_support_pairs": 0,
                    "n_clusters": 0,
                    "clustered_support": 0.0,
                    "supported_clustered": False,
                    "top_support_mp_terms": "",
                })
                continue

            g_cluster = cluster_support_rows(g_sup, lexical_threshold=lexical_cluster_threshold)
            top_per_cluster = (
                g_cluster.sort_values(["cluster_id", "final_pair_score"], ascending=[True, False])
                .groupby("cluster_id", dropna=False)
                .head(1)
                .copy()
            )
            clustered_support = noisy_or(top_per_cluster["final_pair_score"].astype(float).tolist())
            top_terms = " | ".join(
                (top_per_cluster.sort_values("final_pair_score", ascending=False)
                 .head(5)["mp_term"].astype(str).tolist())
            )
            clustered_rows.append({
                **{c: u[c] for c in key_cols},
                "analysis_mode": mode,
                "assessable": bool(u["assessable"]),
                "n_support_pairs": int(len(g_sup)),
                "n_clusters": int(top_per_cluster["cluster_id"].nunique()),
                "clustered_support": float(clustered_support),
                "supported_clustered": bool(float(clustered_support) >= support_threshold),
                "top_support_mp_terms": top_terms,
            })

            for cid, gc in g_cluster.groupby("cluster_id", dropna=False):
                best = gc.sort_values("final_pair_score", ascending=False).iloc[0]
                audit_rows.append({
                    **{c: u[c] for c in key_cols},
                    "analysis_mode": mode,
                    "cluster_id": int(cid),
                    "cluster_size": int(len(gc)),
                    "best_mp_id": best["mp_id"],
                    "best_mp_term": best["mp_term"],
                    "best_score": float(best["final_pair_score"]),
                    "ancestor_id": best.get("ancestor_id", np.nan),
                    "ancestor_label": best.get("ancestor_label", np.nan),
                    "cluster_terms": " | ".join(sorted(gc["mp_term"].astype(str).unique())),
                })

    return pd.DataFrame(raw_rows), pd.DataFrame(clustered_rows), pd.DataFrame(audit_rows)


def aggregate_domain_support(target_support: pd.DataFrame, all_targets: pd.DataFrame, support_threshold: float) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []

    targets_by_domain = (
        all_targets[["target_id", "human_domain"]]
        .drop_duplicates()
        .groupby("human_domain", dropna=False)["target_id"]
        .apply(list)
        .to_dict()
    )

    grouped = target_support.groupby(["genotype_id", "matched_sfari_genes", "analysis_mode"], dropna=False)
    for (gid, genes, mode), g in grouped:
        domains = STRICT_DOMAINS if mode == "strict" else BROAD_DOMAINS
        for dom in domains:
            dom_targets = set(targets_by_domain.get(dom, []))
            if not dom_targets:
                rows.append({
                    "genotype_id": gid,
                    "matched_sfari_genes": genes,
                    "analysis_mode": mode,
                    "domain": dom,
                    "n_targets_total": 0,
                    "n_targets_assessable": 0,
                    "n_targets_supported": 0,
                    "domain_support_score": np.nan,
                    "matched_targets_fraction": np.nan,
                    "domain_supported": False,
                })
                continue
            sub = g[g["target_id"].isin(dom_targets)].copy()
            assessable = sub[sub["assessable"] == True].copy()
            n_total = len(dom_targets)
            n_assess = len(assessable)
            if n_assess == 0:
                rows.append({
                    "genotype_id": gid,
                    "matched_sfari_genes": genes,
                    "analysis_mode": mode,
                    "domain": dom,
                    "n_targets_total": n_total,
                    "n_targets_assessable": 0,
                    "n_targets_supported": 0,
                    "domain_support_score": np.nan,
                    "matched_targets_fraction": np.nan,
                    "domain_supported": False,
                })
                continue
            n_supported = int((assessable["clustered_support"] >= support_threshold).sum())
            dom_score = float(assessable["clustered_support"].mean())
            frac = n_supported / n_assess if n_assess else np.nan
            rows.append({
                "genotype_id": gid,
                "matched_sfari_genes": genes,
                "analysis_mode": mode,
                "domain": dom,
                "n_targets_total": n_total,
                "n_targets_assessable": n_assess,
                "n_targets_supported": n_supported,
                "domain_support_score": dom_score,
                "matched_targets_fraction": frac,
                "domain_supported": bool(n_supported > 0),
            })
    return pd.DataFrame(rows)


def aggregate_overall_support(domain_support: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    for (gid, genes, mode), g in domain_support.groupby(["genotype_id", "matched_sfari_genes", "analysis_mode"], dropna=False):
        assess = g[g["n_targets_assessable"] > 0].copy()
        if assess.empty:
            rows.append({
                "genotype_id": gid,
                "matched_sfari_genes": genes,
                "analysis_mode": mode,
                "assessable_domains": 0,
                "supported_domains": 0,
                "overall_support_score": np.nan,
                "mean_matched_targets_fraction": np.nan,
            })
            continue
        rows.append({
            "genotype_id": gid,
            "matched_sfari_genes": genes,
            "analysis_mode": mode,
            "assessable_domains": int(len(assess)),
            "supported_domains": int(assess["domain_supported"].sum()),
            "overall_support_score": float(assess["domain_support_score"].mean()),
            "mean_matched_targets_fraction": float(assess["matched_targets_fraction"].mean()),
        })
    return pd.DataFrame(rows)


def build_assessability_summary(gen_pairs: pd.DataFrame, domain_support: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if not gen_pairs.empty:
        for mode in ["strict", "broad"]:
            assess_col = f"{mode}_assessable"
            sub = gen_pairs.groupby(["genotype_id", "matched_sfari_genes", "human_domain"], dropna=False)[assess_col].any().reset_index(name="assessable")
            rows.append(
                sub.groupby("human_domain", dropna=False)["assessable"]
                .agg(n_genotypes="count", assessable_fraction="mean")
                .reset_index()
                .assign(analysis_mode=mode, summary_type="target_domain_assessability")
            )
    if not domain_support.empty:
        tmp = domain_support.copy()
        tmp["domain_assessable"] = tmp["n_targets_assessable"] > 0
        rows.append(
            tmp.groupby(["analysis_mode", "domain"], dropna=False)["domain_assessable"]
            .agg(n_genotypes="count", assessable_fraction="mean")
            .reset_index()
            .assign(summary_type="domain_assessability")
        )
    if rows:
        return pd.concat(rows, ignore_index=True)
    return pd.DataFrame(columns=["analysis_mode", "domain", "summary_type", "n_genotypes", "assessable_fraction"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reranked_pairs_tsv", type=str, default="03_reranked_pairs.tsv")
    ap.add_argument("--mouse_mp_csv", type=str, default="00_all_matching_autism_genotype_phenotypes_long.csv")
    ap.add_argument("--support_threshold", type=float, default=0.30)
    ap.add_argument("--lexical_cluster_threshold", type=float, default=0.65)
    ap.add_argument("--outdir", type=str, default="asd_support_aggregated")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    reranked = read_table(Path(args.reranked_pairs_tsv)).copy()
    mouse_mp = read_table(Path(args.mouse_mp_csv)).copy()

    all_targets = reranked[["target_id", "hpo_id", "hpo_label", "human_domain"]].drop_duplicates().copy()

    gen_pairs = prepare_genotype_pair_evidence(reranked, mouse_mp)
    gen_pairs.to_csv(outdir / "01_genotype_pair_evidence.tsv", sep="\t", index=False)

    raw_support, clustered_support, cluster_audit = aggregate_target_support(
        gen_pairs, support_threshold=args.support_threshold, lexical_cluster_threshold=args.lexical_cluster_threshold
    )
    raw_support.to_csv(outdir / "02_target_support_raw.tsv", sep="\t", index=False)
    clustered_support.to_csv(outdir / "03_target_support_clustered.tsv", sep="\t", index=False)
    cluster_audit.to_csv(outdir / "04_cluster_audit.tsv", sep="\t", index=False)

    domain_support = aggregate_domain_support(clustered_support, all_targets, support_threshold=args.support_threshold)
    domain_support.to_csv(outdir / "05_domain_support.tsv", sep="\t", index=False)

    overall = aggregate_overall_support(domain_support)
    overall.to_csv(outdir / "06_overall_genotype_support.tsv", sep="\t", index=False)

    assess = build_assessability_summary(gen_pairs, domain_support)
    assess.to_csv(outdir / "07_assessability_summary.tsv", sep="\t", index=False)

    config = {
        "reranked_pairs_tsv": args.reranked_pairs_tsv,
        "mouse_mp_csv": args.mouse_mp_csv,
        "support_threshold": args.support_threshold,
        "lexical_cluster_threshold": args.lexical_cluster_threshold,
        "strict_domains": STRICT_DOMAINS,
        "broad_domains": BROAD_DOMAINS,
        "strict_evidence_scope": sorted(ALLOWED_EVIDENCE_SCOPE_STRICT),
        "broad_evidence_scope": sorted(ALLOWED_EVIDENCE_SCOPE_BROAD),
        "note": "Clustered target support uses top-per-cluster noisy-OR; domain means are computed over assessable targets only.",
    }
    (outdir / "08_run_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    print(f"Done. Outputs written to: {outdir.resolve()}")
    print(f"Genotype pair evidence rows: {len(gen_pairs)}")
    print(f"Target support rows: {len(clustered_support)}")
    print(f"Domain support rows: {len(domain_support)}")
    print(f"Overall genotype rows: {len(overall)}")


if __name__ == "__main__":
    main()
