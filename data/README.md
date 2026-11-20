# Data

The inputs of the primary analysis run. `../MANIFEST.tsv` gives the path each script reads a file from, and S2 Table of the supplement gives the version, size and SHA-256 of every third-party file.

| Path | Content |
|---|---|
| `labels_corrected_2026-11-02.tsv` | the primary labels: the curated models of each disorder among the 32,535 genotypes |
| `relabel.json`, `label_audit.json` | the label rules applied to the MGI disease reports and their audit (S3 Table) |
| `01_all_genotype_summary.csv` | one row per genotype of the genotype set, derived from the MGI reports |
| `08_all_genotype_phenotypes_long_blinded.csv.gz` | the MP annotations of every genotype under blinded identifiers, read by the aggregation step |
| `99_run_config.json` | the configuration of the genotype set build |
| `ONTOLOGY_VERSIONS.md` | the ontology releases the run read |
| `paraphrased_criteria/` | per disorder, the diagnostic criteria in the project's paraphrase (`*_criteria.txt`), from which the criterion specifications take the text of each unit, and the stage 1 core text, the criteria with the supporting passages in paraphrase (`*_core_text.txt`) |
| `mgi_add.json` | counts from the additional MGI reports (S2 and S14 Tables) |
| `human_gene_lists/` | the gene lists implicated by human genetics (S5 Table) |
| `third_party_inputs/` | the snapshots the run read: MGI reports, the MP ontology, the Disease Ontology, HPO and its disease annotations |

MGI overwrites its reports weekly and keeps no archive, so the snapshots are deposited. Files with a date in their name are the later releases read by the drift analyses only.

## Third-party files not redistributed

| File | Version | Read by |
|---|---|---|
| Monarch `phenio-monarch-hp-mp.0.4.semsimian.tsv` and its IC companion | version 0.4 | the PhenoDigm comparator and two retrieval channels |
| PubTator3 gene, disease and species files | accessed 2026-10 | literature attention (S14 Table) |
| IMPC `statistical-results-ALL.csv.gz` | downloaded 2026-10 | the IMPC-only test (S1 Text) |
| SFARI Gene animal models export | 2026-03-22 | metadata of the genotype set build |

Each file is available from its provider and is expected at the path S2 Table lists.
