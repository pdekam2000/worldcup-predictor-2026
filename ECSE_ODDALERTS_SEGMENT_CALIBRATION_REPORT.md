# ECSE OddAlerts Segment Calibration Report

**Phase:** ECSE-ODDALERTS-4  
**Generated:** 2026-07-01 05:49:15 UTC  
**Mode:** Research calibration — no production writes

---

## V1 problem

WEAK badge (15.0% Top-1) outperformed STRONG (12.5%) — rules were display-oriented, not evidence-calibrated.

---

## V2 monotonicity (Top-3 primary)

```json
{
  "primary_metric": "top3_hit_rate",
  "strong": 0.3187,
  "medium": 0.2809,
  "weak": 0.0,
  "monotonic": true
}
```

## V1 vs V2 performance

### V1
```json
{
  "STRONG_SHADOW_SIGNAL": {
    "count": 32,
    "top1_hit_rate": 0.125,
    "top3_hit_rate": 0.3125,
    "top5_hit_rate": 0.4688,
    "top10_hit_rate": 0.7812
  },
  "MEDIUM_SHADOW_SIGNAL": {
    "count": 113,
    "top1_hit_rate": 0.1062,
    "top3_hit_rate": 0.2832,
    "top5_hit_rate": 0.4336,
    "top10_hit_rate": 0.7699
  },
  "WEAK_SHADOW_SIGNAL": {
    "count": 40,
    "top1_hit_rate": 0.15,
    "top3_hit_rate": 0.3,
    "top5_hit_rate": 0.45,
    "top10_hit_rate": 0.775
  },
  "WATCH_ONLY": {
    "count": 0
  },
  "DO_NOT_USE": {
    "count": 0
  }
}
```

### V2
```json
{
  "STRONG_SHADOW_SIGNAL": {
    "count": 91,
    "top1_hit_rate": 0.1209,
    "top3_hit_rate": 0.3187,
    "top5_hit_rate": 0.4615,
    "top10_hit_rate": 0.7692
  },
  "MEDIUM_SHADOW_SIGNAL": {
    "count": 89,
    "top1_hit_rate": 0.1236,
    "top3_hit_rate": 0.2809,
    "top5_hit_rate": 0.4494,
    "top10_hit_rate": 0.7865
  },
  "WEAK_SHADOW_SIGNAL": {
    "count": 5,
    "top1_hit_rate": 0.0,
    "top3_hit_rate": 0.0,
    "top5_hit_rate": 0.0,
    "top10_hit_rate": 0.6
  },
  "WATCH_ONLY": {
    "count": 0
  },
  "DO_NOT_USE": {
    "count": 0
  }
}
```

---

## Best predictive segments

