#!/usr/bin/env bash

set -u
export FACET_ROOT="${FACET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
cd "$FACET_ROOT" || exit 1
M="${MODEL:-gpt-5.4}"
TARGET="${1:-gates}"
DRY="${DRY_RUN:-0}"

declare -A CFG=(  [ASD]=asd.disorder.json [SCZ]=scz.disorder.json
                  [ID]=intellectualdisability.disorder.json [NCD]=neurocognitive.disorder.json )
declare -A TAXDIR=( [ASD]=mp_term_taxonomy_criterion_v1_ASD [SCZ]=mp_term_taxonomy_criterion_v1_SCZ
                    [ID]=mp_term_taxonomy_criterion_v1_ID   [NCD]=mp_term_taxonomy_criterion_v1_NCD )
declare -A RUNDIR=( [ASD]=taxonomy_v2_full/run_ASD [ID]=taxonomy_v2_full/run_ID
                    [SCZ]=taxonomy_v2_full/prod_SCZ_2026-07-28
                    [NCD]=taxonomy_v2_full/prod_NCD_2026-07-28 )
declare -A BASETAX=( [ASD]=mp_term_taxonomy_broad_v3 [SCZ]=mp_term_taxonomy_scz_5domain_v1
                     [ID]=mp_term_taxonomy_id_v1     [NCD]=mp_term_taxonomy_neurocognitive_v1 )
declare -A NEEDS_TAXRUN=( [ASD]=no [ID]=no [SCZ]=yes [NCD]=yes )
declare -A NEEDS_STAGE1=( [ASD]=yes [ID]=no [SCZ]=no [NCD]=yes )

say () { echo "[$(date -u +%H:%M:%S)] $*"; }

