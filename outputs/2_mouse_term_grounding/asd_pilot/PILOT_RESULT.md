# Stage 2a pilot: criterion-grounded taxonomy versus the current design

Expectations were declared before the run in `build_pilot_term_set.py`. Both designs are scored on the same terms.

## Headline

| quantity | old design | new design | reading |
|---|---|---|---|
| RECOVERY, blocked terms now admitted | 0 of 14 (0%) | 14 of 14 (100%) | higher is the point of the redesign |
| RETENTION, admitted terms still admitted | 15 of 15 (100%) | 15 of 15 (100%) | a drop means the new prompt is too strict |
| SPECIFICITY, must-block terms refused | 16 of 16 (100%) | 16 of 16 (100%) | a drop means the new prompt is too loose |

**VERDICT: ACCEPT.** Pre-declared acceptance rule: recovery at or above 60 percent, retention at or above 85 percent, specificity at or above 85 percent. Recovery alone is not sufficient.


## EXPECT_ADMIT, should now be admitted

| term | old | new | item | expected item | flags | verdict |
|---|---|---|---|---|---|---|
| abnormal chemical nociception | block | admit | B4 | B4 | qualifier absent | ok |
| abnormal grooming behavior | block | admit | B2 +B1 | B2 | qualifier absent, review | ok |
| abnormal habituation to a novel object | block | admit | B4 | B4 | qualifier absent | ok |
| abnormal habituation to a novel odor | block | admit | B4 | B4 | qualifier absent | ok |
| abnormal mechanical nociception | block | admit | B4 | B4 | qualifier absent | ok |
| abnormal nest building behavior | block | admit | B2 +B1 | B2 | qualifier absent, review | ok |
| abnormal olfactory behavior | block | admit | B4 | B4 | qualifier absent | ok |
| abnormal pain threshold | block | admit | B4 | B4 | qualifier absent | ok |
| abnormal response to novel object | block | admit | B4 +B3 | B4 | qualifier absent | ok |
| abnormal thermal nociception | block | admit | B4 | B4 | qualifier absent | ok |
| abnormal thermosensation | block | admit | B4 | B4 | qualifier absent | ok |
| decreased grooming behavior | block | admit | B2 +B1 | B2 | qualifier absent, review | ok |
| decreased thermal nociceptive threshold | block | admit | B4 | B4 | qualifier absent | ok |
| increased thermal nociceptive threshold | block | admit | B4 | B4 | qualifier absent | ok |

## EXPECT_KEEP, must stay admitted

| term | old | new | item | expected item | flags | verdict |
|---|---|---|---|---|---|---|
| abnormal behavioral response to light | admit | admit | B4 | B4 | . | ok |
| abnormal response to novel odor | admit | admit | B4 | B4 | qualifier absent | ok |
| abnormal response to tactile stimuli | admit | admit | B4 | B4 | qualifier absent | ok |
| abnormal social investigation | admit | admit | A1 +A3 | A1 | . | ok |
| abnormal social play behavior | admit | admit | A3 +A1 | A3 | . | ok |
| abnormal vocalization | admit | admit | A2 +A1 | A2 | qualifier absent, review | ok |
| cognitive inflexibility | admit | admit | B2 | B2 | qualifier absent | ok |
| decreased social novelty preference | admit | admit | A3 +A1 | A3 | . | ok |
| decreased vocalization | admit | admit | A2 +A1 | A2 | qualifier absent, review | ok |
| hyporesponsive to tactile stimuli | admit | admit | B4 | B4 | qualifier absent | ok |
| impaired social recognition | admit | admit | A3 +A1 | A3 | . | ok |
| increased grooming behavior | admit | admit | B2 +B1 | B2 | qualifier absent | ok |
| increased stereotypic behavior | admit | admit | B1 +B2 | B1 | . | ok |
| social withdrawal | admit | admit | A1 +A3 | A3 | . | ok |
| stereotypic behavior | admit | admit | B1 +B2 | B1 | . | ok |

## EXPECT_BLOCK, must stay refused

| term | old | new | item | expected item | flags | verdict |
|---|---|---|---|---|---|---|
| abnormal adipose tissue morphology | block | block | none | none | . | ok |
| abnormal behavior | block | block | none | none | . | ok |
| abnormal brain wave pattern | block | block | none | none | . | ok |
| abnormal mounting behavior | block | block | none | none | . | ok |
| abnormal nociceptor morphology | block | block | none | none | . | ok |
| abnormal object recognition memory | block | block | none | none | . | ok |
| abnormal pup retrieval | block | block | none | none | . | ok |
| abnormal short-term object recognition memory | block | block | none | none | . | ok |
| abnormal synaptic transmission | block | block | none | none | . | ok |
| abnormal vision | block | block | none | none | . | ok |
| anosmia | block | block | none | none | . | ok |
| ataxia | block | block | none | none | . | ok |
| deafness | block | block | none | none | . | ok |
| impaired long-term object recognition memory | block | block | none | none | . | ok |
| impaired spatial learning | block | block | none | none | . | ok |
| increased aggression | block | block | none | none | . | ok |

## DSM item assignment

Of 29 admitted terms carrying a pre-declared expected item, 29 were assigned that item as primary or secondary (100% if any).

