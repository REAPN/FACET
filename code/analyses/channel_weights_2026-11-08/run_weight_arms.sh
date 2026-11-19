#!/bin/bash
set -u
cd "$(dirname "$0")/../.." || exit 2
declare -A CFG=([ASD]=asd.disorder.json [SCZ]=scz.disorder.json [ID]=intellectualdisability_topup20260910.disorder.json [NCD]=neurocognitive.disorder.json)
mkdir -p _judgeswap/runs _judgeswap/logs; L=_judgeswap/logs
python3 audit/channel_weights_2026-11-08/build_weight_arms.py > $L/weight_arms_build.log 2>&1 || { echo "BUILD FAILED"; exit 1; }
one(){ D=$1; X=$2; O=_judgeswap/${D}_${X}; R=_judgeswap/runs/${D}_${X}
  echo "STAGE3 $(date -u +%FT%TZ)" > _judgeswap/${D}_${X}.status
  python3 stage3_aggregate.py --config ${CFG[$D]} --regime off --reranked_pairs_tsv $O/03_reranked_pairs_filled.tsv --outdir_template "${R}_s3_pol{regime}/" > $L/${D}_${X}_s3.log 2>&1 || { echo "FAIL3 $(date -u +%FT%TZ)" > _judgeswap/${D}_${X}.status; return 1; }
  echo "STAGE4 $(date -u +%FT%TZ)" > _judgeswap/${D}_${X}.status
  python3 stage4_permutation_null.py --config ${CFG[$D]} --regime off --reranked_pairs_tsv $O/03_reranked_pairs_filled.tsv --overall_support_tsv "${R}_s3_poloff/06_overall_genotype_support.tsv" --outdir_template "${R}_s4_pol{regime}/" > $L/${D}_${X}_s4.log 2>&1 || { echo "FAIL4 $(date -u +%FT%TZ)" > _judgeswap/${D}_${X}.status; return 1; }
  echo "DONE $(date -u +%FT%TZ)" > _judgeswap/${D}_${X}.status; }
echo "START $(date -u +%FT%TZ)"
for X in wequal wlexf1 wnolex wnoemb wnores wnojac; do
  for D in ASD SCZ ID NCD; do one $D $X & done
  wait; echo "$X finished $(date -u +%FT%TZ)"; cat _judgeswap/*_${X}.status
done
python3 audit/channel_weights_2026-11-08/eval_weights.py
echo "END $(date -u +%FT%TZ)"
