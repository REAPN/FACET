# Part B results: independent anchor reassignment vs production

Label compared = item_id when attributable is True, else none. Second unit reported separately.

| Disorder | Judge | Anchors prod / judge / both | Primary-label agreement | Kappa | Attributable agreement | Second-unit agreement |
|---|---|---|---|---|---|---|
| ASD | claude | 43 / 46 / 42 | 42/42 (100.0%) | 1.000 | 42/42 | 42/42 |
|  | claude: anchors without production attribution | HP:5200061, HP:0034434, HP:4000090, HP:5200123 | | | | |
| ASD | gemini | 43 / 46 / 42 | 40/42 (95.2%) | 0.944 | 41/42 | 41/42 |
|  | gemini: anchors without production attribution | HP:5200061, HP:0034434, HP:4000090, HP:5200123 | | | | |
| SCZ | claude | 41 / 41 / 41 | 31/41 (75.6%) | 0.565 | 32/41 | 39/41 |
| SCZ | gemini | 41 / 41 / 41 | 30/41 (73.2%) | 0.614 | 32/41 | 36/41 |
| ID | claude | 25 / 25 / 25 | 24/25 (96.0%) | 0.937 | 24/25 | 25/25 |
| ID | gemini | 25 / 25 / 25 | 24/25 (96.0%) | 0.934 | 24/25 | 25/25 |
| NCD | claude | 28 / 28 / 28 | 27/28 (96.4%) | 0.927 | 27/28 | 28/28 |
| NCD | gemini | 28 / 28 / 28 | 28/28 (100.0%) | 1.000 | 28/28 | 28/28 |

Unanimity of all three (production + both judges): ASD 40/42, SCZ 26/41, ID 23/25, NCD 27/28

Review list: 22 anchors (20 with a scored-unit or attributable disagreement, 2 second-unit only). File PARTB_REVIEW_LIST.tsv.

| Disorder | HPO | Label | Production | claude | gemini |
|---|---|---|---|---|---|
| ASD | HP:0033055 | Impaired ability to plan | none (2nd none) |  | B2 (2nd none) |
| ASD | HP:5200310 | Diminishment of social interactions | A1 (2nd A3) |  | A3 (2nd A1) |
| SCZ | HP:0002463 | Language impairment | none (2nd none) | A3 (2nd none) | A3 (2nd none) |
| SCZ | HP:0000745 | Abnormal diminished volition | A5 (2nd B) | A5 (2nd none) | A5 (2nd none) |
| SCZ | HP:0000718 | Aggressive behavior | A4 (2nd none) | none (2nd none) |  |
| SCZ | HP:0002311 | Incoordination | A4 (2nd none) | none (2nd none) |  |
| SCZ | HP:5200310 | Diminishment of social interactions | B (2nd A5) | A5 (2nd B) | A5 (2nd B) |
| SCZ | HP:5200401 | Abnormal judgment | none (2nd none) | A1 (2nd none) | A1 (2nd none) |
| SCZ | HP:0025766 | Abnormal affect | A5 (2nd none) | none (2nd none) | A4 (2nd none) |
| SCZ | HP:5200045 | Reduced impulse control | A4 (2nd none) | none (2nd none) |  |
| SCZ | HP:0000708 | Atypical behavior | A4 (2nd none) | none (2nd none) |  |
| SCZ | HP:5200216 | Abnormal perceptual state | none (2nd none) | A2 (2nd none) | A2 (2nd none) |
| SCZ | HP:5200424 | Delusional perception | none (2nd none) | A1 (2nd none) | A1 (2nd none) |
| SCZ | HP:0000748 | Inappropriate laughter | none (2nd none) |  | A4 (2nd none) |
| SCZ | HP:0001262 | Excessive daytime somnolence | none (2nd none) |  | A4 (2nd none) |
| SCZ | HP:0004396 | Poor appetite | none (2nd none) |  | A5 (2nd B) |
| SCZ | HP:0012523 | Oral aversion | none (2nd none) |  | A4 (2nd A5) |
| SCZ | HP:5200046 | Sensory behavioral abnormality | none (2nd none) |  | A2 (2nd none) |
| SCZ | HP:5200024 | Abnormal relationship | B (2nd A5) |  | B (2nd none) |
| ID | HP:0010526 | Dysgraphia | A (2nd none) | none (2nd none) |  |
| ID | HP:0000745 | Abnormal diminished volition | none (2nd none) |  | B (2nd none) |
| NCD | HP:0010992 | Stress urinary incontinence | B (2nd none) | none (2nd none) |  |
