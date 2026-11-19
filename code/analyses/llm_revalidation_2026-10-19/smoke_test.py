#!/usr/bin/env python3
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
import pandas as pd
import rerank_ambiguous_pairs_api_v3 as R, rerank_independent_judge as RIJ, judge_backends as JB
sys.path.insert(0, "audit/llm_revalidation_2026-10-19")
from rejudge_record_pairs import typed
t = typed(pd.read_csv("neurocognitive_pair_rerank_v1_ncdB_cf/03_reranked_pairs_filled.tsv", sep="\t", low_memory=False))
j = t[t["rerank_action"].notna()]
g = j[j["target_id"] == j["target_id"].iloc[0]].head(5)
f = g.iloc[0]
user = RIJ.build_user_prompt(f["target_id"], str(f["hpo_label"]), str(f["target_text"]), str(f["human_domain"]), g)
for b, m in (("claude", os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")), ("gemini", os.environ.get("GEMINI_MODEL", "gemini-2.5-pro"))):
    try:
        o = JB.bundle_judgment(b, m, RIJ.BASE_DEV_PROMPT, user, seed=1, schema=R.RERANK_SCHEMA)
        print(b, m, "OK", [(x.get("candidate_index"), x.get("strict_eligible"), x.get("behavioral_analog_type")) for x in o.get("selected_candidates", [])])
    except Exception as e:
        import re
        print(b, m, "FAILED", type(e).__name__, re.sub(r"(sk-|AIza)[A-Za-z0-9_\-]+", "[redacted]", str(e))[:200])
