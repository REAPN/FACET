#!/usr/bin/env python3
"""aggregate_support_clustered_broad.py
====================================

Usage
-----
    # Headline rigorous run (defaults: filled reranked input + Strategy B gate)
    python3 aggregate_support_clustered_broad.py         --outdir asd_support_aggregated_broad_v3_rigorous
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("aggregate_broad")


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

ALLOWED_EVIDENCE_SCOPE_STRICT = {
    "organism_behavior",
    "organism_sensory",
    "developmental_behavior",
}
ALLOWED_EVIDENCE_SCOPE_BROAD = {
    "organism_behavior",
    "organism_sensory",
    "developmental_behavior",
    "unclear",
}

STRONG_BEHAVIORAL_ANALOG_TYPES = {"direct_analog", "close_support"}

STOP = {
    "abnormal", "impaired", "reduced", "increased", "decreased", "behavior",
    "response", "of", "the", "and", "to", "in", "for", "with", "a", "an",
    "phenotype", "deviation",
}


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".tsv", ".txt"}:
        return pd.read_csv(path, sep="\t", low_memory=False)
    return pd.read_csv(path, low_memory=False)


def clean_text(x) -> str:
    return re.sub(r"\s+", " ", str(x or "")).strip()


def norm_tokens(x: str) -> set:
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


def noisy_or(scores: Sequence[float]) -> float:
    vals = [float(x) for x in scores if pd.notna(x) and float(x) > 0]
    if not vals:
        return 0.0
    prod = 1.0
    for s in vals:
        prod *= 1.0 - max(0.0, min(1.0, s))
    return 1.0 - prod


def cluster_indices(
    mp_ids: Sequence[str],
    ancestor_ids: Sequence[Optional[str]],
    texts: Sequence[str],
    lexical_threshold: float,
    max_lexical_n: int = 200,
) -> List[int]:
    n = len(mp_ids)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    by_mp: Dict[str, List[int]] = {}
    for i, m in enumerate(mp_ids):
        by_mp.setdefault(str(m), []).append(i)
    for idxs in by_mp.values():
        for j in range(1, len(idxs)):
            union(idxs[0], idxs[j])

    by_anc: Dict[str, List[int]] = {}
    for i, a in enumerate(ancestor_ids):
        if a is None:
            continue
        s = str(a)
        if s in {"", "nan", "None", "NaN"}:
            continue
        by_anc.setdefault(s, []).append(i)
    for idxs in by_anc.values():
        for j in range(1, len(idxs)):
            union(idxs[0], idxs[j])

    if n <= max_lexical_n:
        for i in range(n):
            for j in range(i + 1, n):
                if find(i) == find(j):
                    continue
                if token_jaccard(texts[i], texts[j]) >= lexical_threshold:
                    union(i, j)

    label_for_root: Dict[int, int] = {}
    out = []
    next_id = 1
    for i in range(n):
        root = find(i)
        if root not in label_for_root:
            label_for_root[root] = next_id
            next_id += 1
        out.append(label_for_root[root])
    return out


def detect_genotype_columns(mp: pd.DataFrame) -> List[str]:
    candidates = [
        "genotype_id",
        "blinded_genotype_id",
        "allelic_composition",
        "allele_symbols",
        "genetic_background",
        "matched_sfari_genes",
        "matched_marker_names",
        "disease_terms",
        "autism_disease_terms",
        "benchmark_group",
        "pubmed_ids",
    ]
    return [c for c in candidates if c in mp.columns]


def prepare_genotype_pair_evidence(
    reranked: pd.DataFrame,
    mouse_mp: pd.DataFrame,
    eligibility_mode: str = "score_assisted_broad",
    broad_score_threshold: float = 0.57,
    strict_score_threshold: float = 0.62,
    strict_analog_gate: str = "strong",
    polarity_mode: str = "off",
    taxonomy_tsv: Optional[str] = None,
    polarity_schema_tsv: Optional[str] = None,
) -> pd.DataFrame:
    keep_cols = detect_genotype_columns(mouse_mp)
    if "mp_id" not in mouse_mp.columns or "mp_term" not in mouse_mp.columns:
        raise ValueError("mouse_mp_csv must contain mp_id and mp_term columns.")
    if "mp_id" not in reranked.columns or "mp_term" not in reranked.columns:
        raise ValueError("reranked_pairs_tsv must contain mp_id and mp_term columns.")
    log.info("Keeping mouse-side cols: %s", keep_cols)

    mouse_keep = list(set(keep_cols + ["mp_id", "mp_term"]))
    gen = mouse_mp[mouse_keep].drop_duplicates()
    log.info("Mouse rows after dedup: %d (%d unique genotypes, %d unique MP terms)",
             len(gen),
             gen["genotype_id"].nunique() if "genotype_id" in gen.columns else -1,
             gen["mp_id"].nunique())

    merged = gen.merge(reranked, on=["mp_id", "mp_term"], how="inner",
                        suffixes=("_gen", ""))
    log.info("After inner merge with reranked pairs: %d rows", len(merged))

    not_llm_judged = (
        merged["rerank_action"].isna()
        if "rerank_action" in merged.columns
        else pd.Series([True] * len(merged), index=merged.index)
    )
    score_col = "transparent_score" if "transparent_score" in merged.columns else "final_pair_score"
    if score_col not in merged.columns:
        raise ValueError(
            "reranked_pairs_tsv must contain transparent_score or final_pair_score column."
        )

    for col, default in [
        ("comparable_observable", False),
        ("strict_eligible", False),
        ("broad_eligible", False),
        ("evidence_scope", "unclear"),
    ]:
        if col not in merged.columns:
            merged[col] = default
        else:
            merged[col] = merged[col].fillna(default)

    merged["comparable_observable"] = merged["comparable_observable"].astype(bool)
    merged["strict_eligible"] = merged["strict_eligible"].astype(bool)
    merged["broad_eligible"] = merged["broad_eligible"].astype(bool)
    merged["evidence_scope"] = merged["evidence_scope"].astype(str)

    n_admitted_broad = 0
    n_admitted_strict = 0
    if eligibility_mode == "llm_only":
        pass
    elif eligibility_mode in ("score_assisted_broad", "score_assisted_both"):
        admit_broad = not_llm_judged & (merged[score_col].astype(float) >= broad_score_threshold)
        n_admitted_broad = int(admit_broad.sum())
        if n_admitted_broad > 0:
            merged.loc[admit_broad, "broad_eligible"] = True
            merged.loc[admit_broad, "comparable_observable"] = True
            mask_unclear = admit_broad & (merged["evidence_scope"] == "unclear")
            merged.loc[mask_unclear, "evidence_scope"] = "organism_behavior"
        if eligibility_mode == "score_assisted_both":
            admit_strict = not_llm_judged & (merged[score_col].astype(float) >= strict_score_threshold)
            n_admitted_strict = int(admit_strict.sum())
            if n_admitted_strict > 0:
                merged.loc[admit_strict, "strict_eligible"] = True
                merged.loc[admit_strict, "comparable_observable"] = True
                mask_unclear = admit_strict & (merged["evidence_scope"] == "unclear")
                merged.loc[mask_unclear, "evidence_scope"] = "organism_behavior"
    else:
        raise ValueError(
            f"Unknown eligibility_mode: {eligibility_mode!r}. "
            "Choose from: llm_only | score_assisted_broad | score_assisted_both"
        )

    log.info(
        "Eligibility mode: %s | non-LLM rows auto-admitted: broad=%d, strict=%d",
        eligibility_mode, n_admitted_broad, n_admitted_strict,
    )

    in_strict_scope = merged["evidence_scope"].isin(ALLOWED_EVIDENCE_SCOPE_STRICT)
    in_broad_scope = merged["evidence_scope"].isin(ALLOWED_EVIDENCE_SCOPE_BROAD)

    if "behavioral_analog_type" in merged.columns:
        analog_strong = merged["behavioral_analog_type"].fillna("").isin(
            STRONG_BEHAVIORAL_ANALOG_TYPES
        )
    else:
        analog_strong = pd.Series([False] * len(merged), index=merged.index)

    merged["strong_analog"] = analog_strong

    if strict_analog_gate == "strong":
        merged["strict_candidate"] = (
            merged["strict_eligible"]
            & merged["comparable_observable"]
            & in_strict_scope
            & analog_strong
        )
    elif strict_analog_gate == "any":
        merged["strict_candidate"] = (
            merged["strict_eligible"] & merged["comparable_observable"] & in_strict_scope
        )
    else:
        raise ValueError(
            f"Unknown strict_analog_gate: {strict_analog_gate!r}. Choose 'strong' or 'any'."
        )

    merged["broad_candidate"] = (
        merged["broad_eligible"] & merged["comparable_observable"] & in_broad_scope
    )
    merged["strict_assessable"] = merged["comparable_observable"] & in_strict_scope
    merged["broad_assessable"] = merged["comparable_observable"] & in_broad_scope
    log.info(
        "Strict analog gate: %s | strict_candidate=%d, broad_candidate=%d",
        strict_analog_gate,
        int(merged["strict_candidate"].sum()),
        int(merged["broad_candidate"].sum()),
    )

    merged["polarity_weight"] = 1.0
    if polarity_mode == "schema":
        if not polarity_schema_tsv:
            raise ValueError(
                "--polarity_schema_tsv is required when --polarity_mode schema."
            )
        sch = read_table(Path(polarity_schema_tsv))
        target_sch = (sch[sch["entity_type"] == "human_target"]
                      .drop_duplicates("entity_id")
                      .set_index("entity_id").to_dict("index"))
        mouse_sch = (sch[sch["entity_type"] == "mouse_term"]
                     .drop_duplicates("entity_id")
                     .set_index("entity_id").to_dict("index"))
        log.info("Polarity schema: %d HPO targets, %d MP terms annotated",
                 len(target_sch), len(mouse_sch))

        res_w = {"explicit": 1.0, "inferred": 0.8, "coarse": 0.5, "unknown": 0.3}

        def schema_pair_weight(hpo_id, mp_id):
            t = target_sch.get(str(hpo_id))
            m = mouse_sch.get(str(mp_id))
            if t is None or m is None:
                return 1.0, "outside_subset"
            rw = min(res_w.get(t.get("polarity_resolution"), 0.3),
                     res_w.get(m.get("polarity_resolution"), 0.3))
            t_func = t.get("functional_effect")
            m_func = m.get("functional_effect")
            t_dom = t.get("domain")
            m_dom = m.get("domain")

            if t_dom != m_dom:
                return 0.4 * rw, "cross_domain_partial"

            if t_dom == "sensory_reactivity":
                if t_func != "abnormal_unspecified" and m_func != "abnormal_unspecified":
                    return 1.0 * rw, "sensory_bidirectional_match"
                if t_func == "abnormal_unspecified" or m_func == "abnormal_unspecified":
                    return 0.6 * rw, "sensory_one_side_coarse"

            t_coarse = t_func == "abnormal_unspecified"
            m_coarse = m_func == "abnormal_unspecified"
            if t_coarse and m_coarse:
                return 0.5 * rw, "both_coarse"
            if t_coarse or m_coarse:
                return 0.6 * rw, "one_side_coarse"
            if t_func == m_func:
                return 1.0 * rw, "exact_directional_match"
            plausible = {("less","slower"),("slower","less"),("more","faster"),("faster","more")}
            if (t_func, m_func) in plausible:
                return 0.75 * rw, "inferred_plausible"
            return 0.1 * rw, "explicit_directional_conflict"

        weights = []
        explanations = []
        for hpo_id, mp_id in zip(merged["hpo_id"], merged["mp_id"]):
            w, e = schema_pair_weight(hpo_id, mp_id)
            weights.append(w)
            explanations.append(e)
        merged["polarity_weight"] = weights
        merged["polarity_explanation"] = explanations
        merged["final_pair_score_pre_polarity"] = merged["final_pair_score"]
        merged["final_pair_score"] = (
            pd.to_numeric(merged["final_pair_score"], errors="coerce").fillna(0.0)
            * merged["polarity_weight"].astype(float)
        )
        n_subset = (merged["polarity_explanation"] != "outside_subset").sum()
        log.info("Polarity mode=schema | %d/%d pairs in annotated subset",
                 int(n_subset), len(merged))
        log.info("  explanation distribution:")
        for kind, cnt in merged["polarity_explanation"].value_counts().items():
            log.info("    %s: %d", kind, int(cnt))
    elif polarity_mode != "off":
        if not taxonomy_tsv:
            raise ValueError(
                "--taxonomy_tsv is required when --polarity_mode in {soft, strict} "
                "(polarity columns live in the taxonomy file)."
            )
        tax_pol = read_table(Path(taxonomy_tsv))
        if "asd_direction_consistency" not in tax_pol.columns:
            raise ValueError(
                f"taxonomy_tsv {taxonomy_tsv} lacks 'asd_direction_consistency'. "
                "Run assign_mp_polarity.py to add polarity columns first."
            )
        polarity_lookup = (tax_pol[["mp_id", "asd_direction_consistency"]]
                           .drop_duplicates(subset=["mp_id"])
                           .set_index("mp_id")["asd_direction_consistency"]
                           .to_dict())
        merged["asd_direction_consistency"] = (
            merged["mp_id"].map(polarity_lookup).fillna("na")
        )
        weight_map = {
            "soft":   {"asd_like": 1.0, "na": 1.0, "bidirectional": 0.5, "anti_asd": 0.0},
            "strict": {"asd_like": 1.0, "na": 1.0, "bidirectional": 0.0, "anti_asd": 0.0},
        }[polarity_mode]
        merged["polarity_weight"] = (
            merged["asd_direction_consistency"].map(weight_map).fillna(1.0)
        )
        merged["final_pair_score_pre_polarity"] = merged["final_pair_score"]
        merged["final_pair_score"] = (
            pd.to_numeric(merged["final_pair_score"], errors="coerce").fillna(0.0)
            * merged["polarity_weight"].astype(float)
        )
        n_zeroed = int((merged["polarity_weight"] == 0).sum())
        n_halved = int((merged["polarity_weight"] == 0.5).sum())
        log.info("Polarity mode=%s | %d pairs zeroed, %d pairs halved",
                 polarity_mode, n_zeroed, n_halved)
    return merged


def aggregate_target_support_vectorized(
    gen_pairs: pd.DataFrame,
    support_threshold: float,
    lexical_cluster_threshold: float,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    base_key = ["genotype_id", "target_id", "hpo_id", "hpo_label", "human_domain"]
    if "matched_sfari_genes" in gen_pairs.columns:
        out_cols_extra = ["matched_sfari_genes"]
    else:
        out_cols_extra = []

    raw_rows: List[Dict] = []
    clustered_rows: List[Dict] = []
    audit_rows: List[Dict] = []

    for mode in ("strict", "broad"):
        cand_col = f"{mode}_candidate"
        assess_col = f"{mode}_assessable"

        univ = (
            gen_pairs.groupby(base_key, dropna=False, sort=False)[assess_col]
            .any()
            .reset_index(name="assessable")
        )
        log.info("[%s] universe rows: %d", mode, len(univ))

        sup = gen_pairs[gen_pairs[cand_col]].copy()
        log.info("[%s] supported candidate rows: %d", mode, len(sup))

        if not sup.empty:
            raw_grp = (
                sup.groupby(base_key, dropna=False, sort=False)
                .agg(
                    n_support_pairs=("final_pair_score", "size"),
                    raw_support=(
                        "final_pair_score",
                        lambda s: noisy_or(s.tolist()),
                    ),
                )
                .reset_index()
            )
        else:
            raw_grp = pd.DataFrame(
                columns=base_key + ["n_support_pairs", "raw_support"]
            )

        raw_full = univ.merge(raw_grp, on=base_key, how="left")
        raw_full["n_support_pairs"] = raw_full["n_support_pairs"].fillna(0).astype(int)
        raw_full["raw_support"] = raw_full["raw_support"].fillna(0.0).astype(float)
        raw_full["analysis_mode"] = mode
        raw_full["supported_raw"] = raw_full["raw_support"] >= support_threshold

        if out_cols_extra:
            attach = (
                gen_pairs[base_key + out_cols_extra]
                .drop_duplicates(subset=base_key)
            )
            raw_full = raw_full.merge(attach, on=base_key, how="left")

        for r in raw_full.to_dict(orient="records"):
            raw_rows.append({**r})

        unsup_keys = univ.merge(
            sup[base_key].drop_duplicates(),
            on=base_key, how="left", indicator=True,
        )
        unsup_only = unsup_keys[unsup_keys["_merge"] == "left_only"][base_key + ["assessable"]]
        for r in unsup_only.to_dict(orient="records"):
            row = {**r,
                   "analysis_mode": mode,
                   "n_support_pairs": 0,
                   "n_clusters": 0,
                   "clustered_support": 0.0,
                   "supported_clustered": False,
                   "top_support_mp_terms": ""}
            if out_cols_extra:
                row.update({c: "" for c in out_cols_extra})
            clustered_rows.append(row)

        if not sup.empty:
            sup_local = sup.copy()
            if "ancestor_id" not in sup_local.columns:
                sup_local["ancestor_id"] = ""
            if "mp_definition" not in sup_local.columns:
                sup_local["mp_definition"] = ""
            sup_local["_text_for_cluster"] = (
                sup_local["mp_term"].fillna("") + "; "
                + sup_local["mp_definition"].fillna("")
            )

            grp = sup_local.groupby(base_key, dropna=False, sort=False)
            n_groups = grp.ngroups
            log.info("[%s] clustering %d (genotype, target) groups", mode, n_groups)
            t0 = time.time()
            done = 0
            for keys, g in grp:
                cluster_ids = cluster_indices(
                    mp_ids=g["mp_id"].tolist(),
                    ancestor_ids=g.get("ancestor_id", pd.Series([""] * len(g))).tolist(),
                    texts=g["_text_for_cluster"].tolist(),
                    lexical_threshold=lexical_cluster_threshold,
                )
                gc = g.assign(cluster_id=cluster_ids)
                top_per_cluster = (
                    gc.sort_values(["cluster_id", "final_pair_score"],
                                    ascending=[True, False])
                    .groupby("cluster_id", sort=False)
                    .head(1)
                )
                clustered_support = noisy_or(
                    top_per_cluster["final_pair_score"].tolist()
                )
                top_terms = " | ".join(
                    top_per_cluster.sort_values("final_pair_score", ascending=False)
                    .head(5)["mp_term"].astype(str).tolist()
                )
                key_dict = dict(zip(base_key, keys))
                row = {
                    **key_dict,
                    "analysis_mode": mode,
                    "assessable": True,
                    "n_support_pairs": int(len(g)),
                    "n_clusters": int(top_per_cluster["cluster_id"].nunique()),
                    "clustered_support": float(clustered_support),
                    "supported_clustered": bool(clustered_support >= support_threshold),
                    "top_support_mp_terms": top_terms,
                }
                if out_cols_extra:
                    for c in out_cols_extra:
                        v = g[c].dropna().astype(str).unique()
                        row[c] = v[0] if len(v) else ""
                clustered_rows.append(row)

                for cid, gc_sub in gc.groupby("cluster_id", sort=False):
                    best = gc_sub.sort_values("final_pair_score", ascending=False).iloc[0]
                    audit_rows.append({
                        **key_dict,
                        "analysis_mode": mode,
                        "cluster_id": int(cid),
                        "cluster_size": int(len(gc_sub)),
                        "best_mp_id": best["mp_id"],
                        "best_mp_term": best["mp_term"],
                        "best_score": float(best["final_pair_score"]),
                        "ancestor_id": best.get("ancestor_id", ""),
                        "ancestor_label": best.get("ancestor_label", ""),
                        "cluster_terms": " | ".join(
                            sorted(gc_sub["mp_term"].astype(str).unique())
                        ),
                    })
                done += 1
                if done % 50000 == 0:
                    elapsed = time.time() - t0
                    log.info("  ...clustered %d/%d (%.1fs, %.0f groups/s)",
                             done, n_groups, elapsed,
                             done / max(elapsed, 1e-9))

    raw_df = pd.DataFrame(raw_rows)
    clustered_df = pd.DataFrame(clustered_rows)
    audit_df = pd.DataFrame(audit_rows)
    return raw_df, clustered_df, audit_df


def aggregate_domain_support(
    target_support: pd.DataFrame,
    all_targets: pd.DataFrame,
    support_threshold: float,
) -> pd.DataFrame:
    rows: List[Dict] = []
    targets_by_domain = (
        all_targets[["target_id", "human_domain"]]
        .drop_duplicates()
        .groupby("human_domain", dropna=False)["target_id"]
        .apply(set)
        .to_dict()
    )
    grp_keys = ["genotype_id", "analysis_mode"]
    if "matched_sfari_genes" in target_support.columns:
        grp_keys.append("matched_sfari_genes")
    grouped = target_support.groupby(grp_keys, dropna=False, sort=False)
    log.info("Aggregating domain support over %d (genotype, mode) groups",
             grouped.ngroups)
    for keys, g in grouped:
        keymap = dict(zip(grp_keys, keys))
        mode = keymap["analysis_mode"]
        domains = STRICT_DOMAINS if mode == "strict" else BROAD_DOMAINS
        for dom in domains:
            dom_target_ids = targets_by_domain.get(dom, set())
            if not dom_target_ids:
                rows.append({**keymap, "domain": dom,
                             "n_targets_total": 0, "n_targets_assessable": 0,
                             "n_targets_supported": 0,
                             "domain_support_score": np.nan,
                             "matched_targets_fraction": np.nan,
                             "domain_supported": False})
                continue
            sub = g[g["target_id"].isin(dom_target_ids)]
            n_total = len(dom_target_ids)
            assessable = sub[sub["assessable"]]
            n_assess = len(assessable)
            if n_assess == 0:
                rows.append({**keymap, "domain": dom,
                             "n_targets_total": n_total,
                             "n_targets_assessable": 0,
                             "n_targets_supported": 0,
                             "domain_support_score": np.nan,
                             "matched_targets_fraction": np.nan,
                             "domain_supported": False})
                continue
            n_supported = int(
                (assessable["clustered_support"] >= support_threshold).sum()
            )
            dom_score = float(assessable["clustered_support"].mean())
            frac = n_supported / n_assess if n_assess else np.nan
            rows.append({**keymap, "domain": dom,
                         "n_targets_total": n_total,
                         "n_targets_assessable": n_assess,
                         "n_targets_supported": n_supported,
                         "domain_support_score": dom_score,
                         "matched_targets_fraction": frac,
                         "domain_supported": bool(n_supported > 0)})
    return pd.DataFrame(rows)


VALID_AGGREGATORS = ("mean", "sum", "min", "max",
                     "prod_complement", "weighted_assessable")


def _apply_overall_aggregator(scores: np.ndarray, n_assessable: int,
                              n_total_domains: int, aggregator: str) -> float:
    if scores.size == 0:
        return float("nan")
    if aggregator == "mean":
        return float(np.mean(scores))
    if aggregator == "sum":
        return float(np.sum(scores))
    if aggregator == "min":
        return float(np.min(scores))
    if aggregator == "max":
        return float(np.max(scores))
    if aggregator == "prod_complement":
        clipped = np.clip(scores, 0.0, 1.0)
        return float(1.0 - np.prod(1.0 - clipped))
    if aggregator == "weighted_assessable":
        if n_total_domains <= 0:
            return float("nan")
        return float(np.mean(scores) * (n_assessable / n_total_domains))
    raise ValueError(f"Unknown overall_aggregator: {aggregator!r}; "
                     f"choose from {VALID_AGGREGATORS}.")


def aggregate_overall_support(
    domain_support: pd.DataFrame,
    overall_aggregator: str = "mean",
) -> pd.DataFrame:
    if overall_aggregator not in VALID_AGGREGATORS:
        raise ValueError(
            f"overall_aggregator={overall_aggregator!r} not in {VALID_AGGREGATORS}"
        )
    grp_keys = ["genotype_id", "analysis_mode"]
    if "matched_sfari_genes" in domain_support.columns:
        grp_keys.append("matched_sfari_genes")
    rows: List[Dict] = []
    for keys, g in domain_support.groupby(grp_keys, dropna=False, sort=False):
        keymap = dict(zip(grp_keys, keys))
        assess = g[g["n_targets_assessable"] > 0]
        analysis_mode = str(keymap.get("analysis_mode", "strict"))
        n_total = len(STRICT_DOMAINS) if analysis_mode == "strict" else len(BROAD_DOMAINS)
        if assess.empty:
            rows.append({**keymap,
                         "assessable_domains": 0,
                         "supported_domains": 0,
                         "overall_support_score": np.nan,
                         "mean_matched_targets_fraction": np.nan,
                         "overall_aggregator": overall_aggregator})
            continue
        scores = assess["domain_support_score"].dropna().to_numpy(dtype=float)
        n_assessable = int(len(assess))
        overall = _apply_overall_aggregator(
            scores, n_assessable, n_total, overall_aggregator,
        )
        rows.append({**keymap,
                     "assessable_domains": n_assessable,
                     "supported_domains": int(assess["domain_supported"].sum()),
                     "overall_support_score": overall,
                     "mean_matched_targets_fraction": float(assess["matched_targets_fraction"].mean()),
                     "overall_aggregator": overall_aggregator})
    return pd.DataFrame(rows)


def build_assessability_summary(
    gen_pairs: pd.DataFrame,
    domain_support: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    if not gen_pairs.empty:
        for mode in ("strict", "broad"):
            assess_col = f"{mode}_assessable"
            grp_cols = ["genotype_id", "human_domain"]
            sub = (
                gen_pairs.groupby(grp_cols, dropna=False, sort=False)[assess_col]
                .any()
                .reset_index(name="assessable")
            )
            agg = (
                sub.groupby("human_domain", dropna=False)["assessable"]
                .agg(n_genotypes="count", assessable_fraction="mean")
                .reset_index()
                .assign(analysis_mode=mode,
                        summary_type="target_domain_assessability")
            )
            rows.append(agg)
    if not domain_support.empty:
        tmp = domain_support.copy()
        tmp["domain_assessable"] = tmp["n_targets_assessable"] > 0
        agg = (
            tmp.groupby(["analysis_mode", "domain"], dropna=False)["domain_assessable"]
            .agg(n_genotypes="count", assessable_fraction="mean")
            .reset_index()
            .assign(summary_type="domain_assessability")
        )
        rows.append(agg)
    if not rows:
        return pd.DataFrame(columns=["analysis_mode", "domain", "summary_type",
                                       "n_genotypes", "assessable_fraction"])
    return pd.concat(rows, ignore_index=True)


def build_per_genotype_covariates(
    overall: pd.DataFrame,
    domain_support: pd.DataFrame,
    gen_pairs: pd.DataFrame,
) -> pd.DataFrame:
    grp_keys = ["genotype_id", "analysis_mode"]
    n_mp = (
        gen_pairs.groupby("genotype_id", sort=False)["mp_id"]
        .nunique()
        .rename("n_mp_terms")
        .reset_index()
    )
    out = overall.copy()
    out = out.merge(n_mp, on="genotype_id", how="left")
    out["n_mp_terms"] = out["n_mp_terms"].fillna(0).astype(int)
    out["assessable_fraction"] = out["assessable_domains"] / 4.0
    return out[["genotype_id", "analysis_mode", "n_mp_terms",
                "assessable_domains", "supported_domains",
                "assessable_fraction", "overall_support_score",
                "mean_matched_targets_fraction"]]


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--reranked_pairs_tsv",
        type=str,
        default="asd_pair_rerank_v3_broad_v3/03_reranked_pairs_filled.tsv",
        help=(
            "Reranked candidate pairs TSV. Default = the rigorous (Strategy E) "
            "filled output. For sensitivity-test regimes that use the "
            "pre-fill data, point this to '.../03_reranked_pairs.tsv' instead."
        ),
    )
    ap.add_argument(
        "--mouse_mp_csv", type=str,
        default="broad_benchmark_setup/08_all_genotype_phenotypes_long_blinded.csv",
    )
    ap.add_argument("--support_threshold", type=float, default=0.30)
    ap.add_argument("--lexical_cluster_threshold", type=float, default=0.65)
    ap.add_argument(
        "--eligibility_mode",
        type=str,
        choices=["llm_only", "score_assisted_broad", "score_assisted_both"],
        default="score_assisted_broad",
        help=(
            "How non-LLM-judged candidate pairs are admitted. "
            "'llm_only' reproduces the original behavior (only pairs with explicit "
            "LLM eligibility flags count). 'score_assisted_broad' auto-admits "
            "non-LLM pairs to BROAD if transparent_score >= --broad_score_threshold "
            "(strict still LLM-only). 'score_assisted_both' also auto-admits to "
            "STRICT at --strict_score_threshold."
        ),
    )
    ap.add_argument(
        "--broad_score_threshold",
        type=float,
        default=0.57,
        help=(
            "transparent_score floor for auto-admitting non-LLM pairs to BROAD. "
            "Default 0.57 derived by maximizing balanced accuracy on the 180 "
            "LLM-judged pairs (BA=0.736, precision=0.83, recall=0.70)."
        ),
    )
    ap.add_argument(
        "--strict_score_threshold",
        type=float,
        default=0.62,
        help=(
            "transparent_score floor for auto-admitting non-LLM pairs to STRICT "
            "in 'score_assisted_both' mode. Default 0.62 (BA=0.701) but precision "
            "is only 0.24, so use with caution; not applied unless explicitly chosen."
        ),
    )
    ap.add_argument(
        "--strict_analog_gate",
        type=str,
        choices=["strong", "any"],
        default="strong",
        help=(
            "Whether strict_candidate additionally requires behavioral_analog_type "
            "in {direct_analog, close_support}. Default 'strong' filters out "
            "internally-inconsistent strict_eligible=True with weak_support / "
            "mismatch / mechanistic_only cases (Strategy B in lab notebook). "
            "'any' reproduces the original strict definition for sensitivity comparison."
        ),
    )
    ap.add_argument(
        "--polarity_mode",
        type=str,
        choices=["off", "soft", "strict", "schema"],
        default="off",
        help=(
            "Direction-aware score weighting. "
            "'off' (default): no polarity adjustment. "
            "'soft': asd_like=1.0, bidirectional=0.5, anti_asd=0.0, na=1.0 "
            "(regex-based, from assign_mp_polarity.py). "
            "'strict': asd_like=1.0, bidirectional=0.0, anti_asd=0.0, na=1.0 "
            "(regex-based, harshest). "
            "'schema': LLM-annotated structured-semantic-layer comparison "
            "(measured_feature × assay_metric × functional_effect → "
            "match_weight × resolution_weight). Requires --polarity_schema_tsv. "
            "'soft'/'strict' require --taxonomy_tsv (for asd_direction_consistency)."
        ),
    )
    ap.add_argument(
        "--taxonomy_tsv",
        type=str,
        default=None,
        help=(
            "Path to mp_term_taxonomy_broad_v3/03_mp_term_taxonomy.tsv. Required "
            "when --polarity_mode in {soft, strict} (regex-based polarity from "
            "asd_direction_consistency column)."
        ),
    )
    ap.add_argument(
        "--polarity_schema_tsv",
        type=str,
        default=None,
        help=(
            "Path to polarity_schema_v1/01_term_annotations.tsv (output of "
            "annotate_polarity_schema.py). Required when --polarity_mode schema."
        ),
    )
    ap.add_argument(
        "--overall_aggregator",
        type=str,
        choices=list(VALID_AGGREGATORS),
        default="mean",
        help="Model-level aggregator across assessable DSM-5 domains. See VALID_AGGREGATORS.",
    )
    ap.add_argument("--outdir", type=str, default="asd_support_aggregated_broad")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    log.info("Reading reranked pairs: %s", args.reranked_pairs_tsv)
    reranked = read_table(Path(args.reranked_pairs_tsv)).copy()
    log.info("Reranked pairs: %d rows", len(reranked))

    log.info("Reading mouse MP table: %s", args.mouse_mp_csv)
    mouse_mp = read_table(Path(args.mouse_mp_csv)).copy()
    log.info("Mouse MP table: %d rows", len(mouse_mp))

    all_targets = (
        reranked[["target_id", "hpo_id", "hpo_label", "human_domain"]]
        .drop_duplicates()
        .copy()
    )
    log.info("Distinct HPO targets in reranked pairs: %d", len(all_targets))

    gen_pairs = prepare_genotype_pair_evidence(
        reranked,
        mouse_mp,
        eligibility_mode=args.eligibility_mode,
        broad_score_threshold=args.broad_score_threshold,
        strict_score_threshold=args.strict_score_threshold,
        strict_analog_gate=args.strict_analog_gate,
        polarity_mode=args.polarity_mode,
        taxonomy_tsv=args.taxonomy_tsv,
        polarity_schema_tsv=args.polarity_schema_tsv,
    )
    log.info("Genotype pair evidence: %d rows, %d genotypes",
             len(gen_pairs), gen_pairs["genotype_id"].nunique() if len(gen_pairs) else 0)
    gen_pairs.to_csv(outdir / "01_genotype_pair_evidence.tsv", sep="\t", index=False)

    raw_support, clustered_support, cluster_audit = aggregate_target_support_vectorized(
        gen_pairs,
        support_threshold=args.support_threshold,
        lexical_cluster_threshold=args.lexical_cluster_threshold,
    )
    raw_support.to_csv(outdir / "02_target_support_raw.tsv", sep="\t", index=False)
    clustered_support.to_csv(outdir / "03_target_support_clustered.tsv", sep="\t", index=False)
    cluster_audit.to_csv(outdir / "04_cluster_audit.tsv", sep="\t", index=False)

    domain_support = aggregate_domain_support(
        clustered_support, all_targets, support_threshold=args.support_threshold,
    )
    domain_support.to_csv(outdir / "05_domain_support.tsv", sep="\t", index=False)

    overall = aggregate_overall_support(
        domain_support, overall_aggregator=args.overall_aggregator,
    )
    overall.to_csv(outdir / "06_overall_genotype_support.tsv", sep="\t", index=False)
    log.info("Overall aggregator: %s", args.overall_aggregator)

    assess = build_assessability_summary(gen_pairs, domain_support)
    assess.to_csv(outdir / "07_assessability_summary.tsv", sep="\t", index=False)

    covariates = build_per_genotype_covariates(overall, domain_support, gen_pairs)
    covariates.to_csv(outdir / "07b_per_genotype_covariates.tsv", sep="\t", index=False)

    config = {
        "reranked_pairs_tsv": args.reranked_pairs_tsv,
        "mouse_mp_csv": args.mouse_mp_csv,
        "support_threshold": args.support_threshold,
        "lexical_cluster_threshold": args.lexical_cluster_threshold,
        "eligibility_mode": args.eligibility_mode,
        "broad_score_threshold": args.broad_score_threshold,
        "strict_score_threshold": args.strict_score_threshold,
        "strict_analog_gate": args.strict_analog_gate,
        "polarity_mode": args.polarity_mode,
        "taxonomy_tsv": args.taxonomy_tsv,
        "polarity_schema_tsv": args.polarity_schema_tsv,
        "overall_aggregator": args.overall_aggregator,
        "strict_domains": STRICT_DOMAINS,
        "broad_domains": BROAD_DOMAINS,
        "strict_evidence_scope": sorted(ALLOWED_EVIDENCE_SCOPE_STRICT),
        "broad_evidence_scope": sorted(ALLOWED_EVIDENCE_SCOPE_BROAD),
        "elapsed_seconds": round(time.time() - t0, 1),
        "note": "Vectorized broad-universe rewrite. Genotype-only key; matched_sfari_genes preserved as informational only.",
    }
    (outdir / "08_run_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    log.info("Done in %.1fs. Outputs at %s", time.time() - t0, outdir.resolve())
    log.info("genotype pair evidence rows: %d", len(gen_pairs))
    log.info("target support rows: %d", len(clustered_support))
    log.info("domain support rows: %d", len(domain_support))
    log.info("overall genotype rows: %d", len(overall))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
