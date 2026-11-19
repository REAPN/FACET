# What the LLM adds at the level of pairs (2026-11-08)

140 rated pairs of the four powered disorders with a definite rating (0 without a retrieval score skipped). Rater verdict = majority of composite ratings, ties half. The LLM of record admits 71; each retrieval rule admits the same number. Pair bootstrap, 4000 replicates.

| Rule | admits | agreement with raters | kappa | confirmation of admitted | rejection of refused | recall of rater-admitted |
|---|---|---|---|---|---|---|
| LLM admission of record | 71 | 0.793 | 0.635 | 0.662 | 0.906 | 0.879 |
| retrieval alone (transparent score), top k pooled | 71 | 0.729 | 0.474 | 0.592 | 0.833 | 0.785 |
| embedding alone, top k pooled | 71 | 0.743 | 0.507 | 0.606 | 0.848 | 0.804 |
| retrieval alone, top k within each disorder | 71 | 0.721 | 0.446 | 0.577 | 0.819 | 0.766 |
| embedding alone, top k within each disorder | 71 | 0.746 | 0.521 | 0.613 | 0.855 | 0.813 |

Agreement difference, LLM minus retrieval rule (95% pair-bootstrap interval):

- retrieval alone (transparent score), top k pooled: +0.064 (-0.004 to +0.136)
- embedding alone, top k pooled: +0.050 (-0.018 to +0.121)
- retrieval alone, top k within each disorder: +0.071 (+0.000 to +0.139)
- embedding alone, top k within each disorder: +0.046 (-0.021 to +0.114)

Threshold-free AUROC against the rater majority (123 pairs, ties dropped):

- LLM admission (binary): 0.835
- retrieval transparent score: 0.803
- embedding cosine: 0.811
- final pair score (retrieval plus LLM adjustment): 0.860
- retrieval transparent score within LLM-admitted pairs: 0.559; within LLM-refused pairs: 0.656

Sampling caveat: the instrument was drawn by stratum from the record's verdicts. Retrieval score separates the record's admitted from refused rated pairs at AUROC 0.859 (median transparent score 0.585 admitted against 0.344 refused), so the instrument is not neutral between the two rules.
