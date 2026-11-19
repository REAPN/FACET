# FACET: criterion-anchored measurement of mouse model face validity for psychiatric disorders

FACET (Face-validity Assessment by Criterion-Anchored-LLM Extraction and Translation) measures which DSM-5-TR diagnostic criteria the recorded phenotypes of a mouse genotype model. Authored by An Le under Chunyu Liu's mentorship at SUNY Upstate.  

This repository provides the code, the input data and the recorded outputs behind the manuscript. It covers five disorders (autism spectrum disorder, schizophrenia, intellectual developmental disorder, major neurocognitive disorder and major depressive disorder) and the 32,535 annotated genotypes of Mouse Genome Informatics (MGI).

The pipeline has three steps. Anchoring resolves each criterion to Human Phenotype Ontology (HPO) anchors and grounds each Mammalian Phenotype (MP) term to the criteria it could model. Judgment retrieves candidate pairs of anchor and MP term by embedding and lexical similarity and submits them to an LLM (gpt-5.4), which admits or refuses each pair without access to genes, genotypes or disease labels. Aggregation credits each genotype with the criteria its annotated phenotypes model, which yields two measures: Diagnostic Coverage and a permutation-based support score.

## Layout

| Path | Content |
|---|---|
| `data/` | the labels of record, the genotype tables derived from MGI, the human gene lists and the third-party snapshots the run read. See `data/README.md` |
| `code/pipeline/` | the scripts of each step, with the disorder configurations and the run sheets of record |
| `code/analyses/` | one folder per validation or sensitivity analysis |
| `code/expert_study/` | the build of the rating instrument and the agreement analysis |
| `code/figures/`, `code/supplement_tables/` | the figure builders and the scripts behind the supplementary tables |
| `outputs/` | the recorded output of every step and every reported analysis result. See `outputs/README.md` |
| `tools/make_worktree.py` | restores the folder layout in which the scripts run |
| `MANIFEST.tsv` | one row per file: repository path, the path the scripts read it from, size, SHA-256, role, the table or figure reporting it and a note |

The folders of `code/pipeline/` and `outputs/` carry the same numbers, so the scripts of a step and the output they wrote are found under one name.

| Step | Folder | Content |
|---|---|---|
| Inputs | `0_genotypes_and_labels` | the genotype set and the curated-model labels |
| Anchoring | `1_criterion_anchors` | criterion text sectioning, HPO anchors and their attribution to criterion units |
| Anchoring | `2_mouse_term_grounding` | grounding of the 11,485 annotated MP terms to criteria |
| Judgment | `3_pair_judgment` | retrieval of candidate pairs and the LLM judgment |
| Aggregation | `4_diagnostic_coverage` | the per-genotype catalogue of credited criteria |
| Aggregation | `5_support_score` | the support score, its permutation null and the benchmarks against the curated labels |

## Requirements

Python 3.10 with numpy, pandas and scipy runs the aggregation and the analyses. Single analyses also import statsmodels, scikit-learn and matplotlib. The anchoring and judgment steps import openai, rapidfuzz, pypdf and pydantic, and the tests with alternate LLMs import the Anthropic and Google clients.

## Preparing the working tree

The scripts import one another and read their inputs by paths relative to one project root. The repository arranges the files by step for reading, and `tools/make_worktree.py` places each file at the path the scripts expect (the `original_path` column of `MANIFEST.tsv`). Every command below runs from that working tree.

```
python3 tools/make_worktree.py work
cd work
export FACET_ROOT=$PWD
```

The tree takes about 0.9 GB. Files stored gzipped are unpacked.

## Reproducing the reported results

The reported values recompute from the recorded outputs with no LLM call and no API key. Each analysis script reads the recorded outputs and writes the result behind one table or figure. Three examples:

```
python3 audit/composition_2026-11-06/composition.py                          # Figure 3, S16 Table
python3 audit/geneclust_2026-10-08/depth_matched_intervals_2026-11-02.py     # Table 3
python3 audit/power_2026-11-18/power_hanley_mcneil.py                        # S32 Table
```

`code/README.md` lists every script with the table or figure it reports, the folder to run it from and the inputs that are not deposited.

## Running the pipeline

