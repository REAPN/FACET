#!/bin/bash
set -u
CAP=${1:?give the cap in USD}; H=audit/llm_revalidation_2026-10-19
echo "$(date -u +%FT%TZ) gemini resume 2 started, cap $CAP"
python3 $H/gemini_batch.py run C_ASD C_SCZ C_ID C_NCD --budget_usd $CAP || echo "part C run step stopped (see above); continuing with part A"
python3 $H/gemini_batch.py status
for D in ASD SCZ NCD; do GEMINI_BUDGET_USD=$CAP GEMINI_INGEST=1 bash $H/run_judgeswap.sh $D gemini 2 & done
GEMINI_BUDGET_USD=$CAP GEMINI_INGEST_SYNC=1 bash $H/run_judgeswap.sh ID gemini 2 &
wait
for D in ASD SCZ ID NCD; do python3 $H/reclassify_mp_criterion_independent.py --disorder $D --backend gemini --model gemini-2.5-pro \
  --terms_file _reclass/sample/partC_sample_$D.tsv --ingest _gbatches/C_$D/results.jsonl --no_api; done
for D in ASD SCZ ID NCD; do echo "$D: $(cat _judgeswap/${D}_gemini.status)"; done
python3 $H/llm_budget.py
echo "$(date -u +%FT%TZ) gemini resume 2 finished"
