# BETTING_DAY_FEATURE_STABILITY_FORENSIC_REPORT

**Status:** `BETTING_DAY_FEATURE_STABILITY_AND_OOD_FORENSIC_COMPLETE`  
**Baseline commit:** `f8187ac`  
**Deployment:** NOT DEPLOYED

## Verdict

Similarity Overlay remains on HOLD. This audit explains ROI deterioration without changing any locked policy.

**Primary root cause:** `Too many false OOD / skipped profitable days`

## Holdout snapshot

- Always / Baseline / Overlay ROI: `{'always': 0.38556604, 'baseline': 0.29096154, 'overlay': 0.17277978}`
- Drawdowns: `{'always': 4.33, 'baseline': 4.0, 'overlay': 2.4025}`
- OOD days analyzed: `75`
- False OOD: `68`
- Missed profit (eval): `14.8`
- Avoided loss (eval): `4.33`

## Feature drift / instability

- Top unstable: `['pct_full_super_consensus', 'avg_residual_risk', 'pct_over_direction', 'pct_tier_a', 'pct_high_goal_shift', 'n_discovered_fixtures', 'simultaneous_kickoff_count', 'n_eligible_fixtures', 'pct_consensus_high', 'n_selected_fixtures', 'total_insurance_tickets', 'capital_concentration_baseline', 'capital_concentration_calibrated', 'coupon_diversification_score', 'pct_model_conflict']`
- Top drifted: `['rolling_market_family_reliability', 'rolling_league_reliability', 'rolling_dow_reliability', 'rolling_insurance_rescue_rate', 'rolling_odds_bucket_reliability', 'rolling_model_calibration', 'rolling_month_phase', 'max_wde_confidence', 'median_entropy', 'avg_combined_odds', 'market_correlation_score', 'n_eligible_fixtures', 'avg_market_families', 'pct_btts_yes', 'n_discovered_fixtures']`
- Minimal stable feature count: `72`

## Method forensic

- Locked method: cosine / K=10
- Cosine deserved win on validation: `True`
- Validation winner: `cosine`

## Component contribution

```json
{
  "ood_filtering_roi_impact": -0.11131705,
  "regime_filtering_roi_impact": -0.00645099,
  "similarity_score_roi_impact": -0.00645099,
  "full_overlay_vs_baseline_roi": -0.11818176,
  "ood_filtering_dd_impact": -1.5975,
  "full_overlay_vs_baseline_dd": -1.5975
}
```

## Ranked failure causes

```json
[
  {
    "cause": "Too many false OOD / skipped profitable days",
    "impact_score": 694.8,
    "evidence": {
      "false_ood": 68,
      "true_ood": 7,
      "false_alarm_rate": 0.90666667,
      "missed_profit": 14.8,
      "avoided_loss": 4.33
    }
  },
  {
    "cause": "Noisy feature groups hurting overlay",
    "impact_score": 48.0,
    "evidence": {
      "groups_help_when_removed": [
        "timing",
        "slate",
        "market",
        "prediction_quality",
        "historical_rolling",
        "league"
      ]
    }
  },
  {
    "cause": "Feature distribution drift (train\u2192holdout)",
    "impact_score": 30.0,
    "evidence": {
      "top_drifted_features": [
        "rolling_market_family_reliability",
        "rolling_league_reliability",
        "rolling_dow_reliability",
        "rolling_insurance_rescue_rate",
        "rolling_odds_bucket_reliability"
      ]
    }
  },
  {
    "cause": "Poor feature stability",
    "impact_score": 17.8183,
    "evidence": {
      "top_unstable_features": [
        "pct_full_super_consensus",
        "avg_residual_risk",
        "pct_over_direction",
        "pct_tier_a",
        "pct_high_goal_shift"
      ]
    }
  },
  {
    "cause": "Regime instability / coarse regime count",
    "impact_score": 12.0,
    "evidence": {
      "note": "Locked regime count=3; forensic checks silhouette/stability separately"
    }
  },
  {
    "cause": "Capital reduction / over-restrictive overlay",
    "impact_score": 11.8182,
    "evidence": {
      "full_overlay_vs_baseline_roi": -0.11818176,
      "baseline_roi": 0.29096154,
      "overlay_roi": 0.17277978,
      "baseline_exposure": 0.530612,
      "overlay_exposure": 0.282653
    }
  },
  {
    "cause": "OOD filtering ROI drag",
    "impact_score": 11.1317,
    "evidence": {
      "ood_filtering_roi_impact": -0.11131705
    }
  },
  {
    "cause": "Small analog count / over-sensitive similarity",
    "impact_score": 0.5161,
    "evidence": {
      "similarity_score_roi_impact": -0.00645099
    }
  }
]
```

## Recommendations (NOT implemented)

```json
[
  {
    "priority": "Very high priority",
    "recommendation": "Recalibrate OOD detector to reduce false alarms on profitable days",
    "expected_impact": "High \u2014 recover missed profit without giving back all DD gains",
    "expected_risk": "Medium \u2014 may reintroduce some losing days",
    "implementation_complexity": "Medium",
    "do_not_implement_in_this_phase": true
  },
  {
    "priority": "High priority",
    "recommendation": "Shrink to a stable minimal feature subset (remove high-drift groups first)",
    "expected_impact": "Medium/High \u2014 may preserve DD with less ROI damage",
    "expected_risk": "Low/Medium",
    "implementation_complexity": "Medium",
    "do_not_implement_in_this_phase": true
  },
  {
    "priority": "High priority",
    "recommendation": "Separate exposure reduction from hard OOD skips",
    "expected_impact": "High \u2014 keep risk control without zeroing profitable days",
    "expected_risk": "Medium",
    "implementation_complexity": "Medium",
    "do_not_implement_in_this_phase": true
  },
  {
    "priority": "Medium priority",
    "recommendation": "Revisit regime count / stability with train-only silhouette constraints",
    "expected_impact": "Medium",
    "expected_risk": "Low",
    "implementation_complexity": "Low",
    "do_not_implement_in_this_phase": true
  },
  {
    "priority": "Low priority",
    "recommendation": "Re-audit cosine vs mixed after feature pruning (do not retune yet)",
    "expected_impact": "Low/Medium",
    "expected_risk": "Low",
    "implementation_complexity": "Low",
    "do_not_implement_in_this_phase": true
  }
]
```

**NOT DEPLOYED**
