# Mirrored permutation null: consolidated result (corrected labels, strict, K4)

Observed support scores are the record's in both columns. The null of record combines every candidate-passing pair per anchor by noisy-OR. The mirrored null first clusters near-duplicate pairs exactly as the Stage 3 aggregator does (same mp_id, same ancestor, token Jaccard of term text at or above 0.65), keeps the top pair per cluster and then combines. The random term sets are identical, so every difference below comes from the score function alone.

## ASD
| universe | n (positives) | discrimination AUROC, null of record | discrimination AUROC, mirrored null | difference (90 percent interval) |
|---|---|---|---|---|
| headline | 11961 (85) | 0.9557 | 0.9557 | +0.0000 (+0.0000 to +0.0000) |
| full pool | 32535 (85) | 0.9689 | 0.9689 | +0.0000 (+0.0000 to +0.0000) |
Genotypes whose p value changed: 10 of 18439 (up 10, down 0, largest change in neg log10 p 0.0038). Ceiling ties: 389 under the null of record, 389 under the mirrored null. Null mean shift over depths: mean -2e-06, range -7e-06 to 0.0, 60 of 92 depths differ. Observed scores identical: True.

## SCZ
| universe | n (positives) | discrimination AUROC, null of record | discrimination AUROC, mirrored null | difference (90 percent interval) |
|---|---|---|---|---|
| headline | 12486 (42) | 0.6823 | 0.6823 | -0.0000 (-0.0000 to +0.0000) |
| full pool | 32535 (42) | 0.7094 | 0.7094 | -0.0000 (-0.0000 to +0.0000) |
Genotypes whose p value changed: 2 of 19432 (up 2, down 0, largest change in neg log10 p 0.0047). Ceiling ties: 57 under the null of record, 57 under the mirrored null. Null mean shift over depths: mean -1e-06, range -1.4e-05 to 0.0, 29 of 92 depths differ. Observed scores identical: True.

## IDD
| universe | n (positives) | discrimination AUROC, null of record | discrimination AUROC, mirrored null | difference (90 percent interval) |
|---|---|---|---|---|
| headline | 12382 (111) | 0.7511 | 0.7511 | -0.0000 (-0.0000 to +0.0000) |
| full pool | 32535 (121) | 0.7591 | 0.7591 | -0.0000 (-0.0000 to +0.0000) |
Genotypes whose p value changed: 11 of 18716 (up 11, down 0, largest change in neg log10 p 0.0134). Ceiling ties: 478 under the null of record, 478 under the mirrored null. Null mean shift over depths: mean -5e-06, range -2.4e-05 to 0.0, 61 of 92 depths differ. Observed scores identical: True.

## NCD
| universe | n (positives) | discrimination AUROC, null of record | discrimination AUROC, mirrored null | difference (90 percent interval) |
|---|---|---|---|---|
| headline | 11603 (68) | 0.6638 | 0.6638 | +0.0000 (+0.0000 to +0.0000) |
| full pool | 32535 (73) | 0.7237 | 0.7237 | +0.0000 (+0.0000 to +0.0000) |
Genotypes whose p value changed: 15 of 17472 (up 15, down 0, largest change in neg log10 p 0.0036). Ceiling ties: 17 under the null of record, 17 under the mirrored null. Null mean shift over depths: mean -4e-06, range -1.9e-05 to 0.0, 55 of 92 depths differ. Observed scores identical: True.
