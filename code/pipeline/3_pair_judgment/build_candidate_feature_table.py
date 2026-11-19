#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import numpy as np
import pandas as pd

try:
    from rapidfuzz import fuzz
except Exception:
    fuzz = None

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

STRICT_DOMAINS = [
    "social_interaction",
    "communication",
    "repetitive_restricted",
    "sensory_reactivity",
]

ADJACENCY = {
    "social_interaction": {"communication", "developmental_support"},
    "communication": {"social_interaction", "developmental_support"},
    "repetitive_restricted": {"sensory_reactivity", "developmental_support"},
    "sensory_reactivity": {"repetitive_restricted"},
    "developmental_support": {"social_interaction", "communication", "repetitive_restricted"},
}

SOCIAL_PAT = re.compile(r"social|recipro|peer|conspecific|eye contact|friend|play|withdraw|recognition")
COMM_PAT = re.compile(r"communicat|conversation|language|speech|vocal|ultrasonic|verbal|nonverbal")
RRB_PAT = re.compile(r"repetit|stereotyp|restricted|ritual|sameness|insistence|persever|groom|marble bury|self[- ]?injur")
SENS_PAT = re.compile(r"sensory|pain|temperature|auditory|visual|olfact|tactile|touch|somatosens|hyperreact|hyporeact")
DEV_PAT = re.compile(r"development|delay|regress|milestone|neurodevelopment")
MOTOR_PAT = re.compile(r"motor|gait|coordination|balance")
COG_PAT = re.compile(r"learn|memory|attention|cognit|behavior")

STOP = {
    "abnormal", "impaired", "reduced", "increase", "decrease", "difficulty",
    "behavior", "response", "phenotype", "abnormality", "defect", "defective",
    "of", "the", "and", "to", "in", "for", "with", "a", "an",
}


def clean_text(x: str) -> str:
    x = str(x or "")
    x = re.sub(r"\s+", " ", x).strip()
    return x


def norm_tokens(x: str) -> List[str]:
    toks = re.findall(r"[a-z0-9]+", x.lower())
    return [t for t in toks if len(t) > 2 and t not in STOP]


def lexical_score(a: str, b: str) -> float:
    a = clean_text(a)
    b = clean_text(b)
    if not a or not b:
        return 0.0
    if fuzz is not None:
        ts = fuzz.token_set_ratio(a, b) / 100.0
        wr = fuzz.WRatio(a, b) / 100.0
        return 0.6 * ts + 0.4 * wr
    ta = set(norm_tokens(a))
    tb = set(norm_tokens(b))
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def cosine_similarity(u: np.ndarray, v: np.ndarray) -> float:
    if u.size == 0 or v.size == 0:
        return 0.0
    denom = float(np.linalg.norm(u) * np.linalg.norm(v))
    if denom == 0:
        return 0.0
    return float(np.dot(u, v) / denom)


def normalize_domain(x: str) -> str:
    x = clean_text(x).lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "social": "social_interaction",
        "social_behavior": "social_interaction",
        "social_interaction": "social_interaction",
        "communication": "communication",
        "language": "communication",
        "repetitive": "repetitive_restricted",
        "repetitive_restricted": "repetitive_restricted",
        "restricted_repetitive": "repetitive_restricted",
        "sensory": "sensory_reactivity",
        "sensory_reactivity": "sensory_reactivity",
        "developmental": "developmental_support",
        "developmental_support": "developmental_support",
        "cognitive": "cognitive_behavioral_support",
        "cognitive_behavioral_support": "cognitive_behavioral_support",
        "behavioral_support": "cognitive_behavioral_support",
        "motor": "motor_support",
        "motor_support": "motor_support",
        "mechanistic_neurophysiology": "mechanistic_neurophysiology",
        "mechanistic_neuroanatomy": "mechanistic_neuroanatomy",
        "generic_neurological": "generic_neurological",
        "off_target": "off_target",
        "other": "other",
    }
    return aliases.get(x, x if x else "other")


def infer_hpo_domain(category: str, label: str, phenotype_text: str) -> str:
    text = f"{clean_text(label)} {clean_text(phenotype_text)}".lower()
    category = clean_text(category).lower()
    if category == "sensory" or SENS_PAT.search(text):
        return "sensory_reactivity"
    if category == "language" or COMM_PAT.search(text):
        return "communication"
    if category == "restricted_repetitive_behavior" or RRB_PAT.search(text):
        return "repetitive_restricted"
    if category == "social_communication":
        if COMM_PAT.search(text) and not SOCIAL_PAT.search(text):
            return "communication"
        if SOCIAL_PAT.search(text):
            return "social_interaction"
        return "social_interaction"
    if category == "developmental_course" or DEV_PAT.search(text):
        return "developmental_support"
    if category == "motor" or MOTOR_PAT.search(text):
        return "motor_support"
    if COG_PAT.search(text):
        return "cognitive_behavioral_support"
    if SOCIAL_PAT.search(text):
        return "social_interaction"
    return "other"


