#!/bin/bash
set -u
CAP=${1:?give the cap in USD}; H=audit/llm_revalidation_2026-10-19
J="A_ASD A_SCZ A_ID A_NCD C_ASD C_SCZ C_ID C_NCD"
echo "$(date -u +%FT%TZ) gemini chain started, cap $CAP"
python3 $H/gemini_batch.py pilot $J --n 20 --budget_usd $CAP || { echo "pilot step failed"; exit 1; }
python3 $H/gemini_batch.py run $J --budget_usd $CAP || { echo "run step stopped (see above)"; exit 1; }
python3 $H/gemini_batch.py status
for D in ASD SCZ ID NCD; do GEMINI_BUDGET_USD=$CAP GEMINI_INGEST=1 bash $H/run_judgeswap.sh $D gemini 2 & done; wait
for D in ASD SCZ ID NCD; do python3 $H/reclassify_mp_criterion_independent.py --disorder $D --backend gemini --model gemini-2.5-pro \
  --terms_file _reclass/sample/partC_sample_$D.tsv --ingest _gbatches/C_$D/results.jsonl --no_api; done
for D in ASD SCZ ID NCD; do echo "$D: $(cat _judgeswap/${D}_gemini.status)"; done
python3 $H/llm_budget.py
echo "$(date -u +%FT%TZ) gemini chain finished"
