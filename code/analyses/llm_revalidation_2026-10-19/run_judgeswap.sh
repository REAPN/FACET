#!/bin/bash
set -u
D=$1; X=$2; W=${3:-4}
CLAUDE_MODEL=${CLAUDE_MODEL:-claude-opus-4-8}; GEMINI_MODEL=${GEMINI_MODEL:-gemini-2.5-pro}; OPENAI_MODEL=${OPENAI_MODEL:-gpt-5.4}
declare -A CFG=([ASD]=asd.disorder.json [SCZ]=scz.disorder.json [ID]=intellectualdisability_topup20260910.disorder.json [NCD]=neurocognitive.disorder.json)
case $X in claude) M=$CLAUDE_MODEL;; gemini) M=$GEMINI_MODEL;; openai) M=$OPENAI_MODEL;; cached) M=record;; *) echo "backend?"; exit 2;; esac
H=audit/llm_revalidation_2026-10-19; O=_judgeswap/${D}_${X}; L=_judgeswap/logs; mkdir -p $O $L _judgeswap/runs
st(){ echo "$1 $(date -u +%FT%TZ)" > _judgeswap/${D}_${X}.status; }
st JUDGE
EXTRA=""
case $X in
  claude) EXTRA="--no_api"; [ -f _batches/A_${D}/results.jsonl ] && EXTRA="--ingest _batches/A_${D}/results.jsonl --no_api";;
  gemini) [ -z "${GEMINI_BUDGET_USD:-}" ] && { echo "set GEMINI_BUDGET_USD (spend cap, USD) first"; st FAIL_NOBUDGET; exit 1; }
          EXTRA="--budget_usd $GEMINI_BUDGET_USD"; [ -n "${PILOT:-}" ] && EXTRA="$EXTRA --max_calls $PILOT"
          [ -n "${GEMINI_INGEST:-}" ] && EXTRA="--budget_usd $GEMINI_BUDGET_USD --ingest _gbatches/A_${D}/results.jsonl --no_api"
          [ -n "${GEMINI_INGEST_SYNC:-}" ] && EXTRA="--budget_usd $GEMINI_BUDGET_USD --ingest _gbatches/A_${D}/results.jsonl";;
  openai) [ -z "${OPENAI_BUDGET_USD:-}" ] && { echo "set OPENAI_BUDGET_USD (spend cap, USD) first"; st FAIL_NOBUDGET; exit 1; }
          { [ -z "${OPENAI_PRICE_IN_PER_M:-}" ] || [ -z "${OPENAI_PRICE_OUT_PER_M:-}" ]; } && echo "note: no OPENAI_PRICE_* in the shell, the ledger assumes 2.50 in and 15.00 out per million tokens (high on purpose); real spend is on the OpenAI dashboard"
          EXTRA="--budget_usd $OPENAI_BUDGET_USD"; [ -n "${PILOT:-}" ] && EXTRA="$EXTRA --max_calls $PILOT";;
esac
python3 $H/rejudge_record_pairs.py --disorder $D --backend $X --model $M --workers $W --outdir $O $EXTRA >> $L/${D}_${X}_judge.log 2>&1
rc=$?
if [ $rc -eq 7 ]; then st PILOT_DONE; tail -n 1 $L/${D}_${X}_judge.log; exit 0; fi
if [ $rc -ne 0 ]; then st FAIL_JUDGE_rc$rc; echo "judge step rc=$rc, see $L/${D}_${X}_judge.log (re-run to resume)"; exit 1; fi
if [ "$D" = "NCD" ] && [ ! -f $O/03_reranked_pairs_filled.tsv.pre_cf ]; then
  python3 $H/apply_ncd_cf.py $O/03_reranked_pairs_filled.tsv >> $L/${D}_${X}_judge.log 2>&1 || { st FAIL_CF; exit 1; }
fi
R=_judgeswap/runs/${D}_${X}
st STAGE3
python3 stage3_aggregate.py --config ${CFG[$D]} --regime off --reranked_pairs_tsv $O/03_reranked_pairs_filled.tsv --outdir_template "${R}_s3_pol{regime}/" > $L/${D}_${X}_s3.log 2>&1 || { st FAIL3; exit 1; }
st STAGE4
python3 stage4_permutation_null.py --config ${CFG[$D]} --regime off --reranked_pairs_tsv $O/03_reranked_pairs_filled.tsv --overall_support_tsv "${R}_s3_poloff/06_overall_genotype_support.tsv" --outdir_template "${R}_s4_pol{regime}/" > $L/${D}_${X}_s4.log 2>&1 || { st FAIL4; exit 1; }
st DONE
