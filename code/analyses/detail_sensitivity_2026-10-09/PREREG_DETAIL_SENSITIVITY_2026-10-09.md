# Pre-registration: annotation-detail sensitivity, 2026-10-09

Written 2026-10-09T04:58Z, before any detail metric or outcome was computed. Requested by An on 2026-10-09 ("run a sensitivity that gives weight to detailed annotation, this may further reveal biases"). Definitions follow `METHODS_DEFINITIONS_2026-10-08.md`. No dash-family characters. No LLM call.

## Question

1. Does the detail of a line's behavioral annotation follow researcher focus (curated status, gene prior, annotation source)?
2. Does rewarding lines with more detailed behavioral annotation change discrimination, and do the curated-against-gene-line contrasts of F34 survive matching on detail as well as on count?

## Population and labels

K4 pool (32,535 genotypes). Corrected labels of 2026-10-08. Every contrast restricts both classes to behaviorally annotated lines (at least one annotation equal to or descending from MP:0004924) unless a line says otherwise.

## Detail metrics (per genotype, over its distinct annotations equal to or below MP:0004924)

- D1, primary. Mean propagated information content, `ic_prop` in the canonical `mappability_catalog/mp_term_specificity.tsv` (IC(t) = -log2 of the share of 76,060 MGI genotypes annotated to t or a descendant, per `SPECIFIC_GENERIC_MP_RULE.md`). Cutoff-free and separate from the annotation count.
- D2, secondary. Number of behavioral annotations with `ic_prop` of 11.0 bits or more ("specific" under the frozen cut). The cut was calibrated on the SCZ catatonia partition only and its generalization is unproven. Disclosed wherever used.
- D3, secondary. Maximum `ic_prop` over the genotype's behavioral annotations.
- D4, secondary. Mean is_a depth below MP:0004924 (shortest path length, MP:0004924 itself at 0). This is ontology depth, a second reading of "detailed".

Detail tertiles: cut points of D1 computed once over all behaviorally annotated K4 genotypes. One set for every disorder.

## Analyses

A. Who gets detailed annotation.
- D1 to D4 summarized for curated models, uncurated lines carrying an H gene (human-genetics list, as in 6c) and other uncurated lines, per disorder.
- D1 by annotation source (IMPC allele with no literature row, IMPC allele with literature, literature only), as defined in `landscape.py`.
- Curated against other uncurated on D1: AUROC with gene-clustered percentile interval (1,000 replicates, seed 20261008).
- Logistic model among behaviorally annotated K4 lines, per disorder: curated status on log(1 + behavioral-annotation count) and standardized D1. Wald intervals. A D1 odds ratio above 1 means curated status favors detailed annotation beyond its count.

B. Detail-weighted discrimination (the reward). Full pool, support score, discrimination AUROC, both classes behaviorally annotated. Each genotype is weighted by D1 divided by the mean D1 of the restricted set. The weighted AUROC uses product weights over positive and negative pairs. Report the unweighted value, the weighted value and the paired difference with a gene-clustered percentile interval (1,000 replicates). Repeat for diagnostic coverage (convergent AUROC). MDD has no support score and gets coverage only.

C. Restriction to detailed lines. As B, but both classes restricted to lines with D2 of 1 or more instead of weighting.

D. Matched on count and detail. The F34 contrasts (curated against H lines, curated against other uncurated, H lines without a curated gene against other uncurated), on support and coverage. Negatives are reweighted to the positives' joint distribution over 12 cells: the 4 count strata of METHODS_DEFINITIONS section 6 (1 to 2, 3 to 5, 6 to 10, 11 or more) crossed with the 3 detail tertiles. Report beside the count-only F34 values.

## Reporting and interpretation rules

- Every number states pool, label version, restriction and classes, score, AUROC family and interval type.
- A change is called material only when the gene-clustered interval of the paired difference excludes 0. Otherwise it is reported as no material change, with the interval.
- If curated models carry more detail than uncurated lines after their count is accounted for, that is an annotation (researcher focus) bias in the label. Literature labs that hypothesize a disorder run targeted assays and are annotated to specific terms, while broad screens annotate to fewer, more general terms.
- If weighting raises an AUROC, the separation concentrates in detailed lines. If it lowers it, the separation rests partly on coarse annotation.
- Known mechanical link, stated in advance: IC comes from MGI-wide annotation frequency, and a fixed screening battery annotates the same terms on many lines, which lowers their IC. A source difference in D1 therefore partly reflects how terms are used, which is the bias this analysis is meant to expose. It is not by itself a statement about the biology of those lines.
- Results go to FINDINGS_LOG with an F number. Nothing here changes a value of record.
