import os

FACET_ROOT = os.environ.get("FACET_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
U = FACET_ROOT


RUNS_PRECRITERION = {
    "ASD": {"pos": "ASD_primary",
            "labels": "broad_benchmark_setup/01_all_genotype_summary.csv",
            "pval": "benchmark/run_2026-05-11_v3_poloff_strict/00_score_filtered_strict.tsv",
            "bench": "benchmark/run_2026-05-11_v3_poloff_strict"},
    "SCZ": {"pos": "SCZ_primary",
            "labels": "benchmark_tables_per_tier/SCZ_tier_0.csv",
            "pval": "benchmark/run_2026-05-28_v2_scz_poloff_strict/00_score_filtered_strict.tsv",
            "bench": "benchmark/run_2026-05-28_v2_scz_poloff_strict"},
    "ID":  {"pos": "IntellectualDisability_primary",
            "labels": "benchmark_tables_per_tier/IntellectualDisability_tier_0.csv",
            "pval": "benchmark/run_2026-06-02_v1_intellectualdisability_poloff_strict/00_score_filtered_strict.tsv",
            "bench": "benchmark/run_2026-06-02_v1_intellectualdisability_poloff_strict",
            "destroyed": "overwritten 2026-07-28 by the outdir_template repoint"},
    "NCD": {"pos": "Neurocognitive_primary",
            "labels": "benchmark_tables_per_tier/SCZ_tier_0.csv",
            "pval": "benchmark/run_2026-07-27_v1_neurocognitive_poloff_strict/00_score_filtered_strict.tsv",
            "bench": "benchmark/run_2026-07-27_v1_neurocognitive_poloff_strict"},
}

_CRIT = "benchmark/run_2026-07-28_criterion_v1_%s_poloff_strict"
RUNS_CRITERION = {
    "ASD": {"pos": "ASD_primary",
            "labels": "broad_benchmark_setup/01_all_genotype_summary.csv",
            "pval": _CRIT % "asd" + "/00_score_filtered_strict.tsv",
            "bench": _CRIT % "asd"},
    "SCZ": {"pos": "SCZ_primary",
            "labels": "benchmark_tables_per_tier/SCZ_tier_0.csv",
            "pval": _CRIT % "scz" + "/00_score_filtered_strict.tsv",
            "bench": _CRIT % "scz"},
    "ID":  {"pos": "IntellectualDisability_primary",
            "labels": "benchmark_tables_per_tier/IntellectualDisability_tier_0.csv",
            "pval": _CRIT % "intellectualdisability" + "/00_score_filtered_strict.tsv",
            "bench": _CRIT % "intellectualdisability"},
    "NCD": {"pos": "Neurocognitive_primary",
            "labels": "benchmark_tables_per_tier/SCZ_tier_0.csv",
            "pval": _CRIT % "neurocognitive" + "/00_score_filtered_strict.tsv",
            "bench": _CRIT % "neurocognitive"},
}

SUBSTRATE = os.environ.get("FACET_SUBSTRATE", "criterion").strip().lower()
if SUBSTRATE not in ("criterion", "precriterion"):
    raise SystemExit("FACET_SUBSTRATE must be 'criterion' or 'precriterion', got %r" % SUBSTRATE)

RUNS = dict(RUNS_CRITERION if SUBSTRATE == "criterion" else RUNS_PRECRITERION)
REF_ENFORCED = (SUBSTRATE == "precriterion")
OUT_TAG = "" if SUBSTRATE == "precriterion" else "_criterion"

_dead = {k: v["destroyed"] for k, v in RUNS.items() if "destroyed" in v}
if _dead:
    raise SystemExit(
        "FACET_SUBSTRATE=%s cannot run: %s\n"
        "The ratified numbers for these disorders cannot be recomputed from source. Use\n"
        "FACET_SUBSTRATE=criterion (the default) for the current substrate, and quote the\n"
        "ratified values from CANONICAL_RESULT.md as historical."
        % (SUBSTRATE, "; ".join("%s: %s" % kv for kv in _dead.items())))

for _k, _r in RUNS.items():
    _p = os.path.join(U, _r["pval"])
    if not os.path.exists(_p):
        raise SystemExit(
            "substrate %s: %s score file missing\n  %s\n"
            "Do NOT repoint this at a surviving directory of a different generation. Check\n"
            "COMPUTATION_WINGS_LOCK_2026-07-28.md before changing any pointer here."
            % (SUBSTRATE, _k, _p))
