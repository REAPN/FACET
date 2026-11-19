"""
Build the blinded expert rating instrument.
Sample is stratified and INTERLEAVED so that any prefix is approximately balanced:
a rater who stops at item 40 still leaves a usable, balanced subsample.
Verdicts are written to a SEALED key file that raters must not open.
"""
import csv, json, random, re, hashlib, sys, io
from pathlib import Path

OUT = Path("_rating_pilot_2026")
SEED = 20260813
N_UNIQUE, N_DUP, N_ANCHOR = 60, 10, 5

RERANK = {
 "ASD": "asd_pair_rerank_v3_broad_v3/03_reranked_pairs_filled.tsv",
 "SCZ": "scz_pair_rerank_v1/03_reranked_pairs_filled.tsv",
 "ID":  "intellectualdisability_pair_rerank_v1/03_reranked_pairs_filled.tsv",
 "NCD": "neurocognitive_pair_rerank_v1_ncdB_cf/03_reranked_pairs_filled.tsv",
 "MDD": "mdd_pair_rerank_v1/03_reranked_pairs_filled.tsv"}
DNAME = {"ASD":"Autism spectrum disorder","SCZ":"Schizophrenia",
         "ID":"Intellectual disability","NCD":"Major neurocognitive disorder",
         "MDD":"Major depressive disorder"}


def criterion_map():
    src = io.open("DSM5-Mouse-Map/build.py", encoding="utf-8").read()
    blk = src[src.find("CRITERIA = {"): src.find("UNREACHABLE = {")]
    ns = {}
    exec(blk.rsplit("}", 1)[0] + "}", {}, ns)
    lab = {}
    for d, rows in ns["CRITERIA"].items():
        for cid, short, label, gloss, kind in rows:
            if kind != "scored": continue
            lab[(d, short)] = (cid, label, gloss)
    out = {}
    for d in ("ASD","SCZ","ID","NCD","MDD"):
        f = f"DSM5-Mouse-Map/inputs/target_units_{d}.tsv"
        try: rows = list(csv.DictReader(io.open(f, encoding="utf-8", errors="replace"), delimiter="\t"))
        except FileNotFoundError: continue
        for r in rows:
            it = (r.get("item_id") or "").strip()
            hp = (r.get("hpo_id") or "").strip()
            if not hp or not it: continue
            if (d, it) in lab: out[(d, hp)] = lab[(d, it)]
    return out

