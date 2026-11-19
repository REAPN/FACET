#!/usr/bin/env python3
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import permutation_null_per_genotype as P
import aggregate_support_clustered_broad as A
import stage4_permutation_null as S

LEXICAL_THRESHOLD = 0.65
MAX_LEXICAL_N = 200

_TOKENS: Dict[str, Set[str]] = {}
_ANC: Dict[Tuple[str, int], str] = {}
_LEX_LINK: Dict[int, Dict[str, Set[str]]] = {}
_orig_build_lookups = P.build_lookups
_orig_support_score = P.support_score


def _text_tokens(term, definition) -> Set[str]:
    text = f"{'' if pd.isna(term) else term}; {'' if pd.isna(definition) else definition}"
    return A.norm_tokens(text)


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def build_lookups_mirrored(rer: pd.DataFrame, scope_strict=None, scope_broad=None):
    out = _orig_build_lookups(rer, scope_strict=scope_strict, scope_broad=scope_broad)
    mp_lookup, target_domain, t_to_idx, t_domain_arr, targets, rer2 = out
    term_col = "mp_term" if "mp_term" in rer2.columns else "mp_label"
    def_col = "mp_definition" if "mp_definition" in rer2.columns else None
    anc_col = "ancestor_id" if "ancestor_id" in rer2.columns else None
    _TOKENS.clear(); _ANC.clear(); _LEX_LINK.clear()
    keep = (rer2["strict_cand"] | rer2["broad_cand"] | rer2["strict_assessable"] | rer2["broad_assessable"])
    sub = rer2[keep]
    for _, r in sub.iterrows():
        mp = str(r["mp_id"])
        if mp not in _TOKENS:
            _TOKENS[mp] = _text_tokens(r[term_col], r[def_col] if def_col else "")
        tidx = t_to_idx[r["target_id"]]
        a = "" if anc_col is None else str(r[anc_col])
        if a in {"nan", "None", "NaN"}:
            a = ""
        _ANC[(mp, tidx)] = a
    per_t: Dict[int, List[str]] = defaultdict(list)
    for _, r in sub[sub["strict_cand"] | sub["broad_cand"]].iterrows():
        per_t[t_to_idx[r["target_id"]]].append(str(r["mp_id"]))
    for tidx, mps in per_t.items():
        mps = sorted(set(mps))
        links: Dict[str, Set[str]] = defaultdict(set)
        for i in range(len(mps)):
            ti = _TOKENS.get(mps[i], set())
            for j in range(i + 1, len(mps)):
                if _jaccard(ti, _TOKENS.get(mps[j], set())) >= LEXICAL_THRESHOLD:
                    links[mps[i]].add(mps[j]); links[mps[j]].add(mps[i])
        _LEX_LINK[tidx] = links
    P.log.info("mirrored clustering: %d mp ids with tokens, %d targets with lexical links",
               len(_TOKENS), sum(1 for v in _LEX_LINK.values() if v))
    return out


def _clustered_noisy_or(tidx: int, rows: List[Tuple[str, float]]) -> float:
    n = len(rows)
    if n == 1:
        return P.noisy_or(np.array([rows[0][1]]))
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    by_mp: Dict[str, List[int]] = defaultdict(list)
    by_anc: Dict[str, List[int]] = defaultdict(list)
    for i, (mp, _) in enumerate(rows):
        by_mp[mp].append(i)
        a = _ANC.get((mp, tidx), "")
        if a:
            by_anc[a].append(i)
    for idxs in list(by_mp.values()) + list(by_anc.values()):
        for j in range(1, len(idxs)):
            union(idxs[0], idxs[j])
    if n <= MAX_LEXICAL_N:
        links = _LEX_LINK.get(tidx, {})
        for i in range(n):
            li = links.get(rows[i][0])
            if not li:
                continue
            for j in range(i + 1, n):
                if rows[j][0] in li and find(i) != find(j):
                    union(i, j)
    best: Dict[int, float] = {}
    for i, (_, s) in enumerate(rows):
        r = find(i)
        if s > best.get(r, -1.0):
            best[r] = s
    return P.noisy_or(np.array(list(best.values()), dtype=float))


def support_score_mirrored(mp_ids: List[str], mp_lookup: Dict, t_domain_arr: np.ndarray,
                           n_targets: int, mode: str, domains_strict=None, domains_broad=None):
    if domains_strict is None:
        domains_strict = P.DEFAULT_STRICT_DOMAINS
    if domains_broad is None:
        domains_broad = P.DEFAULT_BROAD_DOMAINS
    domains_set = domains_strict if mode == "strict" else domains_broad
    cand_idx = 2 if mode == "strict" else 3
    assess_idx = 4 if mode == "strict" else 5
    per_target: Dict[int, List[Tuple[str, float]]] = defaultdict(list)
    assessable: set = set()
    for mp in mp_ids:
        if mp in mp_lookup:
            for entry in mp_lookup[mp]:
                tidx = entry[0]
                if entry[assess_idx]:
                    assessable.add(tidx)
                    if entry[cand_idx]:
                        per_target[tidx].append((mp, entry[1]))
    if not assessable:
        return 0.0, 0
    target_score: Dict[int, float] = {}
    for tidx in assessable:
        rows = per_target.get(tidx)
        target_score[tidx] = _clustered_noisy_or(tidx, rows) if rows else 0.0
    domain_scores: Dict[str, List[float]] = defaultdict(list)
    for tidx, s in target_score.items():
        d = t_domain_arr[tidx]
        if d in domains_set:
            domain_scores[d].append(s)
    if not domain_scores:
        return 0.0, 0
    return float(np.mean([np.mean(v) for v in domain_scores.values()])), len(domain_scores)


def self_check() -> None:
    rows = [("MP:1", 0.9), ("MP:2", 0.8)]
    _TOKENS.update({"MP:1": {"alpha"}, "MP:2": {"beta"}}); _LEX_LINK[0] = {}
    assert abs(_clustered_noisy_or(0, rows) - P.noisy_or(np.array([0.9, 0.8]))) < 1e-12
    _LEX_LINK[0] = {"MP:1": {"MP:2"}, "MP:2": {"MP:1"}}
    assert abs(_clustered_noisy_or(0, rows) - 0.9) < 1e-12
    _TOKENS.clear(); _LEX_LINK.clear()


if __name__ == "__main__":
    self_check()
    P.build_lookups = build_lookups_mirrored
    P.support_score = support_score_mirrored
    P.log.info("permutation null with Stage 3 clustering mirrored (threshold %.2f, max lexical n %d)",
               LEXICAL_THRESHOLD, MAX_LEXICAL_N)
    sys.exit(S.main())
