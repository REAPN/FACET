# Expert agreement, computed from the sealed key (v9)

Build v9_k3_168pairs_n12_judged, 168 pairs each rated by 3 raters, 12 codes, 3 anchors. Positive prevalence 3.0 percent in the population of 14205 rateable pairs.

## 1. Human against the model, the two conditional rates

Estimated over distinct pairs. Every pair is rated by three raters and contributes the share of them who agreed with the pipeline (mean rate) and whether more than half did (majority rate). The sized half-width is root p q over distinct pairs, the conservative basis the study was sized on. The empirical half-width is the standard error of the pair means, the design-based figure now that a pair's value averages three ratings. The rater half-width adds the between-rater spread (tau, the standard deviation of rater leniency after binomial noise is removed) divided by the rater count. The lower bound is one-sided 95 percent on the rater-adjusted empirical standard error and is the one the decision rule reads.

| comparison | class | distinct pairs | ratings | mean rate | majority rate | Wilson 95 percent | sized half-width | empirical half-width | rater half-width | tau | one-sided lower bound |
|---|---|---|---|---|---|---|---|---|---|---|---|
| composite against the strict-gate analog decision | confirmation, pipeline accepted | 77 | 138 | 0.662 | 0.662 | 0.551 to 0.758 | 0.106 | 0.092 | 0.173 | 0.211 | 0.517 |
| composite against the strict-gate analog decision | rejection, pipeline refuted | 75 | 130 | 0.884 | 0.880 | 0.793 to 0.939 | 0.072 | 0.067 | 0.072 | 0.037 | 0.824 |
| Q1 against the criterion-match tier | confirmation, pipeline accepted | 74 | 132 | 0.788 | 0.784 | 0.682 to 0.866 | 0.093 | 0.087 | 0.092 | 0.044 | 0.711 |
| Q1 against the criterion-match tier | rejection, pipeline refuted | 78 | 136 | 0.733 | 0.737 | 0.625 to 0.818 | 0.098 | 0.090 | 0.090 | 0.000 | 0.657 |

Widest sized half-width on the primary comparison 0.106 against the design target 0.10: not met. Widest rater-adjusted empirical half-width 0.173.

Declared rule (both point rates at or above 0.85 and both one-sided lower bounds at or above 0.70 for expert-supported; either point rate below 0.70 for not expert-confirmed; measured otherwise): **not expert-confirmed**. Confirmation 0.662 (lower bound 0.517), rejection 0.884 (lower bound 0.824).

## 2. Chance-corrected agreement

Kappa is reported on each rater's own set, built 21 accepted and 21 refuted, because kappa is sensitive to how rare a class is. AC1 is reported the same way and again with the two classes weighted back to the population, 420 accepted and 13785 refuted.

**composite against the strict-gate analog decision**

| rater | items rated | kappa | AC1 |
|---|---|---|---|
| pooled, pair-weighted | 152 | 0.545 | 0.548 |

Caution: on this comparison the core splits 77 and 75, not evenly, so the kappa above is not on a balanced margin and the 0.4 and 0.6 reading does not apply to it. The core is built evenly on the strict-gate class only.

Mean kappa across raters 0.527, range 0.143 to 0.762.

Population-weighted AC1 0.886, population-weighted kappa 0.253, weights carry each disorder and class back to its population count, descriptive only.

**Q1 against the criterion-match tier**

| rater | items rated | kappa | AC1 |
|---|---|---|---|
| pooled, pair-weighted | 152 | 0.520 | 0.520 |

Caution: on this comparison the core splits 74 and 78, not evenly, so the kappa above is not on a balanced margin and the 0.4 and 0.6 reading does not apply to it. The core is built evenly on the strict-gate class only.

Mean kappa across raters 0.525, range 0.286 to 0.809.

Population-weighted AC1 0.667, population-weighted kappa 0.113, weights carry each disorder and class back to its population count, descriptive only.

## 3. Expert against expert

Mean agreement between two experts on the same pair, over every dyad of every pair rated by at least two raters: 0.792 on 107 pairs (125 dyads), pair bootstrap 95 percent 0.713 to 0.866. On an even class mixture this corresponds to kappa 0.584. This is the ceiling any automated judge can be held to; no line attached.


Mean dyad kappa 0.534 over 13 rater dyads sharing at least one block of 14 pairs; each dyad is small, so read the pair-level figure above.

## 4. Descriptive breakdowns

| disorder | distinct pairs | mean agreement |
|---|---|---|
| ASD | 44 | 83.0 percent |
| ID | 33 | 77.3 percent |
| MDD | 12 | 65.3 percent |
| NCD | 31 | 75.8 percent |
| SCZ | 32 | 75.0 percent |

| stratum, S1 is the accepted class | distinct pairs | mean agreement |
|---|---|---|
| S1 | 77 | 66.2 percent |
| S2 | 13 | 53.8 percent |
| S3 | 8 | 79.2 percent |
| S4 | 54 | 98.1 percent |

## 5. Q2 analog grade

Quadratic weighted kappa 0.601 on 263 ratings where both scales apply. Ratings, not distinct pairs, and secondary.

