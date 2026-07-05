# ECSE-TOP5-RANK-FORENSIC-1 — Report

**Recommendation:** `ECSE_WEAK_RANK_BIAS_ONLY`
**Dataset size:** 16 finished fixtures with frozen pre-kickoff ECSE Top5

## Task A — Rank hit analysis

- Rank1 hit rate: **12.5%** (2/16)
- Rank2 hit rate: **25.0%** (4/16)
- Rank3 hit rate: **12.5%** (2/16)
- Rank4 hit rate: **18.8%** (3/16)
- Rank5 hit rate: **0.0%** (0/16)
- Top5 miss rate: **31.2%**

## Task B — Cumulative Hit@K

- hit@1: 12.5%
- hit@2: 37.5%
- hit@3: 50.0%
- hit@4: 68.8%
- hit@5: 68.8%

Marginal contributions: {"rank1": 0.125, "rank2_incremental": 0.25, "rank3_incremental": 0.125, "rank4_incremental": 0.1875, "rank5_incremental": 0.0}

## Task D — Bootstrap

```json
{
  "n_boot": 5000,
  "n": 16,
  "rank_ci": {
    "rank1": [
      0.0,
      0.3125
    ],
    "rank2": [
      0.0625,
      0.5
    ],
    "rank3": [
      0.0,
      0.3125
    ],
    "rank4": [
      0.0,
      0.375
    ],
    "rank5": [
      0.0,
      0.0
    ]
  },
  "rank_mean": {
    "rank1": 0.1257,
    "rank2": 0.2507,
    "rank3": 0.124,
    "rank4": 0.188,
    "rank5": 0.0
  },
  "pairwise_diff_ci": {
    "rank1_vs_rank2": [
      -0.4375,
      0.1875
    ],
    "rank1_vs_rank3": [
      -0.25,
      0.25
    ],
    "rank1_vs_rank4": [
      -0.3125,
      0.1875
    ],
    "rank1_vs_rank5": [
      0.0,
      0.3125
    ]
  },
  "bootstrap_best_rank_winner": {
    "1": 715,
    "2": 2808,
    "3": 440,
    "4": 1037,
    "5": 0
  }
}
```

## Task E — Calibration

```json
{
  "probability_buckets": {
    "high_12plus": {
      "n": 39,
      "hit_rate": 0.1538,
      "mean_predicted_prob": 0.147
    },
    "mid_8_12": {
      "n": 33,
      "hit_rate": 0.1515,
      "mean_predicted_prob": 0.0967
    },
    "low_5_8": {
      "n": 8,
      "hit_rate": 0.0,
      "mean_predicted_prob": 0.0694
    }
  },
  "by_rank": {
    "rank1": {
      "n": 16,
      "hit_rate": 0.125,
      "mean_prob": 0.1569
    },
    "rank2": {
      "n": 16,
      "hit_rate": 0.25,
      "mean_prob": 0.1406
    },
    "rank3": {
      "n": 16,
      "hit_rate": 0.125,
      "mean_prob": 0.118
    },
    "rank4": {
      "n": 16,
      "hit_rate": 0.1875,
      "mean_prob": 0.0979
    },
    "rank5": {
      "n": 16,
      "hit_rate": 0.0,
      "mean_prob": 0.0791
    }
  }
}
```

## Task F — Shadow reranking (OOS)

```json
{
  "train_n": 10,
  "test_n": 6,
  "global_weights": {
    "1": 0.2,
    "2": 0.2,
    "3": 0.1,
    "4": 0.2,
    "5": 0.0
  },
  "segment_weights": {
    "segment_stage:knockout": {
      "1": 0.2,
      "2": 0.2,
      "3": 0.1,
      "4": 0.2,
      "5": 0.0
    },
    "segment_favorite:strong_favorite": {
      "1": 0.4,
      "2": 0.2,
      "3": 0.0,
      "4": 0.2,
      "5": 0.0
    },
    "segment_scoring:low_scoring": {
      "1": 0.0,
      "2": 0.2,
      "3": 0.2,
      "4": 0.4,
      "5": 0.0
    },
    "segment_scoring:high_scoring": {
      "1": 0.4,
      "2": 0.2,
      "3": 0.0,
      "4": 0.0,
      "5": 0.0
    },
    "segment_btts:btts_no": {
      "1": 0.0,
      "2": 0.2,
      "3": 0.0,
      "4": 0.4,
      "5": 0.0
    },
    "segment_btts:btts_yes": {
      "1": 0.4,
      "2": 0.2,
      "3": 0.2,
      "4": 0.0,
      "5": 0.0
    }
  },
  "baseline": {
    "top1_accuracy": 0.0,
    "hit@3": 0.5,
    "hit@5": 0.6667,
    "mean_reciprocal_rank": 0.2639,
    "n_test": 6
  },
  "global_rerank": {
    "top1_accuracy": 0.0,
    "hit@3": 0.5,
    "hit@5": 0.6667,
    "mean_reciprocal_rank": 0.2639,
    "n_test": 6
  },
  "segment_rerank": {
    "top1_accuracy": 0.0,
    "hit@3": 0.5,
    "hit@5": 0.6667,
    "mean_reciprocal_rank": 0.2639,
    "n_test": 6
  },
  "best_candidate": "baseline",
  "delta_mrr": 0.0
}
```
