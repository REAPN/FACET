#!/bin/bash
set -u
D=$1
declare -A CFG=([ASD]=asd.disorder.json [SCZ]=scz.disorder.json [ID]=intellectualdisability_topup20260910.disorder.json [NCD]=neurocognitive.disorder.json)
[ -z "${CFG[$D]:-}" ] && { echo "disorder?"; exit 2; }
mkdir -p _nullmirror/logs
st(){ echo "$1 $(date -u +%FT%TZ)" > _nullmirror/${D}.status; }
st RUN
python3 permutation_null_mirrored.py --config ${CFG[$D]} --regime off --outdir_template "_nullmirror/${D}_s4_pol{regime}/" > _nullmirror/logs/${D}.log 2>&1 \
  && st DONE || { st FAIL; echo "see _nullmirror/logs/${D}.log"; exit 1; }
