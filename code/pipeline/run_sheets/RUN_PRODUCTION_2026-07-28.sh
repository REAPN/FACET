#!/usr/bin/env bash

set -u
export FACET_ROOT="${FACET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
cd "$FACET_ROOT" || exit 1
: "${OPENAI_API_KEY:?set OPENAI_API_KEY first}"
M="${MODEL:-gpt-5.4}"
TARGET="${1:-all}"

ARMS=(
  "SCZ_dsmdef:fd777227494a5513:SCZ:1657:6"
  "NCD_dsmdef:991109811bab19ee:NCD:1710:2"
)

prompt_sha () {
  python3 - "$1" <<'PY'
import hashlib, sys
from criterion_spec import load_spec, extract
from criterion_prompt import build_developer_prompt
sp = load_spec(sys.argv[1])
criteria, stems, _ = extract(sp, ".")
print(hashlib.sha256(build_developer_prompt(sp, criteria, stems, mode="joint")
                     .encode("utf-8")).hexdigest()[:16])
PY
}
unit_count () { python3 -c "import json,sys;print(len(json.load(open(sys.argv[1],encoding='utf-8'))['items']))" "$1"; }
rows_of () { python3 -c "import sys;print(sum(1 for _ in open(sys.argv[1],encoding='utf-8'))-1)" "$1"; }

echo "=============================================================="
echo "production gates, $(date -u +%Y-%m-%dT%H:%M:%SZ)"
FAIL=0
for i in "${!ARMS[@]}"; do
  IFS=: read -r SPEC SHA DIS N U <<<"${ARMS[$i]}"
  P="criterion_specs/${SPEC}.json"; S="taxonomy_v2_full/scope_main_${DIS}.tsv"
  GOT=$(prompt_sha "$P" 2>/dev/null); RN=$(rows_of "$S" 2>/dev/null); UN=$(unit_count "$P" 2>/dev/null)
  if   [ "$GOT" != "$SHA" ]; then echo "  $DIS: prompt sha $GOT, FROZEN $SHA  *** MISMATCH"; FAIL=1
  elif [ "$RN"  != "$N"   ]; then echo "  $DIS: scope $RN rows, expected $N  *** MISMATCH"; FAIL=1
  elif [ "$UN"  != "$U"   ]; then echo "  $DIS: $UN scored units, expected $U  *** MISMATCH"; FAIL=1
  else echo "  $DIS: prompt $GOT MATCH, scope $RN rows OK, $UN scored units OK"; fi
done
python3 - <<'PY' || FAIL=1
import hashlib, sys
sys.path.insert(0, ".")
from criterion_spec import load_spec, extract
from criterion_prompt import build_developer_prompt
ok = True
for D, want in (("ASD", "313ec80ceb9d1caf"), ("ID", "e5db1b06dfb0f3bd")):
    sp = load_spec(f"criterion_specs/{D}.json")
    c, s, _ = extract(sp, ".")
    got = hashlib.sha256(build_developer_prompt(sp, c, s, mode="joint").encode()).hexdigest()[:16]
    print(f"  {D}: not re-run, prompt {got} " + ("unchanged" if got == want else f"*** DRIFTED from {want}"))
    ok &= got == want
sys.exit(0 if ok else 1)
PY
if [ "$FAIL" != "0" ]; then
  echo; echo "GATES FAILED. Nothing was spent."
  echo "  rebuild with: python3 build_dsmdef_specs.py --disorders SCZ,NCD \\"
  echo "                  --spec_version 2026-07-28_criterion_plus_dsmdef --no_frozen_check"
  exit 1
fi
echo "gates passed"
echo "=============================================================="
[ "$TARGET" = "gates" ] && exit 0

run () {
  IFS=: read -r SPEC SHA DIS N U <<<"${ARMS[$1]}"
  echo "[$(date -u +%H:%M:%S)] starting $DIS  ($N calls, $U units, model $M)"
  python3 classify_mp_terms_criterion_grounded.py \
    --spec "criterion_specs/${SPEC}.json" \
    --mp_terms "taxonomy_v2_full/scope_main_${DIS}.tsv" \
    --outdir "taxonomy_v2_full/prod_${DIS}_2026-07-28" --model "$M" \
    2>&1 | tail -3
  echo "[$(date -u +%H:%M:%S)] finished $DIS"
}
for i in "${!ARMS[@]}"; do
  IFS=: read -r _ _ DIS _ _ <<<"${ARMS[$i]}"
  if [ "$TARGET" = "all" ] || [ "$TARGET" = "$DIS" ]; then run "$i"; fi
done

echo
echo "score breadth both ways with:"
echo "  python3 score_breadth.py --taxonomy taxonomy_v2_full/prod_SCZ_2026-07-28/03_taxonomy.tsv \\"
echo "                           --spec criterion_specs/SCZ_dsmdef.json --both"
echo
echo "Runs are resumable: re-launch the same command and the classifier picks up from the rows already"
echo "written, refusing to continue if the prompt sha on disk differs from the one that wrote them."
