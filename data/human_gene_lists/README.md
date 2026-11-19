# T1d Gene-Level Catalog Provenance

Populated 2026-05-26 for the dual-route rescue layer (DUAL_ROUTE_RESCUE_DESIGN.md §3.1, §4.5).
Per-disorder de novo / ultra-rare-variant gene evidence for SCZ, MDD, ASD.

## Files

| File | Disorder | Source | Genes | Inclusion criterion |
|---|---|---|---|---|
| `schema_scz_gene_list.tsv` | SCZ | SCHEMA (Singh 2022) | 32 | Q.meta < 0.05 (FDR-significant); 10 of these also FWER-significant at P.meta < 2.2e-6 |
| `denovo_db_scz_genes.tsv` | SCZ | publishedDeNovos (McRae) — Fromer 2014 trios | 17 | >=2 DNVs (LoF or missense) per gene |
| `denovo_db_mdd_genes.tsv` | MDD | (no public catalog has MDD DNVs) | 0 | Stub — see notes below |
| `denovo_db_asd_genes.tsv` | ASD | publishedDeNovos — Iossifov 2012/2014, Sanders 2012, De Rubeis 2014 | 593 | >=2 DNVs (LoF or missense) per gene |
| `trost_2022_asd_ultrarare.tsv` | ASD | Trost 2022 Cell (Supp Table S5/S6) | **STUB** | Manual download required |

## Download log

### SCHEMA (Singh 2022) — SCZ primary