gates () {
  local fail=0
  echo "=============================================================="
  echo "front end gates, $(date -u +%Y-%m-%dT%H:%M:%SZ)"

  python3 - <<'PY' || fail=1
import io, sys
ok = True
s = io.open("build_candidate_feature_table.py", encoding="utf-8").read()
if 'drop_duplicates(subset=["mp_id"], keep="first")' not in s:
    print("  B1 site 1 fix ABSENT from build_candidate_feature_table.py"); ok = False
else:
    print("  B1 site 1 fix present")
for f, need, label in (
    ("rerank_score_floor_fill.py",
     ['fill_df.drop_duplicates(subset=key, keep="last")', "B1 regression", "B1 NOT SATISFIED"],
     "site 2, the fill merge"),
    ("rerank_ambiguous_pairs_api_v3.py",
     ['drop_duplicates(subset=["target_id", "candidate_index"], keep="last")',
      "the rerank merge changed the row count"],
     "site 3, stage 2b appending to its own raw jsonl"),
    ("stage2c_score_floor_fill.py",
     ["B1 regression in the reuse path", "B1 NOT SATISFIED in the reuse path"],
     "site 4, the second writer in the reuse path"),
):
    src = io.open(f, encoding="utf-8").read()
    miss = [n for n in need if n not in src]
    if miss:
        print(f"  B1 {label}: INCOMPLETE in {f}"); ok = False
    else:
        print(f"  B1 {label}: present")
sys.exit(0 if ok else 1)
PY

  python3 - <<'PY' || fail=1
import io, sys
p = "DSM5_paraphrased/ASD_core_text.txt"
t = io.open(p, encoding="utf-8", errors="replace").read()
hasB = "Narrow, repeated patterns" in t
hasB4 = "under-response to sensory stimulation" in t
print(f"  B2 ASD core file {len(t)} bytes, criterion B {hasB}, B4 sensory item {hasB4}")
sys.exit(0 if (hasB and hasB4) else 1)
PY

  python3 - <<'PY' || fail=1
import csv, json, os, sys
W = {"asd": "ASD", "scz": "SCZ", "intellectualdisability": "ID", "neurocognitive": "NCD"}
tiers, ok = {}, True
for f, D in W.items():
    cfg = json.load(open(f + ".disorder.json", encoding="utf-8"))
    t = (cfg.get("stage2_candidate_features") or {}).get("taxonomy_tsv", "")
    if f"criterion_v1_{D}" not in t:
        print(f"  {D}: config still points at {t}"); ok = False; continue
    if not os.path.exists(t):
        print(f"  {D}: taxonomy not built yet at {t}"); continue
    rows = list(csv.DictReader(open(t, encoding="utf-8"), delimiter="\t"))
    tiers[D] = {r["mp_id"]: r["relevance_tier"] for r in rows}
    gate = sum(1 for r in rows if r["relevance_tier"] in ("1", "3", "4"))
    print(f"  {D}: {t}  {len(rows)} rows, candidate universe {gate}")
ks = sorted(tiers)
for i, a in enumerate(ks):
    for b in ks[i + 1:]:
        common = set(tiers[a]) & set(tiers[b])
        same = sum(1 for k in common if tiers[a][k] == tiers[b][k])
        if same == len(common):
            print(f"  {a} and {b} still share an IDENTICAL relevance_tier column"); ok = False
sys.exit(0 if ok else 1)
PY

  python3 - <<'PY' || fail=1
import csv, glob, sys
ok = True
for p in sorted(glob.glob("mp_term_taxonomy_criterion_v1_*/03_mp_term_taxonomy.tsv")):
    with open(p, encoding="utf-8", newline="") as fh:
        r = csv.DictReader(fh, delimiter="\t"); rows = list(r); cols = r.fieldnames
    D = p.split("_v1_")[1].split("/")[0]
    need = [c for c in ("asd_direction_consistency", "polarity", "primary_domain") if c not in cols]
    t1 = [x for x in rows if x["relevance_tier"] == "1"]
    anti = [x for x in t1 if str(x.get("criterion_admissible_directionaware", "")).lower() != "true"]
    gate = sum(1 for x in rows if x["relevance_tier"] in ("1", "2", "3", "4"))
    print(f"  {D}: universe {gate} at isin([1,2,3,4]), tier1 {len(t1)}, "
          f"direction-inconsistent tier1 {len(anti)}"
          + (f", MISSING COLUMNS {need}" if need else ""))
    if need or anti:
        ok = False
sys.exit(0 if ok else 1)
PY

  if [ "$fail" != "0" ]; then
    echo; echo "GATES FAILED. Nothing was spent."; return 1
  fi
  echo "gates passed"
  echo "=============================================================="
  return 0
}

build_taxonomy () {
  local D="$1"
  local run="${RUNDIR[$D]}/03_taxonomy.tsv"
  local out="${TAXDIR[$D]}"
  if [ -s "$out/03_mp_term_taxonomy.tsv" ] && [ "$out/03_mp_term_taxonomy.tsv" -nt "$run" ]; then
    say "$D taxonomy already current, skipping"; return 0
  fi
  [ -s "$run" ] || { say "$D: $run missing, cannot build taxonomy"; return 1; }
  say "$D building stage-2a taxonomy from $run"
  python3 build_stage2a_taxonomy.py --disorder "$D" --run "$run" \
      --base_taxonomy "${BASETAX[$D]}/03_mp_term_taxonomy.tsv" --outdir "$out" || return 1
}

