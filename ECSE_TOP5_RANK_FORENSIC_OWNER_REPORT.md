# ECSE Top5 Rank Forensic — Owner Report

**Phase:** ECSE-TOP5-RANK-FORENSIC-1
**Eligible fixtures:** 16
**Recommendation:** `ECSE_WEAK_RANK_BIAS_ONLY`

| Rank | Hits | Hit Rate | 95% CI | Share of Top5 Hits | Stability |
|---|---:|---:|---|---:|---|
| 1 | 2 | 12.5% | [0.0, 0.3125] | 18.2% | 0.14 |
| 2 | 4 | 25.0% | [0.0625, 0.5] | 36.4% | 0.56 |
| 3 | 2 | 12.5% | [0.0, 0.3125] | 18.2% | 0.09 |
| 4 | 3 | 18.8% | [0.0, 0.375] | 27.3% | 0.21 |
| 5 | 0 | 0.0% | [0.0, 0.0] | 0.0% | 0.0 |

| Metric | Baseline | Best Rerank | Delta |
|---|---:|---:|---:|
| Top1 exact accuracy | 0.0% | 0.0% | +0.0% |
| Hit@3 | 50.0% | 50.0% | +0.0% |
| Hit@5 | 66.7% | 66.7% | +0.0% |
| Mean reciprocal rank | 0.264 | 0.264 | +0.000 |

| Segment | Best Historical Rank | Hit Rate | Sample Size | Stable? |
|---|---:|---:|---:|---|
| segment_stage:knockout | 2 | 25.0% | 16 | False |
| segment_favorite:strong_favorite | 1 | 25.0% | 8 | True |
| segment_scoring:high_scoring | 1 | 33.3% | 6 | True |
| segment_scoring:low_scoring | 2 | 30.0% | 10 | False |