---

# Sensitivity, 68 cannot-tell answers counted as refusals

## 1. Human against the model, the two conditional rates, cannot-tell as refusal

Estimated over distinct pairs. Every pair is rated by three raters and contributes the share of them who agreed with the pipeline (mean rate) and whether more than half did (majority rate). The sized half-width is root p q over distinct pairs, the conservative basis the study was sized on. The empirical half-width is the standard error of the pair means, the design-based figure now that a pair's value averages three ratings. The rater half-width adds the between-rater spread (tau, the standard deviation of rater leniency after binomial noise is removed) divided by the rater count. The lower bound is one-sided 95 percent on the rater-adjusted empirical standard error and is the one the decision rule reads.

| comparison | class | distinct pairs | ratings | mean rate | majority rate | Wilson 95 percent | sized half-width | empirical half-width | rater half-width | tau | one-sided lower bound |
|---|---|---|---|---|---|---|---|---|---|---|---|
| composite against the strict-gate analog decision | confirmation, pipeline accepted | 84 | 168 | 0.528 | 0.536 | 0.422 to 0.631 | 0.107 | 0.085 | 0.198 | 0.258 | 0.362 |
| composite against the strict-gate analog decision | rejection, pipeline refuted | 84 | 168 | 0.923 | 0.923 | 0.845 to 0.963 | 0.057 | 0.046 | 0.047 | 0.016 | 0.883 |
| Q1 against the criterion-match tier | confirmation, pipeline accepted | 80 | 162 | 0.635 | 0.644 | 0.526 to 0.732 | 0.105 | 0.089 | 0.177 | 0.221 | 0.487 |
| Q1 against the criterion-match tier | rejection, pipeline refuted | 88 | 174 | 0.803 | 0.807 | 0.708 to 0.873 | 0.083 | 0.070 | 0.074 | 0.034 | 0.741 |

Widest sized half-width on the primary comparison 0.107 against the design target 0.10: not met. Widest rater-adjusted empirical half-width 0.198.

Declared rule (both point rates at or above 0.85 and both one-sided lower bounds at or above 0.70 for expert-supported; either point rate below 0.70 for not expert-confirmed; measured otherwise): **not expert-confirmed**. Confirmation 0.528 (lower bound 0.362), rejection 0.923 (lower bound 0.883).

## 2. Chance-corrected agreement, cannot-tell as refusal

Kappa is reported on each rater's own set, built 21 accepted and 21 refuted, because kappa is sensitive to how rare a class is. AC1 is reported the same way and again with the two classes weighted back to the population, 420 accepted and 13785 refuted.

**composite against the strict-gate analog decision**

| rater | items rated | kappa | AC1 |
|---|---|---|---|
| pooled, pair-weighted | 168 | 0.450 | 0.471 |

Mean kappa across raters 0.458, range 0.143 to 0.762.

Population-weighted AC1 0.916, population-weighted kappa 0.270, weights carry each disorder and class back to its population count, descriptive only.

**Q1 against the criterion-match tier**

| rater | items rated | kappa | AC1 |
|---|---|---|---|
| pooled, pair-weighted | 168 | 0.441 | 0.454 |

Caution: on this comparison the core splits 80 and 88, not evenly, so the kappa above is not on a balanced margin and the 0.4 and 0.6 reading does not apply to it. The core is built evenly on the strict-gate class only.

Mean kappa across raters 0.458, range 0.190 to 0.809.

Population-weighted AC1 0.761, population-weighted kappa 0.123, weights carry each disorder and class back to its population count, descriptive only.

## 3. Expert against expert, cannot-tell as refusal

Mean agreement between two experts on the same pair, over every dyad of every pair rated by at least two raters: 0.719 on 140 pairs (196 dyads), pair bootstrap 95 percent 0.650 to 0.791. On an even class mixture this corresponds to kappa 0.439. This is the ceiling any automated judge can be held to; no line attached.


Mean dyad kappa 0.377 over 14 rater dyads sharing at least one block of 14 pairs; each dyad is small, so read the pair-level figure above.

## 4. Descriptive breakdowns, cannot-tell as refusal

| disorder | distinct pairs | mean agreement |
|---|---|---|
| ASD | 48 | 78.8 percent |
| ID | 36 | 75.0 percent |
| MDD | 16 | 64.6 percent |
| NCD | 32 | 70.3 percent |
| SCZ | 36 | 67.1 percent |

| stratum, S1 is the accepted class | distinct pairs | mean agreement |
|---|---|---|
| S1 | 84 | 52.8 percent |
| S2 | 14 | 72.6 percent |
| S3 | 9 | 81.5 percent |
| S4 | 61 | 98.4 percent |

## 5. Q2 analog grade, cannot-tell as refusal

Quadratic weighted kappa 0.481 on 286 ratings where both scales apply. Ratings, not distinct pairs, and secondary.

---

# Sensitivity, the first author's block (code A) removed

## 1. Human against the model, the two conditional rates, the first author's block removed

