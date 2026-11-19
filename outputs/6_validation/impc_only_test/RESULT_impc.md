# IMPC-only test of the support score (corrected labels, headline universe, K4)

Universe: IMPC-tagged genotypes of the headline universe with curated models removed. Positives: genotypes whose gene is an H gene (S5 Table). Intervals: 95% gene-clustered bootstrap, 2,000 replicates. Depth matched: background reweighted to the positives' behavioral-depth bins (0, 1 to 2, 3 to 5, 6 to 10, 11 or more), gene-clustered, 500 replicates.

| Disorder | IMPC genotypes | H-gene positives (genes) | Background | Support AUROC (95%) | Coverage AUROC (95%) | Behavioral count AUROC (95%) | PhenoDigm recomputed AUROC (95%) | Support minus PhenoDigm (95%, p) | Support AUROC depth matched (95%) | Behavioral count depth matched |
|---|---|---|---|---|---|---|---|---|---|---|
| ASD | 2460 | 36 (33) | 2424 | 0.491 (0.428 to 0.562) | 0.593 (0.494 to 0.696) | 0.577 (0.481 to 0.672) | 0.499 (0.406 to 0.593) | -0.008 (-0.081 to +0.065, p 0.822) | 0.489 (0.430 to 0.555) | 0.568 |
| SCZ | 2543 | 8 (7) | 2535 | 0.514 (0.442 to 0.712) | 0.513 (0.326 to 0.740) | 0.517 (0.342 to 0.741) | 0.483 (0.321 to 0.667) | +0.031 (-0.147 to +0.207, p 0.678) | 0.517 (0.436 to 0.695) | 0.499 |
| IDD | 2588 | 213 (190) | 2375 | 0.521 (0.497 to 0.546) | 0.524 (0.492 to 0.556) | 0.565 (0.521 to 0.610) | 0.502 (0.456 to 0.546) | +0.019 (-0.027 to +0.070, p 0.412) | 0.517 (0.495 to 0.540) | 0.516 |
| NCD | 2438 | 45 (44) | 2393 | 0.484 (0.470 to 0.509) | 0.513 (0.440 to 0.591) | 0.475 (0.394 to 0.563) | 0.477 (0.398 to 0.558) | +0.007 (-0.074 to +0.087, p 0.871) | 0.486 (0.469 to 0.513) | 0.497 |

Behaviorally annotated share, positives against background: ASD 0.889 against 0.862, SCZ 0.875 against 0.836, IDD 0.84 against 0.818, NCD 0.822 against 0.858

Positive depth bins (0, 1 to 2, 3 to 5, 6 to 10, 11 or more): ASD [4, 23, 8, 1, 0], SCZ [1, 5, 2, 0, 0], IDD [34, 111, 54, 14, 0], NCD [8, 27, 8, 2, 0]