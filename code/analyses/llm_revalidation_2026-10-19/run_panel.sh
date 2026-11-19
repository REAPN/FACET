#!/bin/bash
set -u
D=$1; X=panel; H=audit/llm_revalidation_2026-10-19; O=_judgeswap/${D}_${X}; L=_judgeswap/logs; mkdir -p $L _judgeswap/runs
declare -A CFG=([ASD]=asd.disorder.json [SCZ]=scz.disorder.json [ID]=intellectualdisability_topup20260910.disorder.json [NCD]=neurocognitive.disorder.json)
st(){ echo "$1 $(date -u +%FT%TZ)" > _judgeswap/${D}_${X}.status; }
if [ "$D" = "NCD" ] && [ ! -f $O/03_reranked_pairs_filled.tsv.pre_cf ]; then
  python3 $H/apply_ncd_cf.py $O/03_reranked_pairs_filled.tsv >> $L/${D}_${X}_judge.log 2>&1 || { st FAIL_CF; exit 1; }
fi
R=_judgeswap/runs/${D}_${X}
st STAGE3
python3 stage3_aggregate.py --config ${CFG[$D]} --regime off --reranked_pairs_tsv $O/03_reranked_pairs_filled.tsv --outdir_template "${R}_s3_pol{regime}/" > $L/${D}_${X}_s3.log 2>&1 || { st FAIL3; exit 1; }
st STAGE4
python3 stage4_permutation_null.py --config ${CFG[$D]} --regime off --reranked_pairs_tsv $O/03_reranked_pairs_filled.tsv --overall_support_tsv "${R}_s3_poloff/06_overall_genotype_support.tsv" --outdir_template "${R}_s4_pol{regime}/" > $L/${D}_${X}_s4.log 2>&1 || { st FAIL4; exit 1; }
st DONE; cat _judgeswap/${D}_${X}.status
