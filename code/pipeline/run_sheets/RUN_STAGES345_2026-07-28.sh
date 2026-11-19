#!/usr/bin/env bash

set -u
export FACET_ROOT="${FACET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
cd "$FACET_ROOT" || exit 1
DRY="${DRY_RUN:-0}"
TARGET="${1:-gates}"

declare -A CFG=( [ASD]=asd.disorder.json [SCZ]=scz.disorder.json
                 [ID]=intellectualdisability.disorder.json [NCD]=neurocognitive.disorder.json )

say () { echo "[$(date -u +%H:%M:%S)] $*"; }

readiness () {
  python3 - "${CFG[$1]}" "$1" <<'PY'
import csv, json, os, sys
cfg = json.load(open(sys.argv[1], encoding="utf-8")); D = sys.argv[2]
rr = (cfg.get("stage2_rerank") or {}).get("outdir", "").rstrip("/")
b = os.path.join(rr, "03_reranked_pairs.tsv")
c = os.path.join(rr, "03_reranked_pairs_filled.tsv")
if not os.path.exists(c):
    print(f"  {D}: NOT READY, no stage 2c substrate at {c}"); sys.exit(1)
if os.path.exists(b) and os.path.getmtime(c) < os.path.getmtime(b):
    print(f"  {D}: NOT READY, stage 2c is older than stage 2b"); sys.exit(1)
with open(c, encoding="utf-8", newline="") as fh:
    rows = list(csv.DictReader(fh, delimiter="\t"))
k = {(r.get("target_id"), r.get("hpo_id"), r.get("mp_id")) for r in rows}
if not rows or len(rows) != len(k):
    print(f"  {D}: NOT READY, {len(rows)} rows over {len(k)} unique keys"); sys.exit(1)
tax = (cfg.get("stage2_candidate_features") or {}).get("taxonomy_tsv", "")
if f"criterion_v1_{D}" not in tax:
    print(f"  {D}: NOT READY, config points at {tax}, not its criterion taxonomy"); sys.exit(1)
tu = f"target_units_{D}/03_target_criterion_units.tsv"
print(f"  {D}: READY, {len(rows)} pairs, unique keys, taxonomy {tax}"
      + ("" if os.path.exists(tu) else "   (no target criterion units, gFV runs one arm only)"))
PY
}

regimes_of () { python3 -c "import json,sys;print(' '.join((json.load(open(sys.argv[1],encoding='utf-8')).get('stage3_aggregation') or {}).get('polarity_regimes_to_run',['off'])))" "${CFG[$1]}"; }

run_disorder () {
  local D="$1"
  local C="${CFG[$D]}"
  readiness "$D" || { say "$D is not ready, skipping"; return 1; }
  local REGIMES; REGIMES="$(regimes_of "$D")"
  say "=== $D, regimes: $REGIMES ==="

  if [ "$DRY" = "1" ]; then
    echo "  DRY RUN, nothing written. Planned:"
    for R in $REGIMES; do
      echo "    stage 3 aggregate   --regime $R"
      echo "    stage 4 permutation --regime $R"
      echo "    stage 5 benchmark   --regime $R --mode strict   and   --mode broad"
    done
    echo "    gFV: not run per disorder. Use: bash $0 gfv  (all four in one pass)"
    echo "    (emits the non-criterion HPO exclusion list only)"
    say "=== $D dry run complete, nothing changed ==="
    return 0
  fi

  for R in $REGIMES; do
    say "$D stage 3, regime $R"
    python3 stage3_aggregate.py --config "$C" --regime "$R" || { say "$D stage 3 FAILED"; return 1; }
    say "$D stage 4, regime $R"
    python3 stage4_permutation_null.py --config "$C" --regime "$R" || { say "$D stage 4 FAILED"; return 1; }
    for MODE in strict broad; do
      say "$D stage 5, regime $R, mode $MODE"
      python3 stage5_benchmark.py --config "$C" --regime "$R" --mode "$MODE" \
        || { say "$D stage 5 FAILED ($R/$MODE)"; return 1; }
    done
  done

  say "$D stages 3 to 5 complete. gFV is a separate target: bash $0 gfv"
  if [ -s "target_units_${D}/03_target_criterion_units.tsv" ] && [ ! -s "target_units_${D}/04_noncriterion_hpo_ids.txt" ]; then
    say "$D emitting the non-criterion HPO exclusion list"
    python3 emit_noncriterion_hpo_exclusions.py --disorder "$D" || true
  fi
  say "=== $D done ==="
}

run_gfv () {
  for D in ASD SCZ ID NCD; do
    if [ -s "target_units_${D}/03_target_criterion_units.tsv" ] && [ ! -s "target_units_${D}/04_noncriterion_hpo_ids.txt" ]; then
      say "$D emitting the non-criterion HPO exclusion list"
      python3 emit_noncriterion_hpo_exclusions.py --disorder "$D" || return 1
    fi
  done
  cd mappability_catalog || return 1
  say "gFV reportable arm: strict breadth, leaf depth"
  python3 rebuild_fv_seco_criterion.py --breadth_requires_strict || { say "gFV FAILED"; return 1; }
  say "gFV opt-in arm: SCZ Criterion B counted as provisional"
  python3 rebuild_fv_seco_criterion.py --breadth_requires_strict --include_provisional || return 1
  say "gFV bound: mouse side must name the same criterion unit"
  python3 rebuild_fv_seco_criterion.py --breadth_requires_strict --require_mouse_agreement same || return 1
  cd .. || return 1
  echo "  REPORTABLE ARM: mappability_catalog/genotype_face_validity_seco_criterion_strictonly.tsv"
  echo "  Report _optin and _msame ALONGSIDE it. _msame is a lower bound, not a correction."
  echo "  Numbers of record: CANONICAL_RESULT.md section 1B."
}

__facet_main () {
  case "$TARGET" in
    gates) echo "readiness, $(date -u +%Y-%m-%dT%H:%M:%SZ)"
           for D in ASD SCZ ID NCD; do readiness "$D" || true; done ;;
    gfv) run_gfv ;;
    ASD|SCZ|ID|NCD) run_disorder "$TARGET" ;;
    all) for D in ID SCZ NCD ASD; do run_disorder "$D" || true; done ;;
    *) echo "usage: $0 [gates|ASD|SCZ|ID|NCD|all|gfv]"; exit 2 ;;
  esac
}

__facet_main "$@"
