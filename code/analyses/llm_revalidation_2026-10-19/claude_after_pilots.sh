#!/bin/bash
set -u
CAP=${1:?give the cap in USD, e.g. 70}; H=audit/llm_revalidation_2026-10-19
JOBS="A_ASD A_SCZ A_ID C_ASD C_SCZ C_ID C_NCD"
echo "$(date -u +%FT%TZ) chain started, cap $CAP"
until python3 - <<PY
import json, os, sys
for j in "$JOBS".split():
    f = f"_batches/{j}/results.jsonl"
    n = sum(1 for l in open(f) if '"ok": true' in l) if os.path.exists(f) else 0
    if n < 20: sys.exit(1)
PY
do sleep 30; done
while pgrep -f "claude_batch.py pilot" > /dev/null; do sleep 15; done
echo "$(date -u +%FT%TZ) all pilots in"
for J in $JOBS; do python3 $H/claude_batch.py submit $J --budget_usd $CAP --wait_lock || echo "submit $J refused or failed"; done
python3 $H/claude_batch.py collect $JOBS --wait --wait_lock
python3 $H/claude_batch.py status
for D in ASD SCZ ID; do bash $H/run_judgeswap.sh $D claude & done; wait
for D in ASD SCZ ID NCD; do python3 $H/reclassify_mp_criterion_independent.py --disorder $D --backend claude --model claude-opus-4-8 \
  --terms_file _reclass/sample/partC_sample_$D.tsv --ingest _batches/C_$D/results.jsonl --no_api; done
for D in ASD SCZ ID; do echo "$D: $(cat _judgeswap/${D}_claude.status)"; done
python3 $H/llm_budget.py
echo "$(date -u +%FT%TZ) chain finished"