```json
[
  {
    "bucket": "spread_bucket:spread_mid",
    "top3_lift": 0.0771,
    "top5_lift": 0.033,
    "dimension": "spread_bucket",
    "value": "spread_mid",
    "sample_size": 84,
    "top1_hit_rate": 0.119,
    "top3_hit_rate": 0.369,
    "top5_hit_rate": 0.4762,
    "top10_hit_rate": 0.7976,
    "top1_wilson_ci": [
      0.066,
      0.2055
    ],
    "top3_wilson_ci": [
      0.2737,
      0.4758
    ],
    "low_sample_warning": false,
    "caution_only": false
  },
  {
    "bucket": "competition:bundesliga",
    "top3_lift": 0.0602,
    "top5_lift": 0.0357,
    "dimension": "competition",
    "value": "bundesliga",
    "sample_size": 71,
    "top1_hit_rate": 0.1408,
    "top3_hit_rate": 0.3521,
    "top5_hit_rate": 0.4789,
    "top10_hit_rate": 0.7887,
    "top1_wilson_ci": [
      0.0783,
      0.2402
    ],
    "top3_wilson_ci": [
      0.2512,
      0.4682
    ],
    "low_sample_warning": false,
    "caution_only": false
  },
  {
    "bucket": "promotion_action:inserted",
    "top3_lift": 0.0506,
    "top5_lift": 0.0363,
    "dimension": "promotion_action",
    "value": "inserted",
    "sample_size": 73,
    "top1_hit_rate": 0.137,
    "top3_hit_rate": 0.3425,
    "top5_hit_rate": 0.4795,
    "top10_hit_rate": 0.7945,
    "top1_wilson_ci": [
      0.0761,
      0.2341
    ],
    "top3_wilson_ci": [
      0.2439,
      0.4567
    ],
    "low_sample_warning": false,
    "caution_only": false
  },
  {
    "bucket": "bookmaker_agreement:False",
    "top3_lift": 0.0414,
    "top5_lift": 0.0183,
    "dimension": "bookmaker_agreement",
    "value": "False",
    "sample_size": 78,
    "top1_hit_rate": 0.1538,
    "top3_hit_rate": 0.3333,
    "top5_hit_rate": 0.4615,
    "top10_hit_rate": 0.7821,
    "top1_wilson_ci": [
      0.0903,
      0.2499
    ],
    "top3_wilson_ci": [
      0.2387,
      0.4436
    ],
    "low_sample_warning": false,
    "caution_only": false
  },
  {
    "bucket": "top1_is_1_1:True",
    "top3_lift": 0.0414,
    "top5_lift": 0.0183,
    "dimension": "top1_is_1_1",
    "value": "True",
    "sample_size": 78,
    "top1_hit_rate": 0.1538,
    "top3_hit_rate": 0.3333,
    "top5_hit_rate": 0.4615,
    "top10_hit_rate": 0.7821,
    "top1_wilson_ci": [
      0.0903,
      0.2499
    ],
    "top3_wilson_ci": [
      0.2387,
      0.4436
    ],
    "low_sample_warning": false,
    "caution_only": false
  },
  {
    "bucket": "lambda_total_bucket:lambda_total_mid",
    "top3_lift": 0.0277,
    "top5_lift": 0.031,
    "dimension": "lambda_total_bucket",
    "value": "lambda_total_mid",
    "sample_size": 97,
    "top1_hit_rate": 0.1134,
    "top3_hit_rate": 0.3196,
    "top5_hit_rate": 0.4742,
    "top10_hit_rate": 0.7835,
    "top1_wilson_ci": [
      0.0645,
      0.1917
    ],
    "top3_wilson_ci": [
      0.2352,
      0.4177
    ],
    "low_sample_warning": false,
    "caution_only": false
  },
  {
    "bucket": "lambda_diff_bucket:lambda_diff_tight",
    "top3_lift": 0.0256,
    "top5_lift": 0.033,
    "dimension": "lambda_diff_bucket",
    "value": "lambda_diff_tight",
    "sample_size": 63,
    "top1_hit_rate": 0.1587,
    "top3_hit_rate": 0.3175,
    "top5_hit_rate": 0.4762,
    "top10_hit_rate": 0.7778,
    "top1_wilson_ci": [
      0.0886,
      0.2681
    ],
    "top3_wilson_ci": [
      0.2159,
      0.44
    ],
    "low_sample_warning": false,
    "caution_only": false
  },
  {
    "bucket": "lambda_diff_bucket:lambda_diff_moderate",
    "top3_lift": 0.0008,
    "top5_lift": -0.053,
    "dimension": "lambda_diff_bucket",
    "value": "lambda_diff_moderate",
    "sample_size": 82,
    "top1_hit_rate": 0.0732,
    "top3_hit_rate": 0.2927,
    "top5_hit_rate": 0.3902,
    "top10_hit_rate": 0.7805,
    "top1_wilson_ci": [
      0.034,
      0.1506
    ],
    "top3_wilson_ci": [
      0.2053,
      0.3987
    ],
    "low_sample_warning": false,
    "caution_only": false
  }
]
```

---

## Promotion eligible (v2)

**Count:** 63

---

## Final recommendation

`SEGMENTS_V2_CALIBRATED`
