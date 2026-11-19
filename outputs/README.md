# Outputs

The recorded output of each pipeline step and every analysis result reported in the manuscript and its supplement. `../MANIFEST.tsv` gives the table or figure reporting each file and the path at which a script reads or writes it.

| Folder | Content | Reported in |
|---|---|---|
| `1_criterion_anchors/` | per disorder, the resolved HPO anchors and their attribution to criterion units | Table 1, S11 Table |
| `2_mouse_term_grounding/` | per disorder, the grounding of the 11,485 annotated MP terms to criteria, the anchor sets and their rerun | S21 and S22 Tables |
| `3_pair_judgment/` | per disorder, every judged pair of anchor and MP term with its retrieval channels, transparent score and verdict fields | Methods, S20 Table |
| `4_diagnostic_coverage/` | the per-genotype catalogue of credited criterion units, the unit landscape, coverage AUROC, composition, allele design and cross-disorder overlap | Table 2, Figures 2 to 4, S7, S9, S16 and S28 Tables, S1 Fig |
| `5_support_score/` | per-genotype support scores, support AUROC with intervals, baselines and depth matching, PhenoDigm, the null models and the per-genotype p-values of every test | Table 3, S8 and S10 Tables, S1 Text |
| `6_validation/` | alternate LLMs, the expert study (aggregate), claim-paper removal and relatives, the IMPC-only test, human genetics and attention, annotation detail, database drift, the judgment floor, the channel weights, multiplicity and power | S4, S5, S12 to S14, S23, S24 and S29 to S32 Tables |
| `figures/` | the figures as published | Figures 1 to 5, S1 and S2 Figs |

## Reading the files

- The outputs of anchoring and judgment (`1_` to `3_` and `4_diagnostic_coverage/catalogue`) are the LLM outputs of record. The columns `reason`, `rationale` and `source_fragment` are removed, and no downstream step reads them.
- Files stored gzipped are unpacked by `tools/make_worktree.py`.
- Ten result files predate the labels of record (2026-11-02) and carry no NCD entries. The manifest note marks them, and the NCD values of record are in the files dated 2026-11-02 or later.
- `6_validation/expert_study/` holds aggregate agreement over eight raters. Rows for single raters and for pairs of raters are removed. `instrument/` holds the blinded items, the assignment of items to rater codes and the sampling frame.
- `5_support_score/per_genotype_by_test/` holds the per-genotype p-values of the record replay, the alternate LLMs, the raised judgment floors, the changed channel weights, claim-paper removal and the two alternative null models.
