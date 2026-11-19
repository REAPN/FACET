#!/bin/bash
set -u
cd "$(dirname "$0")/../.." || exit 2
declare -A CFG=([SCZ]=scz.disorder.json [NCD]=neurocognitive.disorder.json)
mkdir -p _judgeswap/runs _judgeswap/logs; L=_judgeswap/logs
one(){ D=$1; X=$2; O=_judgeswap/${D}_${X}; R=_judgeswap/runs/${D}_${X}
  [ -f $O/03_reranked_pairs_filled.tsv ] || { echo "MISSING $O"; return 1; }
  echo "STAGE3 $(date -u +%FT%TZ)" > _judgeswap/${D}_${X}.status
  python3 stage3_aggregate.py --config ${CFG[$D]} --regime off --reranked_pairs_tsv $O/03_reranked_pairs_filled.tsv --outdir_template "${R}_s3_pol{regime}/" > $L/${D}_${X}_s3.log 2>&1 || { echo "FAIL3" > _judgeswap/${D}_${X}.status; return 1; }
  echo "STAGE4 $(date -u +%FT%TZ)" > _judgeswap/${D}_${X}.status
  python3 stage4_permutation_null.py --config ${CFG[$D]} --regime off --reranked_pairs_tsv $O/03_reranked_pairs_filled.tsv --overall_support_tsv "${R}_s3_poloff/06_overall_genotype_support.tsv" --outdir_template "${R}_s4_pol{regime}/" > $L/${D}_${X}_s4.log 2>&1 || { echo "FAIL4" > _judgeswap/${D}_${X}.status; return 1; }
  echo "DONE $(date -u +%FT%TZ)" > _judgeswap/${D}_${X}.status; }
echo "START $(date -u +%FT%TZ)"
one NCD wequal_topup & one SCZ wnolex_topup & wait
cat _judgeswap/NCD_wequal_topup.status _judgeswap/SCZ_wnolex_topup.status
python3 audit/channel_weights_2026-11-08/eval_topup.py
echo "END $(date -u +%FT%TZ)"
