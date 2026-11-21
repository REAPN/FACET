# Code

Every script that produced a result reported in the manuscript or its supplement. The scripts import one another and read their inputs by paths relative to one project root, so they run from the working tree that `tools/make_worktree.py` builds (see the main README). The table below gives the path of each script in that tree.

## Groups

| Folder | What it does |
|---|---|
| `pipeline/0_genotypes_and_labels/` | the 32,535 genotypes and the curated-model labels |
| `pipeline/1_criterion_anchors/` | resolution of criteria to HPO anchors and attribution of anchors to criterion units |
| `pipeline/2_mouse_term_grounding/` | mapping of MP terms to criteria (mouse criterion mapping), with the criterion specifications |
| `pipeline/3_pair_judgment/` | retrieval of candidate pairs and the LLM judgment |
| `pipeline/4_diagnostic_coverage/` | the per-genotype catalogue |
| `pipeline/5_support_score/` | the support score, the permutation nulls and the benchmarks |
| `pipeline/configs/`, `pipeline/run_sheets/`, `pipeline/shared/` | the disorder configurations, the primary run sheets and shared modules |
| `analyses/` | one folder per analysis, with its driver and its pre-specification where one was written. `analyses/geneclust_2026-10-08/common.py` holds the shared loaders (gene clustering, bootstrap, AUROC) |
| `expert_study/` | instrument build, design check and agreement analysis |
| `figures/`, `supplement_tables/` | the figure builders and the scripts behind S1, S4, S5, S7, S9 and S11 Tables and S1 Fig |

## Running a script

```
python3 tools/make_worktree.py work && cd work && export FACET_ROOT=$PWD
python3 audit/composition_2026-11-06/composition.py
```

Scripts run from the project root (the `work` folder), where the folders of `analyses/` stand under `audit/`. Two run from their own folder, because they import `common` and read the files beside them: `audit/geneclust_2026-10-08/cross.py` and `audit/geneclust_2026-10-08/ncd_wpw_removed_2026-11-02.py` (three parts, called with `1`, `2` and `3`). The supplement table scripts are placed in `work/scripts/`.

Comments and docstrings are removed from every script. Each script was compared with its commented source by syntax tree, and no statement differs.

## Checks

Each script below was rerun from a tree rebuilt from this repository, with no LLM call.

| Outcome | Scripts |
|---|---|
| Output identical to the recorded file | `composition.py`, `depth_matched_intervals_2026-11-02.py`, `ncd_wpw_removed_2026-11-02.py` (parts 1 to 3), `ncd_wpw_removed_claimpaper_2026-11-02.py`, `eval_depthstrat.py`, `eval_floor.py` |
| Output equals the reported table | `trivial_baselines_2026-11-02.py` and `llm_ablation_2026-11-02.py` (all four disorders), `landscape.py`, `cross.py`, `s1_rule_check.py`, `s5_hgenes.py`, `s7_composition.py`, `s9_allele_design.py`, `s11_anchors.py`, `s1fig_overlap.py` |
| Inputs present, not rerun (run time) | `eval_weights.py`, `eval_topup.py`, `eval_mirror.py`, `stage3_aggregate.py`, `stage4_permutation_null.py`, `stage5_benchmark.py` |
| Not rerun | `bias.py`, `phenodigm_null.py`, `detail.py`, `run_geneclust.py`, `evalA3.py` |
| Needs an input that is not deposited | `impc_test.py` (IMPC download), `_rating_analysis_v9.py`, `rater_breakdown.py`, `retrieval_vs_llm.py`, `single_rater_agreement.py`, `panel_*_vs_raters*.py` (rater files and answer key), `item5c_abstract_family.py` and `s4_holm_recompute.py` (intermediate family file), `ncd_wpw_removed_relatives_2026-11-02.py` |
| Calls an LLM | the anchoring and judgment scripts, `rejudge_record_pairs.py`, `reassign_units_independent.py`, `reclassify_mp_criterion_independent.py`, `topup_weight_arm.py`, the anchor-gate rerun |

## Script index

Generated from `MANIFEST.tsv`.