def normalize_mouse_domain(primary: str, secondary: str, mp_text: str) -> str:
    for val in [primary, secondary]:
        nd = normalize_domain(val)
        if nd not in {"", "other", "off_target", "generic_neurological"}:
            return nd
    text = mp_text.lower()
    if SENS_PAT.search(text):
        return "sensory_reactivity"
    if COMM_PAT.search(text):
        return "communication"
    if RRB_PAT.search(text):
        return "repetitive_restricted"
    if SOCIAL_PAT.search(text):
        return "social_interaction"
    if DEV_PAT.search(text):
        return "developmental_support"
    if MOTOR_PAT.search(text):
        return "motor_support"
    if COG_PAT.search(text):
        return "cognitive_behavioral_support"
    nd = normalize_domain(primary)
    return nd if nd else "other"


def compatible_domains(h_domain: str, use_spillover: bool) -> Set[str]:
    out = {h_domain}
    if use_spillover:
        out |= set(ADJACENCY.get(h_domain, set()))
    return out


def stable_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".tsv", ".txt"}:
        return pd.read_csv(path, sep="\t")
    return pd.read_csv(path)


def load_hpo_targets(path: Path, include_supporting: bool) -> pd.DataFrame:
    df = read_table(path).copy()
    req = {"hpo_id", "hpo_label"}
    if not req.issubset(df.columns):
        raise ValueError(f"HPO TSV missing required columns: {sorted(req - set(df.columns))}")
    if "centrality" in df.columns:
        allowed = {"core"}
        if include_supporting:
            allowed.add("supporting")
        df = df[df["centrality"].fillna("").isin(allowed)].copy()
    df["normalized_phenotype"] = df.get("normalized_phenotype", "").fillna("")
    df["category"] = df.get("category", "other").fillna("other")
    df["human_domain"] = [
        infer_hpo_domain(c, l, p)
        for c, l, p in zip(df["category"], df["hpo_label"], df["normalized_phenotype"])
    ]
    df["target_id"] = [f"TGT_{i:03d}_{stable_hash(f'{hid}|{lbl}|{ph}') }" for i, (hid, lbl, ph) in enumerate(zip(df["hpo_id"], df["hpo_label"], df["normalized_phenotype"]), start=1)]
    df["target_text"] = (df["hpo_label"].fillna("") + "; " + df["normalized_phenotype"].fillna("")).map(clean_text)
    keep = [
        "target_id", "hpo_id", "hpo_label", "normalized_phenotype", "category",
        "centrality", "human_domain", "target_text",
    ]
    return df[keep].drop_duplicates(subset=["target_id"]).reset_index(drop=True)


def load_taxonomy(path: Path) -> pd.DataFrame:
    tax = read_table(path).copy()
    if "mp_id" not in tax.columns:
        raise ValueError("Taxonomy TSV must contain mp_id")
    if "mp_label" not in tax.columns and "mp_term" in tax.columns:
        tax = tax.rename(columns={"mp_term": "mp_label"})
    for col in ["primary_domain", "secondary_domain", "relevance_tier"]:
        if col not in tax.columns:
            tax[col] = np.nan
    return tax


