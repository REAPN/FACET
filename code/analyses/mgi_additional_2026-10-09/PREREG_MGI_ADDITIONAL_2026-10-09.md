# Pre-registration: analyses of the additional MGI reports, 2026-10-09

Written 2026-10-09T05:52Z. Before writing it, only file headers and row formats were inspected (column layout, the coarse organ-system grain of recombinase "detected in", the high-level MP terms carrying normal flags in the sex report and the row count of the negated-disease file). No outcome was computed. Inputs are in `MGI additional/` (downloaded on 2026-10-09). Definitions follow `METHODS_DEFINITIONS_2026-10-08.md`. K4 pool, corrected labels of 2026-10-08, behaviorally annotated means at least one MP:0004924 descendant. Gene-clustered percentile intervals (1,000 replicates, seed 20261008) unless stated, Wald intervals for odds ratios. No dash-family characters. No LLM call.

## P1. Explicit negatives (`MGI_Geno_NotDiseaseDO.rpt`, NOT column of `MGI_DiseaseMouseModel.rpt`)

- A genotype is an explicit negative for disorder D when either file records it as NOT a model of a DO term that is one of D's config DOIDs or a Disease Ontology descendant of D's root (the M mapping of section 4). `MGI_DiseaseMouseModel.rpt` rows are matched to pool genotypes by allele pair and background.
- Report counts per disorder in the K4 pool, and every genotype that is both a corrected positive and an explicit negative for the same disorder (a label conflict).
- If a disorder has at least 10 explicit negatives in the pool, report curated positives against explicit negatives on support (discrimination AUROC, full pool) and on diagnostic coverage (convergent AUROC). Below 10, report counts only.

## P2. Recorded normal behavioral results (`MGI_Pheno_Sex.rpt`)

- A genotype has a recorded normal behavioral result when any row carries Sex-specific Normal = Y on MP:0005386 behavior/neurological phenotype, MP:0004924 or any MP:0004924 descendant.
- Report counts in the K4 pool, split by behaviorally annotated or not and by curated status per disorder. The quantity of interest is the share of lines without behavioral annotation that nonetheless have a recorded normal behavioral result: a lower bound on how often "not behaviorally annotated" hides an assay with a normal outcome (warning 1).

## P3. Study attention (`MRK_Reference.rpt`, `MGI_IMSRKomp.rpt`)

- Gene attention: distinct PubMed IDs per marker. Genotype attention: the maximum over the genes in its cluster key, entered as log(1 + count). Secondary: IMSR strain count per gene, same construction. Genotypes with no mapped gene are excluded from P3 models.
- P3a. F24 analogue: logistic model of being behaviorally annotated on gene prior, with and without log attention, uncurated lines, per disorder.
- P3b. F12 and F26 analogues: odds ratio for gene prior (H list) and for SFARI for the top coverage tier, adjusted for annotation volume and behavioral-annotation count (as reported), then also for log attention. All retained tier thresholds (ASD 3, 4 and 5, MDD 2 and 3, others 2).
- P3c. Curated status on log attention among behaviorally annotated lines, adjusted for log behavioral-annotation count, per disorder.
- P3d. F34 analogue: curated against H lines and H lines without a curated gene against other uncurated, support and coverage, both classes behaviorally annotated. Negatives reweighted over count stratum (4 bins) by attention tertile (3 bins, cut points fixed once over behaviorally annotated pool lines with a mapped gene). Reported beside the count-only values.

## P4. Where the recombinase acts (`MGI_Recombinase_Full.rpt`)

- Driver alleles are identified as in `landscape.py`. Each is classed by its "detected in" organ systems: nervous-system restricted (detected only in nervous system, head or sensory organs), nervous system plus other systems, assayed with nervous system not detected, and no assay data. A genotype takes the class of its driver (multiple drivers: the broadest class).
- Report the class mix of conditional lines in the pool and in the uncurated ASD ceiling set (5 or 6 criteria).
- F17 analogue: within-gene comparison of conditional lines against germline nulls of the same gene (mean ASD criteria, Wilcoxon signed rank over genes), both classes behaviorally annotated, separately for each driver class with at least 20 genes. Same for IDD, SCZ, NCD and MDD as secondary.

## Rules

- Every number states pool, label version, restriction and classes, score, AUROC family and interval type, and tier threshold where used.
- An effect of adjustment is called material when the adjusted odds ratio's interval excludes the unadjusted point estimate, or when the gene-clustered interval of a paired AUROC difference excludes 0.
- Results go to FINDINGS_LOG as new F numbers. No value of record changes.