| Script | Reported in |
|---|---|
| `analyses/anchor_gate_2026-11-07/build_gate_sets.py` | S21 and S22 Tables |
| `analyses/anchor_gate_2026-11-07/run_scz_gate.py` | S21 and S22 Tables |
| `analyses/anchor_gate_2026-11-07/score_gate.py` | S21 and S22 Tables |
| `analyses/channel_weights_2026-11-08/build_weight_arms.py` | S31 Table |
| `analyses/channel_weights_2026-11-08/eval_topup.py` | S31 Table |
| `analyses/channel_weights_2026-11-08/eval_weights.py` | S31 Table |
| `analyses/channel_weights_2026-11-08/run_topup_arms.sh` | S31 Table |
| `analyses/channel_weights_2026-11-08/run_weight_arms.sh` | S31 Table |
| `analyses/channel_weights_2026-11-08/topup_weight_arm.py` | S31 Table |
| `analyses/composition_2026-11-06/composition.py` | Figure 3, S16 Table |
| `analyses/consolidation_2026-10-12/c4_drift.py` | Methods, database drift |
| `analyses/detail_sensitivity_2026-10-09/detail.py` | S1 Text, annotation detail |
| `analyses/detail_sensitivity_2026-10-09/tier_sweep.py` | S1 Text, annotation detail |
| `analyses/floor_sweep_record_2026-11-08/build_floor_arms.py` | S30 Table |
| `analyses/floor_sweep_record_2026-11-08/eval_floor.py` | S30 Table |
| `analyses/floor_sweep_record_2026-11-08/floor_sweep_record.py` | S30 Table |
| `analyses/floor_sweep_record_2026-11-08/run_floor_arms.sh` | S30 Table |
| `analyses/geneclust_2026-10-08/bias.py` | S5 and S14 Tables |
| `analyses/geneclust_2026-10-08/common.py` | shared loaders of the analyses |
| `analyses/geneclust_2026-10-08/cross.py` | S1 Fig |
| `analyses/geneclust_2026-10-08/depth_matched_intervals_2026-11-02.py` | Table 3 |
| `analyses/geneclust_2026-10-08/depth_matched_intervals_2026-11-02b.py` | Table 3 |
| `analyses/geneclust_2026-10-08/label_audit.py` | S3 Table |
| `analyses/geneclust_2026-10-08/landscape.py` | S7 and S9 Tables |
| `analyses/geneclust_2026-10-08/llm_ablation_2026-11-02.py` | imported by the scripts above |
| `analyses/geneclust_2026-10-08/llm_ablation_ncd_wpw_removed_2026-11-02.py` | Table 3 |
| `analyses/geneclust_2026-10-08/ncd_wpw_removed_2026-11-02.py` | Table 2, Table 3, S8 Table |
| `analyses/geneclust_2026-10-08/ncd_wpw_removed_claimpaper_2026-11-02.py` | S24 Table |
| `analyses/geneclust_2026-10-08/ncd_wpw_removed_relatives_2026-11-02.py` | S24 Table |
| `analyses/geneclust_2026-10-08/relabel.py` | S3 Table |
| `analyses/geneclust_2026-10-08/run_geneclust.py` | Table 3, S8 Table |
| `analyses/geneclust_2026-10-08/trivial_baselines_2026-11-02.py` | imported by the scripts above |
| `analyses/geneclust_2026-10-08/trivial_baselines_ncd_wpw_removed_2026-11-02.py` | Table 3 |
| `analyses/impc_test_2026-11-07/impc_test.py` | S1 Text, IMPC-only test |
| `analyses/llm_revalidation_2026-10-19/apply_ncd_cf.py` | S12 and S23 Tables |
| `analyses/llm_revalidation_2026-10-19/build_panel_table.py` | S12 and S23 Tables |
| `analyses/llm_revalidation_2026-10-19/claude_after_pilots.sh` | S12 and S23 Tables |
| `analyses/llm_revalidation_2026-10-19/claude_batch.py` | S12 and S23 Tables |
| `analyses/llm_revalidation_2026-10-19/errpolicy.py` | S12 and S23 Tables |
| `analyses/llm_revalidation_2026-10-19/evalA.py` | S12 and S23 Tables |
| `analyses/llm_revalidation_2026-10-19/evalA3.py` | S12 and S23 Tables |
| `analyses/llm_revalidation_2026-10-19/eval_gate2.py` | S12 and S23 Tables |
| `analyses/llm_revalidation_2026-10-19/eval_partB.py` | S12 and S23 Tables |
| `analyses/llm_revalidation_2026-10-19/eval_partC.py` | S12 and S23 Tables |
| `analyses/llm_revalidation_2026-10-19/gemini_batch.py` | S12 and S23 Tables |
| `analyses/llm_revalidation_2026-10-19/gemini_chain.sh` | S12 and S23 Tables |
| `analyses/llm_revalidation_2026-10-19/gemini_resume.sh` | S12 and S23 Tables |
| `analyses/llm_revalidation_2026-10-19/gemini_resume2.sh` | S12 and S23 Tables |
| `analyses/llm_revalidation_2026-10-19/llm_budget.py` | S12 and S23 Tables |
| `analyses/llm_revalidation_2026-10-19/make_partC_sample.py` | S12 and S23 Tables |
| `analyses/llm_revalidation_2026-10-19/openai_judge.py` | S12 and S23 Tables |
| `analyses/llm_revalidation_2026-10-19/panel_rules_vs_raters.py` | S12 and S23 Tables |
| `analyses/llm_revalidation_2026-10-19/panel_rules_vs_raters_pr.py` | S12 and S23 Tables |
| `analyses/llm_revalidation_2026-10-19/panel_vs_raters.py` | S12 and S23 Tables |
| `analyses/llm_revalidation_2026-10-19/reassign_units_independent.py` | S12 and S23 Tables |
| `analyses/llm_revalidation_2026-10-19/reclassify_mp_criterion_independent.py` | S12 and S23 Tables |
| `analyses/llm_revalidation_2026-10-19/rejudge_record_pairs.py` | S12 and S23 Tables |
| `analyses/llm_revalidation_2026-10-19/run_judgeswap.sh` | S12 and S23 Tables |
| `analyses/llm_revalidation_2026-10-19/run_panel.sh` | S12 and S23 Tables |
| `analyses/llm_revalidation_2026-10-19/smoke_test.py` | S12 and S23 Tables |
| `analyses/llm_revalidation_2026-10-19/topup_independent_judge.py` | S12 and S23 Tables |
| `analyses/mgi_additional_2026-10-09/mgi_add.py` | S2 and S14 Tables |
| `analyses/nulldepth_2026-11-07/eval_depthstrat.py` | S1 Text, depth-stratified null |
| `analyses/nullmirror_2026-10-27/eval_mirror.py` | S1 Text, mirrored null |
| `analyses/nullmirror_2026-10-27/run_nullmirror.sh` | S1 Text, mirrored null |
| `analyses/open_items_2026-10-13/item1_pubtator_extract.py` | S14 Table |
| `analyses/open_items_2026-10-13/item5c_abstract_family.py` | S4 Table |
| `analyses/overnight_audit_2026-10-09/drift_quant.py` | Methods, database drift |
| `analyses/overnight_audit_2026-10-09/extract_impc.py` | S7 Table, IMPC |
| `analyses/phenodigm_null_2026-11-07/phenodigm_null.py` | S1 Text, PhenoDigm on the same nulls |
| `analyses/power_2026-11-18/power_hanley_mcneil.py` | S32 Table |
| `analyses/rater_breakdown_2026-10-20/rater_breakdown.py` | S13 Table |
| `analyses/rater_design_check_2026-11-09/check_v9_design.py` | Methods, expert study |
| `analyses/rater_single_agreement_2026-11-13/single_rater_agreement.py` | Results, expert study |
| `analyses/retrieval_vs_llm_pairs_2026-11-08/retrieval_vs_llm.py` | S29 Table |
| `analyses/vocab_removal_2026-10-08/vocab_common.py` | imported by the scripts above |
| `expert_study/_rating_analysis_v9.py` | Figure 5, S13 Table |
| `expert_study/_rating_criterion_map.py` | Methods, expert study |
| `expert_study/_rating_pilot_build_v9.py` | Methods, expert study |
| `expert_study/_rating_pilot_render_v9.py` | Methods, expert study |
| `figures/build_fig1_flow_v43.py` | Figure 1 |
| `figures/build_fig3_units_v43.py` | Figure 2 |
| `figures/build_fig5_top10_v19.py` | Figure 4 |
| `figures/build_fig6_auroc_v22.py` | S2 Fig |
| `figures/build_fig7_raters_v37.py` | Figure 5 |
| `figures/build_fig_composition_v18d.py` | Figure 3 |
| `pipeline/0_genotypes_and_labels/build_per_tier_benchmark_tables.py` | S3 Table |
| `pipeline/0_genotypes_and_labels/construct_disorder_tiers.py` | S3 Table |
| `pipeline/0_genotypes_and_labels/setup_external_benchmark_universe_v_3.py` | Methods, genotype set |
| `pipeline/1_criterion_anchors/decompose_targets_to_criterion_units.py` | Methods, anchors |
| `pipeline/1_criterion_anchors/emit_noncriterion_hpo_exclusions.py` | Methods, anchors |
| `pipeline/1_criterion_anchors/pilot_asd_to_hpo_hybrid.py` | Methods, anchors |
| `pipeline/1_criterion_anchors/pilot_asd_to_hpo_hybrid_rev.py` | Methods, anchors |
| `pipeline/1_criterion_anchors/pilot_mdd_to_hpo_hybrid.py` | Methods, anchors |
| `pipeline/1_criterion_anchors/stage1_curate_hpo.py` | Methods, anchors |
| `pipeline/2_mouse_term_grounding/annotate_polarity_schema.py` | Methods |
| `pipeline/2_mouse_term_grounding/apply_polarity_overrides.py` | Methods |
| `pipeline/2_mouse_term_grounding/build_stage2a_taxonomy.py` | Methods, mouse criterion mapping |
| `pipeline/2_mouse_term_grounding/classify_mp_terms_criterion_grounded.py` | Methods, mouse criterion mapping |
| `pipeline/2_mouse_term_grounding/classify_mp_terms_for_asd.py` | Methods, mouse criterion mapping |
| `pipeline/2_mouse_term_grounding/criterion_prompt.py` | Methods, criteria and mapping |
| `pipeline/2_mouse_term_grounding/criterion_rules.py` | Methods, criteria and mapping |
| `pipeline/2_mouse_term_grounding/criterion_spec.py` | Methods, criteria and mapping |
| `pipeline/2_mouse_term_grounding/rebuild_behavioral_taxonomy.py` | Methods, mouse criterion mapping |
| `pipeline/2_mouse_term_grounding/rebuild_id_taxonomy.py` | S21 Table |
| `pipeline/2_mouse_term_grounding/rebuild_mdd_taxonomy.py` | S21 Table |
| `pipeline/2_mouse_term_grounding/rebuild_neurocognitive_taxonomy.py` | S21 Table |
| `pipeline/2_mouse_term_grounding/rebuild_scz_taxonomy.py` | Methods, mouse criterion mapping |
| `pipeline/2_mouse_term_grounding/rebuild_scz_taxonomy_5domain.py` | Methods, mouse criterion mapping |
| `pipeline/3_pair_judgment/build_candidate_feature_table.py` | Methods, retrieval |
| `pipeline/3_pair_judgment/build_candidate_feature_table_mdd.py` | Methods, retrieval |
| `pipeline/3_pair_judgment/bundle_independent_judge.py` | imported by the scripts above |
| `pipeline/3_pair_judgment/judge_backends.py` | imported by the scripts above |
| `pipeline/3_pair_judgment/rerank_ambiguous_pairs_api_v3.py` | Methods, pair judgment |
| `pipeline/3_pair_judgment/rerank_ambiguous_pairs_api_v3_mdd.py` | Methods, pair judgment |
| `pipeline/3_pair_judgment/rerank_independent_judge.py` | imported by the scripts above |
| `pipeline/3_pair_judgment/rerank_score_floor_fill.py` | Methods, pair judgment |
| `pipeline/3_pair_judgment/rerank_score_floor_fill_mdd.py` | Methods, pair judgment |
| `pipeline/3_pair_judgment/rerank_score_floor_fill_topup.py` | Methods, pair judgment |
| `pipeline/3_pair_judgment/rerank_score_floor_fill_topup_v3.py` | Methods, pair judgment |
| `pipeline/3_pair_judgment/stage2a_candidate_features.py` | Methods, retrieval |
| `pipeline/3_pair_judgment/stage2b_rerank.py` | Methods, pair judgment |
| `pipeline/3_pair_judgment/stage2c_score_floor_fill.py` | Methods, pair judgment |
| `pipeline/4_diagnostic_coverage/asd_face_validity_scoring.py` | Methods |
| `pipeline/4_diagnostic_coverage/mappability_catalog/facet_catalog.py` | Methods, Diagnostic Coverage |
| `pipeline/4_diagnostic_coverage/mappability_catalog/phenotype_class_hpo.py` | Methods, Diagnostic Coverage |
| `pipeline/4_diagnostic_coverage/mappability_catalog/rebuild_fv_seco_criterion.py` | Methods, Diagnostic Coverage |
| `pipeline/4_diagnostic_coverage/mappability_catalog/rebuild_fv_seco_native.py` | Methods, Diagnostic Coverage |
| `pipeline/4_diagnostic_coverage/score_breadth.py` | Methods |
| `pipeline/5_support_score/_pilot_multi_2026.py` | imported by the scripts above |
| `pipeline/5_support_score/aggregate_support_clustered.py` | Methods, support score |
| `pipeline/5_support_score/aggregate_support_clustered_broad.py` | Methods, support score |
| `pipeline/5_support_score/assess_run_stability.py` | Methods |
| `pipeline/5_support_score/benchmark/compare_methods_paired.py` | Methods, benchmarks |
| `pipeline/5_support_score/benchmark/compute_benchmark_metrics.py` | Methods, benchmarks |
| `pipeline/5_support_score/benchmark/confirmatory_logistic_models.py` | Methods, benchmarks |
| `pipeline/5_support_score/benchmark/domain_hypothesis_tests.py` | Methods, benchmarks |
| `pipeline/5_support_score/benchmark/run_benchmarks.py` | Methods, benchmarks |
| `pipeline/5_support_score/benchmark/safe_write_util.py` | Methods, benchmarks |
| `pipeline/5_support_score/benchmark/score_baseline_phenodigm_broad.py` | Methods, benchmarks |
| `pipeline/5_support_score/compute_b2_baselines.py` | S2 Table |
| `pipeline/5_support_score/permutation_null_depthstrat.py` | S1 Text, depth-stratified null |
| `pipeline/5_support_score/permutation_null_mirrored.py` | S1 Text, mirrored null |
| `pipeline/5_support_score/permutation_null_per_genotype.py` | Methods, support score |
| `pipeline/5_support_score/rarefy_and_rank_asd_models.py` | Methods |
| `pipeline/5_support_score/run_rescuepool_v2_cells.py` | S2 Table |
| `pipeline/5_support_score/stage3_aggregate.py` | Methods, support score |
| `pipeline/5_support_score/stage4_permutation_null.py` | Methods, support score |
| `pipeline/5_support_score/stage5_benchmark.py` | Methods, benchmarks |
| `pipeline/run_sheets/RUN_FRONTEND_2026-07-28.sh` | Methods |
| `pipeline/run_sheets/RUN_PRODUCTION_2026-07-28.sh` | Methods |
| `pipeline/run_sheets/RUN_STAGES345_2026-07-28.sh` | Methods |
| `pipeline/shared/harmonize/common.py` | imported by the scripts above |
| `pipeline/shared/safe_write_util.py` | imported by the scripts above |
| `supplement_tables/s11_anchors.py` | S11 Table |
| `supplement_tables/s1_rule_check.py` | S1 Table |
| `supplement_tables/s1fig_overlap.py` | S1 Fig |
| `supplement_tables/s4_holm_recompute.py` | S4 Table |
| `supplement_tables/s5_hgenes.py` | S5 Table |
| `supplement_tables/s7_composition.py` | S7 Table |
| `supplement_tables/s9_allele_design.py` | S9 Table |
