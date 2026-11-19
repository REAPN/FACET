# Pre-registration: LLM revalidation on the run of record, 2026-10-19

Written before any independent-judge or reassignment output exists. Open items 1 and 2 of OPEN_ITEMS_2026-10-19.md. Every LLM call is made by An in WSL. Corrected labels of 2026-10-08, K4 pool, gene-clustered percentile intervals, 2,000 replicates, seed 20261008. No dash-family characters.

## Part A. Judge swap on the pairs of record (closes findings-doc 8.1 and 8.4)

Question. Does FACET's discrimination depend on which vendor's LLM makes the pair judgment, on the run of record?

Design. `rejudge_record_pairs.py` re-judges exactly the record pairs (those with a production verdict in each disorder's run-of-record 03_reranked_pairs_filled.tsv: ASD 6,988, SCZ 6,882, IDD 4,398, NCD 2,607) with the production prompts (bundle origin: base plus disorder addendum; fill origin: base), production user prompt and schema, chunks of 5 per target in transparent-rank order. Only the seven verdict columns change; rerank_delta and final_pair_score are recomputed with the production deltas. The NCD construct filter of record (15 keys set strict False) is reapplied. Stages 3 and 4 then run with the run-of-record configs (regime off), as in the vocabulary-removal discrimination wing.

Judges. claude-opus-4-8 and gemini-2.5-pro, the models of the earlier suite (overridable by CLAUDE_MODEL and GEMINI_MODEL; any override is recorded in the outputs and reported).

Deviation from the earlier suite, stated in advance. The May and June suite replayed only stage 2b bundles through production code, on pre-canonical runs, and never covered NCD. A replay through the production bundle and fill code on the run of record was tested on 2026-10-19 with the record verdicts (backend cached) and dropped 27 NCD record verdicts (11 strict), because single-chunk replay cannot rebuild the record's multi-chunk bundles. That path is therefore not used. Bundle composition in the re-judgment can differ from production where production bundles held pairs later superseded; this is a limitation of the design.

Gate 1 (passed 2026-10-19, before any API call). Backend cached reproduces the record table exactly for all four disorders: every verdict column, rerank_delta and final_pair_score identical (strict pairs ASD 145, SCZ 196, IDD 138, NCD 95).
Gate 2. The cached arm through stages 3 and 4 reproduces the headline discrimination AUROCs of record (ASD 0.9557, SCZ 0.6823, IDD 0.7511, NCD 0.6638) to 4 decimals. If it fails, no judge result is read.

Primary outcome. Paired difference in discrimination AUROC (support score, headline universe, corrected labels), each judge minus record, with its gene-clustered 90 percent interval. Equivalent if the interval lies inside plus or minus 0.05. Reported per disorder and judge (8 comparisons), no pooling.
Secondary (reported, not decisive). Full-pool AUROC differences; strict pair counts; pair-level agreement with the record on strict_eligible and on behavioral_analog_type (percent and Cohen kappa), overall and per disorder; chunks failing after retries or pairs without a new verdict (must be 0, else reported and the pair keeps no verdict).
Not covered. The face-validity wing (diagnostic coverage, convergent AUROC) is rebuilt from the match export, not by stages 3 and 4, and is out of scope tonight. MDD (8 positives) is out of scope.

## Part B. Anchor reassignment (closes findings-doc 3.1, informs 3.4)

Question. Do independent LLMs attribute the human anchors to the same DSM-5-TR units as production?

Design. `reassign_units_independent.py` uses the production developer prompt rendered from criterion_specs/{D}.json, the production user prompt and schema, on the current stage 1 targets (ASD 46, SCZ 41, IDD 25, NCD 28). Prompt hashes of the current specs match production for ASD, IDD and NCD. SCZ differs (current 899afb317c9a, production cae0c0c7af4b): the production SCZ attribution predates the SCZ criteria rebuild of 2026-08-01. This is recorded as a finding of the check. An may add a gpt-5.4 rerun of SCZ on the current prompt with the production script as a third arm.
Outcomes. Per disorder: agreement on item_id with production (anchors in both), agreement on attributable, Cohen kappa, unanimity of the three. ASD's 4 current anchors without a production attribution and SCZ's prompt drift are reported separately.
Decision rule. Every anchor where at least one independent judge disagrees with production on a scored unit, or on attributable, goes to the first author's review list with all three reasons. the first author decides per anchor. If any decision changes a scored-unit assignment, the downstream scores are rerun as a sensitivity arm beside the record, not in place of it.

## Part C. Mouse-side criterion classification (added 2026-10-20 01:20Z, before any output of this part exists)

Question. Do independent LLMs reproduce the stage 2a criterion classification of record (which MP terms are admissible for which unit)? This is the fourth LLM step, never independently checked on the criterion-grounded taxonomy (the 2026-07 checks of findings-doc 8.3 and 8.6 used the retired broad_v3 taxonomy).
Design. `reclassify_mp_criterion_independent.py` runs the classifier of record (prompt v4, joint mode, production schema, user prompt and direction rule) on the record scope tables: ASD 1,655, SCZ 1,657, IDD 2,393, NCD 1,710 terms. Prompt hashes match the record for ASD, IDD and NCD. SCZ differs (current 15f7206ccffc, record fd777227494a): the SCZ taxonomy of record predates a later SCZ spec edit, recorded as a finding.
Outcomes. Per disorder and judge: agreement with the record on admissible_directionaware (percent, Cohen kappa), on item_id among terms admissible in either, the admissible counts, and the list of terms admitted by the record but by neither judge, and by both judges but not the record.
Decision rule. Disagreements go to the first author's review list. Downstream rescoring with an independent taxonomy is not run tonight; if the first author's review changes admissions it becomes a sensitivity arm.


## Erratum 2026-10-20 01:40Z (appended; the text above is unchanged)
Parts B and C state that the SCZ attribution of record (cae0c0c7) and the SCZ taxonomy of record (fd777227) predate a SCZ spec edit. That cause is wrong. Both hashes were reproduced exactly on 2026-10-20 by rendering the production prompt builders with DSM5_SCZ_preprocessed/01_diagnostic_criteria.txt.bak_pre_untruncate_2026-08-01 (md5 3e9ec016...) in place of the current file. The only difference between the record prompts and the current prompts is two stray spaces in the criterion A stem ("1 -month" and "(1 )"), repeated in each A unit block; the prompts are identical under whitespace-insensitive comparison. The 2026-08-01 rebuild (SCZ_CRITERIA_FILE_REBUILD_2026-08-01.md) repaired a truncation after criterion F that does not enter these prompts. Consequence: the SCZ arms of parts B and C compare judges on the same criteria content, so any SCZ disagreement is judge disagreement, not prompt drift. No design change.
