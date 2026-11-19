# Judgment-floor sweep on the run of record (2026-11-08)

Raising the floor removes the pairs judged by the floor route (non-injected pairs outside a bundle) below it. Injected descendants and bundle pairs are judged whatever their score. A catalogue match (criterion, admitted MP term) is affected only if every admitted pair behind it is removed.

| Disorder | admitted pairs of record (strict, direct or close) | of them judged by the floor route | lost at 0.60 | lost at 0.65 | catalogue matches losing all pairs at 0.60 | at 0.65 | unjudged pairs in [0.50, 0.57) | in [0.55, 0.57) |
|---|---|---|---|---|---|---|---|---|
| ASD | 145 | 44 | 6 | 20 | 2 | 8 | 333 | 80 |
| SCZ | 196 | 47 | 6 | 26 | 0 | 6 | 257 | 57 |
| IDD | 138 | 50 | 7 | 17 | 0 | 1 | 165 | 51 |
| NCD | 95 | 20 | 14 | 17 | 4 | 6 | 234 | 40 |

Mapping check: catalogue matches of record with no admitted pair found in the rerank folder (descendant or injected terms resolved elsewhere): ASD 0, SCZ 0, IDD 0, NCD 0.

Lowering the floor to 0.55 or 0.50 adds the unjudged pairs counted in the last two columns, which need new LLM judgments under the prompt of record.