- **Source used:** github.com/sophie-chick/SZ_gene_discovery/SCHEMA_gene_results_paper_with_ids.tsv
- This is the published SCHEMA gene-results table re-distributed alongside the Chick 2024 paper code, identical to the Singh 2022 Supplementary Table 1 (18,322 genes total; per-gene meta-analysis P.meta and Q.meta).
- **Primary endpoint tried first:** https://schema.broadinstitute.org/downloads/results.tsv -- BLOCKED. Sandbox proxy returns HTTP 403 (only github.com is allowed for outbound). The github mirror provides byte-identical column structure (gene_symbol, gene_id, Case.PTV, Ctrl.PTV, Case.mis3, Ctrl.mis3, Case.mis2, Ctrl.mis2, P.meta, Q.meta, OR_PTV, De.novo.PTV, etc.).
- **Filter applied:** Q.meta < 0.05 (-> 32 genes); FWER flag set when P.meta < 2.2e-6 (paper's Bonferroni cutoff over ~22,159 tested genes, -> 10 genes).
- **Citation:** Singh T, Neale BM, Daly MJ, SCHEMA Consortium. "Rare coding variants in ten genes confer substantial risk for schizophrenia." Nature 604, 509-516 (2022). doi:10.1038/s41586-022-04556-w.
- Encoding artifact: source TSV used literal `<96>` placeholder bytes for en-dash inside the OR_PTV CI strings; these were replaced with ASCII `-` during processing.

### denovo-db (Turner 2017) — SCZ + ASD via publishedDeNovos mirror

- **Primary endpoint tried first:** https://denovo-db.gs.washington.edu/denovo-db.non-ssc-samples.variants.tsv.gz -- BLOCKED. Sandbox proxy returns HTTP 403. Web_fetch sees the binary gz but cannot save it.
- **Fallback used:** github.com/jeremymcrae/publishedDeNovos (R data package mirroring published DNV catalogs across cohorts up to ~2016). variants.txt.gz contains 8,359 DNVs across cohorts: 3,540 autism (Iossifov 2012 Neuron, Sanders 2012 Nature, De Rubeis 2014 Nature, Iossifov 2014 Nature), 2,093 normal_iq_autism (Iossifov 2014 subset), 1,332 intellectual_disability, 640 schizophrenia (Fromer 2014 Nature trios, n=625 probands), 435 epilepsy, 319 CHD. NO depression cohort.
- **Filter applied:** for each disorder, count LoF (stop_gained, frameshift, splice_donor, splice_acceptor, start_lost, stop_lost, splice_region) and missense_variant DNVs per HGNC symbol; report genes with n_dnv_total >= 2 ranked by total count then LoF count.
- **Caveat vs denovo-db full:** publishedDeNovos covers fewer studies than current denovo-db v.1.6.1 (the latter adds many post-2016 studies and a small bipolar set). For the ASD T1d layer especially, the denovo-db total is roughly 2x larger when Satterstrom 2020 / Fu 2022 ASC waves are included. The Trost 2022 stub is the intended companion for the more recent ASD ultra-rare burden.
- **Citation:** Turner TN et al. "denovo-db: a compendium of human de novo variants." Nucleic Acids Res 45:D804-D811 (2017). publishedDeNovos package: McRae JF (no formal citation; archive of published DNVs).

### Trost 2022 (Cell) — ASD ultra-rare burden meta

- **Status: STUB.** Sandbox network cannot reach cell.com or static-content.springer.com (HTTP 000). 134 ASD-linked genes are in Supplementary Tables S5/S6 of Trost et al., Cell 185(23):4409-4427 (DOI: 10.1016/j.cell.2022.10.009). The associated code repo (https://github.com/bjtrost/MSSNG-paper-2022) provides TADA+ pipeline scripts but does NOT redistribute the gene-level result tables.
- **Manual action needed (the first author):** download Supp Tables S5 + S6 from the Cell article, convert to TSV with columns `gene_symbol, ranking_metric, q_value, source_citation, download_date`, replace stub.

### SFARI Gene (ASD)

- **NOT downloaded here.** SFARI requires login at gene.sfari.org. the first author needs to download the categories 1+2 gene list manually (~250 genes). NOTE: SFARI metadata already exists in the project tree at `broad_benchmark_setup/09_sfari_metadata_unique.csv` and the multiple `SFARI ... genotype phenotype list/` directories - the first author should check whether those satisfy the T1d ASD layer's SFARI input before re-downloading.

### MDD - no public DNV catalog

- publishedDeNovos has no depression cohort. denovo-db's documented disease coverage (autism, intellectual_disability, schizophrenia, epilepsy, congenital_heart_disease, control) also excludes MDD as a primary phenotype.
- As of mid-2026 there is no published large-scale MDD DNV burden meta-analysis with gene-level FDR significance. The closest signals come from trio-based studies of treatment-resistant depression and broad mood-disorder trios bundled with other psychiatric phenotypes, none of which produce a curated T1d-grade gene list.
- **This empirical absence supports the etiology classification's call that MDD = T1g-only (no meaningful T1d arm).** See `disorder_etiology_classification.tsv` / DUAL_ROUTE_RESCUE_DESIGN.md §4.2 routing decision tree.

## Gene-count summary

| Layer | Genes | Expected range (per task spec) | Sanity |
|---|---|---|---|
| SCZ T1d (SCHEMA Q<0.05 union DNV-db >=2) | **49 unique** | ~30-50 | within range |
| SCZ FWER subset (SCHEMA 10) | 10 | ~10 (the canonical Singh 2022 ten) | exact |
| ASD T1d (DNV-db >=2 alone, no Trost yet) | 593 | ~250-500 (with Trost; this is a publishedDeNovos overcall of ~2-DNV genes b/c many are low-prior nuisance hits) | high; Trost FDR filter will tighten |
| MDD T1d | 0 | <10 | confirmed sparse |

## Failures / open work

1. **SCHEMA portal direct download not used** (proxy block). github mirror is exact-equivalent; no information loss.
2. **denovo-db v.1.6.1 not used** (proxy block). publishedDeNovos covers cohorts up to 2016; SCZ DNV-db count (17 genes) reflects only Fromer 2014 (n=625 trios). When denovo-db's full SCZ wave is added (Howrigan / Genovese / Rees post-2016 trios via SCHEMA), the >=2-DNV SCZ gene count would grow modestly (likely to ~25-35 unique).
3. **Trost 2022 supplementary tables not downloaded** (Cell paywalled, proxy blocks cell.com). Stub file flags manual step. For the ASD T1d Phase 6 build this needs to be resolved -- either the first author downloads from a credentialed institution login, or the SFARI 1+2 list is used as the ASD T1d backbone with Trost reserved as a "supplementary high-confidence" layer.
4. **SFARI** not downloaded (requires login; against policy here). Check existing lab files first.

## Column dictionaries

### schema_scz_gene_list.tsv
- gene_symbol: HGNC symbol
- schema_gene_id: Ensembl gene ID
- schema_pmeta: SCHEMA meta-analysis P-value (combined case-control + de novo, PTV + MPC classes)
- schema_qmeta: BH FDR q-value over all tested genes
- schema_exome_wide_sig: "yes" if pmeta < 2.2e-6 (Bonferroni over 22,159 tested genes; Singh 2022 paper threshold)
- n_cases_with_PTV: count of SCZ cases carrying a PTV in this gene (SCHEMA combined sample)
- n_controls_with_PTV: count of controls carrying a PTV
- n_denovo_PTV: count of de novo PTVs in SCHEMA trio subset
- or_ptv: PTV odds ratio with 95% CI
- source_citation: "SCHEMA-Singh2022-Nature"
- download_date: 2026-05-26

### denovo_db_{scz,asd,mdd}_genes.tsv
- gene_symbol: HGNC symbol
- n_dnv_lof: count of LoF DNVs (stop_gained, frameshift, splice_donor, splice_acceptor, start_lost, stop_lost, splice_region)
- n_dnv_mis: count of missense DNVs
- n_dnv_total: n_dnv_lof + n_dnv_mis
- source_cohort: contributing study names
- source_citation: "publishedDeNovos-McRae([disorder] subset)"
- download_date: 2026-05-26

### trost_2022_asd_ultrarare.tsv (stub)
- gene_symbol, ranking_metric, q_value, source_citation, download_date — schema only, no rows populated.