Estimated over distinct pairs. Every pair is rated by three raters and contributes the share of them who agreed with the pipeline (mean rate) and whether more than half did (majority rate). The sized half-width is root p q over distinct pairs, the conservative basis the study was sized on. The empirical half-width is the standard error of the pair means, the design-based figure now that a pair's value averages three ratings. The rater half-width adds the between-rater spread (tau, the standard deviation of rater leniency after binomial noise is removed) divided by the rater count. The lower bound is one-sided 95 percent on the rater-adjusted empirical standard error and is the one the decision rule reads.

| comparison | class | distinct pairs | ratings | mean rate | majority rate | Wilson 95 percent | sized half-width | empirical half-width | rater half-width | tau | one-sided lower bound |
|---|---|---|---|---|---|---|---|---|---|---|---|
| composite against the strict-gate analog decision | confirmation, pipeline accepted | 77 | 118 | 0.654 | 0.649 | 0.542 to 0.750 | 0.106 | 0.095 | 0.193 | 0.226 | 0.492 |
| composite against the strict-gate analog decision | rejection, pipeline refuted | 75 | 111 | 0.880 | 0.880 | 0.787 to 0.936 | 0.074 | 0.072 | 0.078 | 0.041 | 0.815 |
| Q1 against the criterion-match tier | confirmation, pipeline accepted | 74 | 112 | 0.777 | 0.777 | 0.670 to 0.857 | 0.095 | 0.091 | 0.091 | 0.000 | 0.701 |
| Q1 against the criterion-match tier | rejection, pipeline refuted | 78 | 117 | 0.756 | 0.756 | 0.651 to 0.838 | 0.095 | 0.092 | 0.092 | 0.000 | 0.679 |

Widest sized half-width on the primary comparison 0.106 against the design target 0.10: not met. Widest rater-adjusted empirical half-width 0.193.

Declared rule (both point rates at or above 0.85 and both one-sided lower bounds at or above 0.70 for expert-supported; either point rate below 0.70 for not expert-confirmed; measured otherwise): **not expert-confirmed**. Confirmation 0.654 (lower bound 0.492), rejection 0.880 (lower bound 0.815).

## 2. Chance-corrected agreement, the first author's block removed

Kappa is reported on each rater's own set, built 21 accepted and 21 refuted, because kappa is sensitive to how rare a class is. AC1 is reported the same way and again with the two classes weighted back to the population, 420 accepted and 13785 refuted.

**composite against the strict-gate analog decision**

| rater | items rated | kappa | AC1 |
|---|---|---|---|
| pooled, pair-weighted | 152 | 0.532 | 0.536 |

Caution: on this comparison the core splits 77 and 75, not evenly, so the kappa above is not on a balanced margin and the 0.4 and 0.6 reading does not apply to it. The core is built evenly on the strict-gate class only.

Mean kappa across raters 0.503, range 0.143 to 0.762.

Population-weighted AC1 0.884, population-weighted kappa 0.248, weights carry each disorder and class back to its population count, descriptive only.

**Q1 against the criterion-match tier**

| rater | items rated | kappa | AC1 |
|---|---|---|---|
| pooled, pair-weighted | 152 | 0.533 | 0.533 |

Caution: on this comparison the core splits 74 and 78, not evenly, so the kappa above is not on a balanced margin and the 0.4 and 0.6 reading does not apply to it. The core is built evenly on the strict-gate class only.

Mean kappa across raters 0.516, range 0.286 to 0.809.

Population-weighted AC1 0.699, population-weighted kappa 0.124, weights carry each disorder and class back to its population count, descriptive only.

## 3. Expert against expert, the first author's block removed

Mean agreement between two experts on the same pair, over every dyad of every pair rated by at least two raters: 0.772 on 75 pairs (79 dyads), pair bootstrap 95 percent 0.675 to 0.861. On an even class mixture this corresponds to kappa 0.544. This is the ceiling any automated judge can be held to; no line attached.


Mean dyad kappa 0.502 over 9 rater dyads sharing at least one block of 14 pairs; each dyad is small, so read the pair-level figure above.

## 4. Descriptive breakdowns, the first author's block removed

| disorder | distinct pairs | mean agreement |
|---|---|---|
| ASD | 44 | 81.4 percent |
| ID | 33 | 77.3 percent |
| MDD | 12 | 62.5 percent |
| NCD | 31 | 75.8 percent |
| SCZ | 32 | 75.0 percent |

| stratum, S1 is the accepted class | distinct pairs | mean agreement |
|---|---|---|
| S1 | 77 | 65.4 percent |
| S2 | 13 | 53.8 percent |
| S3 | 8 | 75.0 percent |
| S4 | 54 | 98.1 percent |

## 5. Q2 analog grade, the first author's block removed

Quadratic weighted kappa 0.573 on 225 ratings where both scales apply. Ratings, not distinct pairs, and secondary.

---

## The declared decision rule

Expert-supported when both point rates are at or above 0.85 and both one-sided 95 percent lower bounds are at or above 0.70; measured when either rate falls between 0.70 and 0.85; not expert-confirmed when either falls below 0.70. The lower bound reads the pair-level standard error with the between-rater component added. AC1 carries no line and is descriptive.