def load_mouse_terms(mouse_csv: Path, taxonomy_tsv: Path, include_tier2: bool) -> Tuple[pd.DataFrame, pd.DataFrame]:
    mp = read_table(mouse_csv).copy()
    tax = load_taxonomy(taxonomy_tsv)
    if "mp_id" not in mp.columns:
        raise ValueError("Mouse MP CSV must contain mp_id")
    if "mp_term" not in mp.columns:
        raise ValueError("Mouse MP CSV must contain mp_term")

    merged = mp.merge(tax, on="mp_id", how="left", suffixes=("", "_tax"))
    merged["mp_definition"] = merged.get("mp_definition", "").fillna("")
    merged["mp_label"] = merged.get("mp_label", merged["mp_term"]).fillna(merged["mp_term"])
    merged["relevance_tier"] = pd.to_numeric(merged.get("relevance_tier", np.nan), errors="coerce")

    if include_tier2:
        merged = merged[merged["relevance_tier"].fillna(99).isin([1, 2, 3, 4])].copy()
    else:
        merged = merged[merged["relevance_tier"].fillna(99).isin([1, 3, 4])].copy()

    merged["mp_text"] = (merged["mp_label"].fillna("") + "; " + merged["mp_definition"].fillna("")).map(clean_text)
    merged["mouse_domain"] = [
        normalize_mouse_domain(p, s, t)
        for p, s, t in zip(merged.get("primary_domain", ""), merged.get("secondary_domain", ""), merged["mp_text"])
    ]

    term_cols = [
        "mp_id", "mp_label", "mp_term", "mp_definition", "mp_text",
        "mouse_domain", "primary_domain", "secondary_domain", "relevance_tier",
    ]
    terms = merged[term_cols].drop_duplicates(subset=["mp_id"]).reset_index(drop=True)
    return terms, merged


def embed_texts(texts: Sequence[str], model: str) -> Dict[str, np.ndarray]:
    if OpenAI is None:
        raise RuntimeError("openai package is required for embedding retrieval")
    client = OpenAI()
    result: Dict[str, np.ndarray] = {}
    batch = 100
    for i in range(0, len(texts), batch):
        chunk = list(texts[i:i+batch])
        resp = client.embeddings.create(model=model, input=chunk)
        for txt, datum in zip(chunk, resp.data):
            result[txt] = np.array(datum.embedding, dtype=float)
    return result


def load_pairwise_subset(path: Optional[Path], hpo_ids: Set[str], mp_ids: Set[str]) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame(columns=[
            "subject_id", "object_id", "ancestor_information_content", "jaccard_similarity", "phenodigm_score"
        ])
    usecols = None
    try:
        sample = read_table(path).head(1)
        cols = list(sample.columns)
        usecols = [c for c in [
            "subject_id", "object_id", "ancestor_id", "ancestor_label",
            "ancestor_information_content", "jaccard_similarity", "phenodigm_score"
        ] if c in cols]
    except Exception:
        pass
    df = read_table(path)
    if usecols is not None:
        keep = [c for c in usecols if c in df.columns]
        df = df[keep].copy()
    if "subject_id" not in df.columns or "object_id" not in df.columns:
        raise ValueError("Pairwise similarity TSV must contain subject_id and object_id")
    df = df[df["subject_id"].isin(hpo_ids) & df["object_id"].isin(mp_ids)].copy()
    for col in ["ancestor_information_content", "jaccard_similarity", "phenodigm_score"]:
        if col not in df.columns:
            df[col] = np.nan
    return df.reset_index(drop=True)


def load_mp_children(obo_path: str) -> Dict[str, Set[str]]:
    children: Dict[str, Set[str]] = {}
    cur = None
    try:
        fh = open(obo_path, encoding="utf-8", errors="ignore")
    except Exception:
        return children
    for line in fh:
        line = line.rstrip("\n")
        if line == "[Term]":
            cur = None
        elif line.startswith("id: MP:"):
            cur = line[4:].strip()
        elif line.startswith("is_a:") and cur:
            parent = line.split("is_a:")[1].strip().split("!")[0].strip()
            children.setdefault(parent, set()).add(cur)
    fh.close()
    return children


def load_carried_mps(carriage_csv: str) -> Set[str]:
    try:
        df = read_table(Path(carriage_csv))
    except Exception:
        return set()
    if "mp_id" not in df.columns:
        return set()
    return set(df["mp_id"].astype(str))


