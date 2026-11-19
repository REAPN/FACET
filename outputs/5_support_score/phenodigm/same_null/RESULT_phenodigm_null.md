# PhenoDigm referred to the permutation null (corrected labels 2026-11-02, headline universe, K4)

PhenoDigm recomputed (arm 3, full profile) is referred to the same null construction as the support score: random MP sets of the genotype's own size, 10,000 draws, p one plus the count at or above the observed over draws plus one, minus log10 p capped at 4. Intervals: 95% gene-clustered bootstrap, 2,000 replicates.

| Disorder | null | n (curated) | FACET support AUROC | PhenoDigm raw | PhenoDigm referred to the null | FACET minus PhenoDigm raw (95%, p) | FACET minus PhenoDigm referred (95%, p) | Referred minus raw (95%, p) |
|---|---|---|---|---|---|---|---|---|
| ASD | sizematched | 11961 (85) | 0.956 (0.920 to 0.983) | 0.772 (0.707 to 0.831) | 0.792 (0.730 to 0.848) | +0.184 (+0.126 to +0.248, p 0.000) | +0.163 (+0.112 to +0.222, p 0.000) | +0.020 (+0.010 to +0.033, p 0.001) |
| ASD | stratified | 11961 (85) | 0.956 (0.920 to 0.983) | 0.772 (0.707 to 0.831) | 0.657 (0.574 to 0.734) | +0.184 (+0.126 to +0.248, p 0.000) | +0.298 (+0.220 to +0.383, p 0.000) | -0.115 (-0.148 to -0.086, p 0.000) |
| IDD | sizematched | 12382 (111) | 0.751 (0.705 to 0.820) | 0.706 (0.623 to 0.757) | 0.714 (0.626 to 0.767) | +0.045 (-0.028 to +0.158, p 0.277) | +0.037 (-0.040 to +0.157, p 0.381) | +0.008 (-0.006 to +0.019, p 0.227) |
| IDD | stratified | 12382 (111) | 0.751 (0.705 to 0.820) | 0.706 (0.623 to 0.757) | 0.624 (0.532 to 0.680) | +0.045 (-0.028 to +0.158, p 0.277) | +0.127 (+0.042 to +0.256, p 0.002) | -0.082 (-0.115 to -0.057, p 0.000) |
| NCD | sizematched | 11603 (67) | 0.668 (0.595 to 0.737) | 0.593 (0.543 to 0.637) | 0.594 (0.540 to 0.638) | +0.075 (+0.007 to +0.150, p 0.031) | +0.074 (+0.007 to +0.147, p 0.028) | +0.001 (-0.022 to +0.018, p 0.900) |
| NCD | stratified | 11603 (67) | 0.668 (0.595 to 0.737) | 0.593 (0.543 to 0.637) | 0.541 (0.488 to 0.586) | +0.075 (+0.007 to +0.150, p 0.031) | +0.127 (+0.057 to +0.202, p 0.000) | -0.052 (-0.079 to -0.030, p 0.000) |
| SCZ | sizematched | 12486 (42) | 0.682 (0.603 to 0.761) | 0.772 (0.703 to 0.840) | 0.781 (0.717 to 0.844) | -0.090 (-0.191 to +0.001, p 0.054) | -0.099 (-0.198 to -0.013, p 0.033) | +0.009 (-0.004 to +0.024, p 0.201) |
| SCZ | stratified | 12486 (42) | 0.682 (0.603 to 0.761) | 0.772 (0.703 to 0.840) | 0.680 (0.596 to 0.763) | -0.090 (-0.191 to +0.001, p 0.054) | +0.002 (-0.118 to +0.108, p 0.977) | -0.092 (-0.128 to -0.053, p 0.000) |