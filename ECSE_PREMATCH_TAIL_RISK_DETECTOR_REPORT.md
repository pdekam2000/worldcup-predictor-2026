# ECSE Prematch Tail-Risk Detector Report

**Final status:** `PREMATCH_TAIL_DETECTOR_FOUND_NO_ACTIONABLE_EDGE`
**SHA:** 7a93a03c60b7d95898f7b6f9f3b5d1dca560a21b | **Vienna:** 2026-07-13 20:25 CEST

## Leakage warning

Prior +8.76pp lift used **actual** high-score-tail classification for routing — not valid for production.
This detector uses **prematch features only** for routing.

## Executive answers

| # | Question | Answer |
|---|---|---|
| 1 | Identify tail before kickoff? | Partial — PR-AUC 0.3256 |
| 2 | Most useful features | total_lambda, tail_mass, BTTS mass, Last8 scoring rates |
| 3 | Tail base rate | 0.231 |
| 4 | HIGH tier precision | 0.2798 |
| 5 | HIGH tier recall | 0.6865 |
| 6 | Calibrated? | ECE 0.2363 |
| 7 | Conditional Top5 on positives? | Δ -2.5 pp |
| 8 | Global Top5 preserved? | Δ -1.417 pp |
| 9 | Chronological validation? | OOT n=55954 |
| 10 | Leagues benefit? | see league_breakdown |
| 11 | Segment router justified? | **No** |
| 12 | Remain Shadow? | **Yes** |

## Best model metrics

{
  "n": 55954,
  "base_rate": 0.231,
  "threshold": 0.45,
  "precision": 0.2798,
  "recall": 0.6865,
  "f1": 0.3976,
  "roc_auc": 0.617,
  "pr_auc": 0.3256,
  "brier_score": 0.2355,
  "calibration_error": 0.2363,
  "detector_positive_count": 31720,
  "false_positive_rate": 0.5309,
  "confusion_matrix": {
    "tp": 8875,
    "fp": 22845,
    "fn": 4052,
    "tn": 20182
  },
  "precision_above_base_multiple": 1.2111,
  "high_tier_count": 31720,
  "high_tier_precision": 0.2798,
  "high_tier_recall": 0.6865,
  "high_tier_coverage_of_true_tails": 0.6865
}

## Conditional correction (out-of-time)

{
  "oot_fixtures": 55954,
  "detector_positive_fixtures": 31720,
  "detector_negative_fixtures": 24234,
  "canonical_hit_rates_pct": {
    "top3": 33.279,
    "top5": 50.145,
    "top1": 12.646
  },
  "conditional_hit_rates_pct": {
    "top5": 48.728,
    "top3": 32.232,
    "top1": 11.947
  },
  "global_top5_lift_pp": -1.417,
  "global_top3_lift_pp": -1.047,
  "global_top1_lift_pp": -0.699,
  "end_result_top5_canonical_pct": 86.298,
  "end_result_top5_conditional_pct": 83.824,
  "detector_positive_top5_canonical_pct": 46.214,
  "detector_positive_top5_conditional_pct": 43.714,
  "conditional_top5_lift_on_positive_pp": -2.5,
  "non_tail_top5_canonical_pct": 55.29,
  "non_tail_top5_conditional_pct": 55.29,
  "non_tail_degradation_pp": 0.0,
  "league_breakdown": {
    "EN3": {
      "n": 1376,
      "canonical_top5": 51.381,
      "conditional_top5": 51.09,
      "lift_pp": -0.291
    },
    "EN2": {
      "n": 1372,
      "canonical_top5": 51.239,
      "conditional_top5": 50.437,
      "lift_pp": -0.802
    },
    "EN4": {
      "n": 1370,
      "canonical_top5": 49.051,
      "conditional_top5": 48.029,
      "lift_pp": -1.022
    },
    "US1": {
      "n": 1271,
      "canonical_top5": 42.408,
      "conditional_top5": 42.329,
      "lift_pp": -0.079
    },
    "SP2": {
      "n": 1141,
      "canonical_top5": 53.462,
      "conditional_top5": 53.9,
      "lift_pp": 0.438
    },
    "AR1": {
      "n": 1121,
      "canonical_top5": 63.515,
      "conditional_top5": 63.336,
      "lift_pp": -0.179
    },
    "JP2": {
      "n": 1085,
      "canonical_top5": 51.889,
      "conditional_top5": 49.677,
      "lift_pp": -2.212
    },
    "CO1": {
      "n": 1038,
      "canonical_top5": 58.671,
      "conditional_top5": 57.996,
      "lift_pp": -0.675
    },
    "IT2": {
      "n": 980,
      "canonical_top5": 54.184,
      "conditional_top5": 53.878,
      "lift_pp": -0.306
    },
    "IT1": {
      "n": 960,
      "canonical_top5": 54.167,
      "conditional_top5": 52.083,
      "lift_pp": -2.084
    },
    "SP1": {
      "n": 960,
      "canonical_top5": 54.271,
      "conditional_top5": 52.604,
      "lift_pp": -1.667
    },
    "US2": {
      "n": 956,
      "canonical_top5": 44.351,
      "conditional_top5": 42.05,
      "lift_pp": -2.301
    },
    "EN1": {
      "n": 943,
      "canonical_top5": 42.312,
      "conditional_top5": 42.312,
      "lift_pp": 0.0
    },
    "BR1": {
      "n": 928,
      "canonical_top5": 55.065,
      "conditional_top5": 55.28,
      "lift_pp": 0.215
    },
    "JP1": {
      "n": 924,
      "canonical_top5": 52.814,
      "conditional_top5": 52.273,
      "lift_pp": -0.541
    }
  }
}

## Promotion gate

{
  "checks": {
    "min_oot_fixtures": true,
    "min_detector_positive": true,
    "precision_above_base": false,
    "conditional_top5_lift": false,
    "global_top5_protected": false,
    "top3_protected": false,
    "end_result_not_degraded": false,
    "no_automatic_promotion": true,
    "multi_league_improvement": true
  },
  "recommend_segment_router": false,
  "leagues_improved": 2
}