def generate_candidates(
    hpo_df: pd.DataFrame,
    mouse_terms: pd.DataFrame,
    mode: str,
    use_spillover: bool,
    use_embedding_retrieval: bool,
    use_lexical_retrieval: bool,
    top_k_embedding: int,
    top_k_lexical: int,
    embedding_model: str,
    inject_descendants: bool = False,
    mp_children: Optional[Dict[str, Set[str]]] = None,
    carried_mps: Optional[Set[str]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    records: List[Dict[str, object]] = []
    summaries: List[Dict[str, object]] = []

    emb_map_h: Dict[str, np.ndarray] = {}
    emb_map_m: Dict[str, np.ndarray] = {}
    if use_embedding_retrieval:
        h_texts = hpo_df["target_text"].tolist()
        m_texts = mouse_terms["mp_text"].tolist()
        emb_map_h = embed_texts(h_texts, embedding_model)
        emb_map_m = embed_texts(m_texts, embedding_model)

    domain_to_mouse = {d: g.copy() for d, g in mouse_terms.groupby("mouse_domain", dropna=False)}

    MT_INDEX: Dict[str, Dict[str, object]] = {}
    if inject_descendants:
        for _, _mt in mouse_terms.iterrows():
            MT_INDEX[str(_mt["mp_id"])] = _mt.to_dict()
    _desc_cache: Dict[str, Set[str]] = {}
    def _descendants(pid: str) -> Set[str]:
        if not mp_children:
            return set()
        if pid in _desc_cache:
            return _desc_cache[pid]
        seen: Set[str] = set(); stack = [pid]
        while stack:
            n = stack.pop()
            for c in mp_children.get(n, ()):
                if c not in seen:
                    seen.add(c); stack.append(c)
        _desc_cache[pid] = seen
        return seen

    for _, h in hpo_df.iterrows():
        h_domain = h["human_domain"]
        allowed = compatible_domains(h_domain, use_spillover)
        cand_frames = []
        for dom in allowed:
            if dom in domain_to_mouse:
                tmp = domain_to_mouse[dom].copy()
                tmp["matched_domain"] = dom
                cand_frames.append(tmp)
        if not cand_frames:
            summaries.append({
                "target_id": h["target_id"],
                "hpo_id": h["hpo_id"],
                "hpo_label": h["hpo_label"],
                "human_domain": h_domain,
                "n_candidates": 0,
                "n_embedding": 0,
                "n_lexical": 0,
                "n_exhaustive": 0,
                "n_spillover": 0,
            })
            continue
        cand = pd.concat(cand_frames, ignore_index=True)

        cand["lexical_score"] = [lexical_score(h["target_text"], t) for t in cand["mp_text"]]
        if use_embedding_retrieval:
            hvec = emb_map_h.get(h["target_text"], np.array([], dtype=float))
            cand["text_embed_cosine"] = [cosine_similarity(hvec, emb_map_m.get(t, np.array([], dtype=float))) for t in cand["mp_text"]]
        else:
            cand["text_embed_cosine"] = np.nan
        cand["spillover"] = cand["matched_domain"] != h_domain

        selected_ids: Set[str] = set()
        channel_map: Dict[str, Set[str]] = {"embedding": set(), "lexical": set(), "spillover": set(), "exhaustive": set(), "injected": set()}

        if mode == "exhaustive":
            selected_ids = set(cand["mp_id"].astype(str))
            channel_map["exhaustive"] = set(cand["mp_id"].astype(str))
        else:
            if use_embedding_retrieval:
                emb_pick = cand.sort_values(["text_embed_cosine", "lexical_score"], ascending=[False, False]).head(top_k_embedding)
                ids = set(emb_pick["mp_id"].astype(str))
                selected_ids |= ids
                channel_map["embedding"] |= ids
            if use_lexical_retrieval:
                lex_pick = cand.sort_values(["lexical_score", "text_embed_cosine"], ascending=[False, False]).head(top_k_lexical)
                ids = set(lex_pick["mp_id"].astype(str))
                selected_ids |= ids
                channel_map["lexical"] |= ids
            if use_spillover:
                spill_ids = set(cand.loc[cand["spillover"], "mp_id"].astype(str))
                selected_ids |= spill_ids
                channel_map["spillover"] |= spill_ids
        if not selected_ids and not cand.empty:
            top1 = str(cand.sort_values(["lexical_score", "text_embed_cosine"], ascending=[False, False]).iloc[0]["mp_id"])
            selected_ids.add(top1)
            channel_map["lexical"].add(top1)

        if inject_descendants and carried_mps is not None and mp_children:
            inj_ids: Set[str] = set()
            anchors = channel_map["embedding"] | channel_map["lexical"]
            for pid in list(anchors):
                for ch in _descendants(str(pid)):
                    if ch in carried_mps and ch not in selected_ids and ch in MT_INDEX:
                        inj_ids.add(ch)
            if inj_ids:
                hvec_inj = emb_map_h.get(h["target_text"], np.array([], dtype=float)) if use_embedding_retrieval else None
                inj_rows = []
                base_cols = [c for c in cand.columns if c not in ("lexical_score", "text_embed_cosine", "spillover", "matched_domain")]
                for cid in inj_ids:
                    mt = MT_INDEX[cid]
                    lex = lexical_score(h["target_text"], str(mt.get("mp_text", "")))
                    if use_embedding_retrieval:
                        emb = cosine_similarity(hvec_inj, emb_map_m.get(str(mt.get("mp_text", "")), np.array([], dtype=float)))
                    else:
                        emb = np.nan
                    row = {c: mt.get(c, np.nan) for c in base_cols}
                    row.update({"mp_id": cid, "matched_domain": "injected",
                                "lexical_score": lex, "text_embed_cosine": emb, "spillover": True})
                    inj_rows.append(row)
                cand = pd.concat([cand, pd.DataFrame(inj_rows)], ignore_index=True, sort=False)
                selected_ids |= inj_ids
                channel_map["injected"] |= inj_ids

        kept = (cand[cand["mp_id"].astype(str).isin(selected_ids)]
                .drop_duplicates(subset=["mp_id"], keep="first")
                .copy())
        for _, m in kept.iterrows():
            mpid = str(m["mp_id"])
            channels = [name for name, ids in channel_map.items() if mpid in ids]
            records.append({
                "target_id": h["target_id"],
                "hpo_id": h["hpo_id"],
                "hpo_label": h["hpo_label"],
                "target_text": h["target_text"],
                "human_domain": h_domain,
                "mp_id": m["mp_id"],
                "mp_label": m["mp_label"],
                "mp_term": m["mp_term"],
                "mp_definition": m["mp_definition"],
                "mp_text": m["mp_text"],
                "mouse_domain": m["mouse_domain"],
                "matched_domain": m["matched_domain"],
                "primary_domain": m.get("primary_domain", np.nan),
                "secondary_domain": m.get("secondary_domain", np.nan),
                "relevance_tier": m.get("relevance_tier", np.nan),
                "lexical_score": float(m["lexical_score"]),
                "text_embed_cosine": float(m["text_embed_cosine"]) if pd.notna(m["text_embed_cosine"]) else np.nan,
                "spillover": bool(m["spillover"]),
                "retrieval_channels": "|".join(sorted(channels)),
            })

        summaries.append({
            "target_id": h["target_id"],
            "hpo_id": h["hpo_id"],
            "hpo_label": h["hpo_label"],
            "human_domain": h_domain,
            "n_candidates": len(kept),
            "n_embedding": len(channel_map["embedding"]),
            "n_lexical": len(channel_map["lexical"]),
            "n_exhaustive": len(channel_map["exhaustive"]),
            "n_spillover": len(channel_map["spillover"]),
        })

    cand_pairs = pd.DataFrame(records)
    summary = pd.DataFrame(summaries)
    return cand_pairs, summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hpo_tsv", type=str, default="07_final_resolved_hpo_terms.tsv")
    ap.add_argument("--mouse_mp_csv", type=str, default="00_all_matching_autism_genotype_phenotypes_long.csv")
    ap.add_argument("--taxonomy_tsv", type=str, required=True)
    ap.add_argument("--pairwise_similarity_tsv", type=str, default=None)
    ap.add_argument("--include_supporting_hpo", action="store_true")
    ap.add_argument("--include_tier2_mouse", action="store_true")
    ap.add_argument("--mode", choices=["exhaustive", "union"], default="union")
    ap.add_argument("--use_embedding_retrieval", action="store_true")
    ap.add_argument("--use_lexical_retrieval", action="store_true")
    ap.add_argument("--use_spillover", action="store_true")
    ap.add_argument("--top_k_embedding", type=int, default=20)
    ap.add_argument("--top_k_lexical", type=int, default=20)
    ap.add_argument("--embedding_model", type=str, default=os.environ.get("OPENAI_EMBED_MODEL", "text-embedding-3-large"))
    ap.add_argument("--outdir", type=str, default="asd_candidate_features")
    ap.add_argument("--inject_descendants", action="store_true",
                    help="Native descendant injection: license is_a descendants of selected candidates that genotypes carry, bypassing the domain gate and top-N window.")
    ap.add_argument("--mp_obo", type=str, default="MPheno_OBO.ontology")
    ap.add_argument("--carriage_csv", type=str, default=None,
                    help="Genotype->MP CSV for carriage (defaults to --mouse_mp_csv).")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    hpo = load_hpo_targets(Path(args.hpo_tsv), include_supporting=args.include_supporting_hpo)
    mouse_terms, mouse_rows = load_mouse_terms(Path(args.mouse_mp_csv), Path(args.taxonomy_tsv), include_tier2=args.include_tier2_mouse)

    hpo.to_csv(outdir / "01_hpo_targets.tsv", sep="\t", index=False)
    mouse_terms.to_csv(outdir / "02_mouse_terms.tsv", sep="\t", index=False)

    _mp_children = load_mp_children(args.mp_obo) if args.inject_descendants else None
    _carried = load_carried_mps(args.carriage_csv or args.mouse_mp_csv) if args.inject_descendants else None
    if args.inject_descendants:
        print(f"Descendant injection ON: {sum(len(v) for v in (_mp_children or {}).values())} is_a edges, {len(_carried or set())} carried MP ids")
    cand_pairs, target_summary = generate_candidates(
        hpo_df=hpo,
        mouse_terms=mouse_terms,
        mode=args.mode,
        use_spillover=args.use_spillover,
        use_embedding_retrieval=args.use_embedding_retrieval,
        use_lexical_retrieval=args.use_lexical_retrieval,
        top_k_embedding=args.top_k_embedding,
        top_k_lexical=args.top_k_lexical,
        embedding_model=args.embedding_model,
        inject_descendants=args.inject_descendants,
        mp_children=_mp_children,
        carried_mps=_carried,
    )

    pairwise = load_pairwise_subset(
        Path(args.pairwise_similarity_tsv) if args.pairwise_similarity_tsv else None,
        hpo_ids=set(hpo["hpo_id"].astype(str)),
        mp_ids=set(mouse_terms["mp_id"].astype(str)),
    )
    feat = cand_pairs.merge(
        pairwise.rename(columns={"subject_id": "hpo_id", "object_id": "mp_id"}),
        on=["hpo_id", "mp_id"],
        how="left",
    )

    feat.to_csv(outdir / "03_candidate_pairs.tsv", sep="\t", index=False)
    feat.to_csv(outdir / "04_candidate_feature_table.tsv", sep="\t", index=False)
    target_summary.to_csv(outdir / "05_candidate_summary_by_target.tsv", sep="\t", index=False)

    by_domain = feat.groupby(["human_domain", "matched_domain"], dropna=False).agg(
        n_pairs=("mp_id", "count"),
        mean_lexical=("lexical_score", "mean"),
        mean_embed=("text_embed_cosine", "mean"),
        mean_jaccard=("jaccard_similarity", "mean"),
        mean_ic=("ancestor_information_content", "mean"),
    ).reset_index()
    by_domain.to_csv(outdir / "06_candidate_summary_by_domain.tsv", sep="\t", index=False)

    channel_rows = []
    if not feat.empty:
        for ch in ["embedding", "lexical", "spillover", "exhaustive", "injected"]:
            mask = feat["retrieval_channels"].fillna("").str.contains(fr"(^|\|){ch}(\||$)")
            sub = feat[mask].copy()
            channel_rows.append({
                "channel": ch,
                "n_pairs": int(sub.shape[0]),
                "n_unique_targets": int(sub["target_id"].nunique()) if not sub.empty else 0,
                "n_unique_mouse_terms": int(sub["mp_id"].nunique()) if not sub.empty else 0,
                "mean_lexical": float(sub["lexical_score"].mean()) if not sub.empty else np.nan,
                "mean_embed": float(sub["text_embed_cosine"].mean()) if (not sub.empty and sub["text_embed_cosine"].notna().any()) else np.nan,
            })
    pd.DataFrame(channel_rows).to_csv(outdir / "07_candidate_summary_by_channel.tsv", sep="\t", index=False)

    config = {
        "hpo_tsv": args.hpo_tsv,
        "mouse_mp_csv": args.mouse_mp_csv,
        "taxonomy_tsv": args.taxonomy_tsv,
        "pairwise_similarity_tsv": args.pairwise_similarity_tsv,
        "include_supporting_hpo": args.include_supporting_hpo,
        "include_tier2_mouse": args.include_tier2_mouse,
        "mode": args.mode,
        "use_embedding_retrieval": args.use_embedding_retrieval,
        "use_lexical_retrieval": args.use_lexical_retrieval,
        "use_spillover": args.use_spillover,
        "top_k_embedding": args.top_k_embedding,
        "top_k_lexical": args.top_k_lexical,
        "embedding_model": args.embedding_model,
        "inject_descendants": args.inject_descendants,
    }
    (outdir / "08_run_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    print(f"Done. Outputs written to: {outdir.resolve()}")
    print(f"Human targets: {len(hpo)}")
    print(f"Mouse terms: {len(mouse_terms)}")
    print(f"Candidate pairs: {len(feat)}")
    zeros = int((target_summary["n_candidates"] == 0).sum()) if not target_summary.empty else 0
    print(f"Targets with zero candidates: {zeros}")


if __name__ == "__main__":
    main()