Each disorder has one configuration file (`asd.disorder.json`, `scz.disorder.json`, `intellectualdisability.disorder.json`, `neurocognitive.disorder.json`, `mdd.disorder.json`), which names the inputs, the parameters and the output folder of every step. The three run sheets hold the sequence of record with its checks, and each takes a disorder code (`ASD`, `SCZ`, `ID` or `NCD`) or `gates`, which checks the inputs without running any step.

### Aggregation from the recorded judgments

Aggregation needs no LLM call, because the recorded pair judgments are deposited.

```
bash RUN_STAGES345_2026-07-28.sh gates      # confirms that the recorded judgments of each disorder are in place
bash RUN_STAGES345_2026-07-28.sh ASD        # support score, permutation null and benchmarks for one disorder
bash RUN_STAGES345_2026-07-28.sh gfv        # the per-genotype catalogue behind Diagnostic Coverage
```

The run sheet calls three scripts per disorder:

```
python3 stage3_aggregate.py --config asd.disorder.json --regime off            # support per genotype from the admitted pairs
python3 stage4_permutation_null.py --config asd.disorder.json --regime off     # permutation null and p-value per genotype
python3 stage5_benchmark.py --config asd.disorder.json --regime off --mode strict   # support AUROC against the curated labels
```

The benchmark step also scores the PhenoDigm comparator, which reads the Monarch similarity table. That table is not redistributed (see `data/README.md`) and has to be placed at the project root first. The catalogue of record was written by `mappability_catalog/rebuild_fv_seco_criterion.py` with the settings its file names carry:

```
cd mappability_catalog
python3 rebuild_fv_seco_criterion.py --breadth_requires_strict --max_prevalence 0.25 --umbrella_span 1 --pool k4 --floor_asd_a2
```

### Anchoring and judgment

These steps call the LLM and read the diagnostic criteria. They need an OpenAI key in the environment (`OPENAI_API_KEY`) and a licensed copy of the DSM-5-TR, since the manual's text is not redistributed. The tests with alternate LLMs read `ANTHROPIC_API_KEY` and `GOOGLE_API_KEY`.

```
python3 extract_dsm5.py --config asd.disorder.json --pdf <DSM-5-TR PDF>     # sections the criterion text of one disorder
bash RUN_FRONTEND_2026-07-28.sh gates                                       # checks code, criterion text and MP term grounding
bash RUN_FRONTEND_2026-07-28.sh ASD                                         # anchoring and judgment for one disorder
```

The run sheet calls the following scripts in order and skips a step whose output exists:

| Step | Script | LLM |
|---|---|---|
| Grounding of MP terms to criteria | `classify_mp_terms_criterion_grounded.py`, then `build_stage2a_taxonomy.py` | yes |
| Resolution of criteria to HPO anchors | `stage1_curate_hpo.py` | yes |
| Attribution of anchors to criterion units | `decompose_targets_to_criterion_units.py` | yes |
| Retrieval of candidate pairs | `stage2a_candidate_features.py` | embeddings only |
| Judgment of ambiguous pairs | `stage2b_rerank.py` | yes |
| Judgment of the remaining pairs above the score floor | `stage2c_score_floor_fill.py` | yes |

The configuration files and criterion specifications carry the marker `<DSM-5-TR text redacted>` where they held criterion wording, which the user restores from the licensed copy. A new run reproduces the procedure. Its verdicts can differ from the recorded ones, because the LLM is not deterministic (S1 Text reports the reproducibility of the verdicts).

## What is not deposited

- DSM-5-TR text (copyright American Psychiatric Association). The free-text reasons the LLM logged are also removed from the recorded outputs, because they can quote the manual.
- Expert rating returns. `outputs/6_validation/expert_study/` holds aggregate agreement only.
- Third-party files that are large or restricted: the Monarch similarity tables, the PubTator3 files, the IMPC statistical results, and the SFARI Gene export. `data/README.md` gives their versions and S2 Table gives their checksums.
- The run folders of the alternate LLM tests. Their per-genotype support p-values are deposited, which is what the evaluations read.

## Citation and license

The reference of the preprint and the license will be added on release. Third-party inputs keep their own licenses: MGI and the Mammalian Phenotype Ontology (CC BY 4.0), the Disease Ontology (CC0) and the Human Phenotype Ontology (its own license, redistributed unmodified).
