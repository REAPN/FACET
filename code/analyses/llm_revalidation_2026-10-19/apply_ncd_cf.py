#!/usr/bin/env python3
import sys, shutil
import pandas as pd
K = ["target_id", "mp_id", "mp_term"]
a = pd.read_csv("neurocognitive_pair_rerank_v1_ncdB/03_reranked_pairs_filled.tsv", sep="\t", dtype=str, keep_default_na=False)
b = pd.read_csv("neurocognitive_pair_rerank_v1_ncdB_cf/03_reranked_pairs_filled.tsv", sep="\t", dtype=str, keep_default_na=False)
m = a.merge(b, on=K, suffixes=("_a", "_b"))
cf = m[(m.strict_eligible_a.str.lower() == "true") & (m.strict_eligible_b.str.lower() == "false")][K]
assert len(cf) == 15, len(cf)
p = sys.argv[1]
shutil.copy2(p, p + ".pre_cf")
t = pd.read_csv(p, sep="\t", dtype=str, keep_default_na=False)
hit = t.set_index(K).index.isin(cf.set_index(K).index)
was = int((t.loc[hit, "strict_eligible"].str.lower() == "true").sum())
t.loc[hit, "strict_eligible"] = "False"
t.to_csv(p, sep="\t", index=False)
print(f"cf filter: {hit.sum()} keys present, {was} were strict and set False -> {p}")