run_disorder () {
  local D="$1"
  local C="${CFG[$D]}"
  say "=== $D start ==="
  if [ "$DRY" = "1" ]; then
    echo "  DRY RUN, nothing is written, renamed or billed. Planned steps for $D:"
    [ "${NEEDS_TAXRUN[$D]}" = "yes" ] && [ ! -s "${RUNDIR[$D]}/03_taxonomy.tsv" ] \
      && echo "    1. criterion taxonomy run (LLM)" \
      || echo "    1. criterion taxonomy run: skip, ${RUNDIR[$D]}/03_taxonomy.tsv present"
    [ -s "${TAXDIR[$D]}/03_mp_term_taxonomy.tsv" ] \
      && echo "    2. build stage-2a taxonomy: present, rebuilt only if the run is newer" \
      || echo "    2. build stage-2a taxonomy"
    [ "${NEEDS_STAGE1[$D]}" = "yes" ] && echo "    3. stage 1 HPO curation (LLM)" \
      || echo "    3. stage 1: not needed for $D"
    [ -s "target_units_${D}/03_target_criterion_units.tsv" ] \
      && echo "    4. target criterion units: present, skip" \
      || echo "    4. decompose targets to criterion units (LLM)"
    echo "    5. archive any stale stage 2b/2c, then stage 2a, 2b (LLM), 2c (LLM)"
    python3 - "$C" <<'PY'
import json, os, sys
cfg = json.load(open(sys.argv[1], encoding="utf-8"))
cf = (cfg.get("stage2_candidate_features") or {}).get("outdir", "").rstrip("/")
rr = (cfg.get("stage2_rerank") or {}).get("outdir", "").rstrip("/")
prev = None
for name, p in (("2a", os.path.join(cf, "03_candidate_pairs.tsv")),
                ("2b", os.path.join(rr, "03_reranked_pairs.tsv")),
                ("2c", os.path.join(rr, "03_reranked_pairs_filled.tsv"))):
    t = os.path.getmtime(p) if os.path.exists(p) else None
    tag = "absent" if t is None else ("STALE, would be archived" if prev and t < prev else "current")
    print(f"       {name}: {tag}")
    if t is not None and not (prev and t < prev):
        prev = t
PY
    say "=== $D dry run complete, nothing changed ==="
    return 0
  fi

  if [ "${NEEDS_TAXRUN[$D]}" = "yes" ] && [ ! -s "${RUNDIR[$D]}/03_taxonomy.tsv" ]; then
    say "$D criterion taxonomy run"
    bash RUN_PRODUCTION_2026-07-28.sh "$D" || { say "$D taxonomy run FAILED"; return 1; }
  fi
  build_taxonomy "$D" || return 1

  if [ "${NEEDS_STAGE1[$D]}" = "yes" ]; then
    say "$D stage 1, HPO curation, on the B-restored core file"
    python3 stage1_curate_hpo.py --config "$C" || { say "$D stage 1 FAILED"; return 1; }
  fi

  TU="target_units_${D}/03_target_criterion_units.tsv"
  if [ ! -s "$TU" ]; then
    say "$D decomposing stage 1 targets to criterion units"
    HPO="$(python3 -c "import json,sys,os;d=(json.load(open(sys.argv[1],encoding='utf-8')).get('stage1_hpo_curation') or {}).get('outdir','');print(os.path.join(d.rstrip('/'),'07_final_resolved_hpo_terms.tsv'))" "$C")"
    python3 decompose_targets_to_criterion_units.py --disorder "$D"       --spec "criterion_specs/${D}.json" --targets "$HPO"       --outdir "target_units_${D}" --model "$M" || { say "$D target decomposition FAILED"; return 1; }
  else
    say "$D target criterion units already present, skipping"
  fi

  python3 - "$C" <<'PY' || { say "$D could not resolve its stage 2 directories from $C"; return 1; }
import json, os, sys, time
cfg = json.load(open(sys.argv[1], encoding="utf-8"))
cf = (cfg.get("stage2_candidate_features") or {}).get("outdir", "").rstrip("/")
rr = (cfg.get("stage2_rerank") or {}).get("outdir", "").rstrip("/")
if not cf or not rr:
    sys.exit(1)
chain = [("stage 2a", os.path.join(cf, "03_candidate_pairs.tsv")),
         ("stage 2b", os.path.join(rr, "03_reranked_pairs.tsv")),
         ("stage 2c", os.path.join(rr, "03_reranked_pairs_filled.tsv"))]
stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
prev_t, archived = None, []
for name, p in chain:
    t = os.path.getmtime(p) if os.path.exists(p) else None
    if t is not None and prev_t is not None and t < prev_t:
        dest = p + ".superseded_" + stamp
        os.rename(p, dest)
        archived.append(f"{name}: {p} -> {os.path.basename(dest)}")
        t = None
    prev_t = t if t is not None else prev_t
if archived:
    print("  archived stale downstream artifacts, this run regenerates them in order:")
    for a in archived:
        print("    " + a)
else:
    print("  stage 2 chain is consistent, nothing archived")
PY

  say "$D stage 2a, candidate features"
  python3 stage2a_candidate_features.py --config "$C" || { say "$D stage 2a FAILED"; return 1; }

  RAW="$(python3 -c "import json,sys,os;d=(json.load(open(sys.argv[1],encoding='utf-8')).get('stage2_rerank') or {}).get('outdir','');print(os.path.join(d.rstrip('/'),'02_rerank_raw.jsonl'))" "$C")"
  [ -n "$RAW" ] || { say "$D could not resolve the rerank outdir from $C"; return 1; }
  if [ -s "$RAW" ]; then
    say "$D archiving an existing $RAW so stage 2b cannot append to it"
    mv "$RAW" "${RAW}.superseded_$(date -u +%Y%m%dT%H%M%SZ)" || return 1
  fi

  say "$D stage 2b, rerank"
  python3 stage2b_rerank.py --config "$C" --model "$M" || { say "$D stage 2b FAILED"; return 1; }

  python3 - "$C" <<'PY' || { say "$D stage 2b output is not unique, refusing to spend on 2c"; return 1; }
import csv, json, os, sys
cfg = json.load(open(sys.argv[1], encoding="utf-8"))
d = (cfg.get("stage2_rerank") or {}).get("outdir", "")
p = os.path.join(d, "03_reranked_pairs.tsv")
with open(p, encoding="utf-8", newline="") as fh:
    rows = list(csv.DictReader(fh, delimiter="	"))
k = [c for c in ("target_id", "hpo_id", "mp_id") if c and rows and c in rows[0]]
u = len({tuple(r[c] for c in k) for r in rows})
print(f"  pre-2c gate: {len(rows)} rows, {u} unique {tuple(k)} keys, "
      f"{'CLEAN' if u == len(rows) else '*** ' + str(len(rows) - u) + ' DUPLICATES'}")
if not rows:
    print("  pre-2c gate: stage 2b wrote NO data rows, refusing to continue")
sys.exit(0 if (rows and u == len(rows)) else 1)
PY

  say "$D stage 2c, score floor fill"
  python3 stage2c_score_floor_fill.py --config "$C" --model "$M" || { say "$D stage 2c FAILED"; return 1; }

  python3 - "$C" <<'PY' || { say "$D B1 acceptance FAILED, the written substrate has duplicates"; return 1; }
import csv, json, os, sys
cfg = json.load(open(sys.argv[1], encoding="utf-8"))
d = (cfg.get("stage2_rerank") or {}).get("outdir", "")
p = os.path.join(d, "03_reranked_pairs_filled.tsv")
with open(p, encoding="utf-8", newline="") as fh:
    rows = list(csv.DictReader(fh, delimiter="\t"))
keys = {(r.get("target_id"), r.get("hpo_id"), r.get("mp_id")) for r in rows}
print(f"  B1 acceptance: {len(rows)} rows, {len(keys)} unique keys, "
      f"{'CLEAN' if len(rows) == len(keys) else '*** ' + str(len(rows) - len(keys)) + ' DUPLICATES'}")
sys.exit(0 if (rows and len(rows) == len(keys)) else 1)
PY
  say "=== $D done ==="
}

__facet_main () {
  case "$TARGET" in
    gates) gates ;;
    ASD|SCZ|ID|NCD) gates && run_disorder "$TARGET" ;;
    all) gates && for D in SCZ NCD ASD ID; do run_disorder "$D"; done ;;
    *) echo "usage: $0 [gates|ASD|SCZ|ID|NCD|all]"; exit 2 ;;
  esac
}

__facet_main "$@"
