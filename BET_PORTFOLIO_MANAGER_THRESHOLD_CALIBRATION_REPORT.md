# BET_PORTFOLIO_MANAGER_THRESHOLD_CALIBRATION_REPORT

**Status:** `BET_PORTFOLIO_MANAGER_THRESHOLD_CALIBRATION_HOLD`  
**Recommendation:** `CALIBRATION_HOLD`  
**Baseline commit:** `7e77aa3`  
**Deployment:** NOT DEPLOYED

## Baseline vs calibrated vs Always Bet (final holdout)

| Metric | Always Bet | Baseline Managed | Calibrated |
|---|---:|---:|---:|
| ROI | 0.38556604 | 0.32857143 | 0.31640693 |
| Max drawdown | 4.33 | 2.35 | 2.35 |
| Avg exposure/day | 4.326531 | 0.428571 | 0.471429 |

## Action semantics

```json
{
  "research_only": true,
  "definitions": {
    "BET": "Full-capital eligible day",
    "SMALL_BET": "Reduced-capital day",
    "WATCH_NO_CAPITAL": "Observation only \u2014 zero capital (not a hard rejection)",
    "HARD_SKIP": "True hard rejection \u2014 zero capital",
    "WATCH_POSITIVE": "Research micro-allocation subclass of near-SMALL_BET WATCH",
    "zero_capital_days": "Any day with exposure_units == 0 (WATCH_NO_CAPITAL + HARD_SKIP + empty selection)",
    "skipped": "Deprecated generic label \u2014 not used; see WATCH_NO_CAPITAL vs HARD_SKIP"
  },
  "full_capital_days": 0,
  "reduced_capital_days": 86,
  "WATCH_NO_CAPITAL_days": 400,
  "HARD_SKIP_days": 2,
  "all_zero_capital_days": 402,
  "active_day_ratio": 0.17622951,
  "action_counts": {
    "BET": 0,
    "SMALL_BET": 86,
    "WATCH_POSITIVE": 0,
    "WATCH_NO_CAPITAL": 400,
    "HARD_SKIP": 2
  }
}
```

## Grade compression

```json
{
  "research_only": true,
  "no_S_or_A_produced": true,
  "max_observed_score": 81.7259,
  "baseline_A_threshold": 84.0,
  "baseline_S_threshold": 92.0,
  "hypotheses_tested": {
    "grade_boundaries_too_high": true,
    "score_normalization_compressed": false,
    "weights_prevent_high_scores": true,
    "one_penalty_dominates": true,
    "incorrect_normalization_range": false,
    "action_mapping_not_aligned_with_grades": true,
    "incompatible_component_scales": false
  },
  "note": "Grade boundaries not changed until this audit is complete (this file is the audit)."
}
```

## Chronological validation

- Training: `{'roi': 0.45893471, 'max_drawdown': 2.27, 'active_day_ratio': 0.10273973}`
- Validation: `{'roi': 0.44819079, 'max_drawdown': 2.31, 'active_day_ratio': 0.34693878}`
- Final holdout: `{'roi': 0.31640693, 'max_drawdown': 2.35, 'active_day_ratio': 0.42857143}`

## Guardrails

- Passed: `['drawdown_le_75pct_always', 'exposure_le_70pct_always', 'active_days_ge_20pct', 'active_days_le_65pct']`
- Failed: `['managed_roi_ge_always']`

## WATCH split

- WATCH_POSITIVE: 4
- WATCH_REJECT: 324
- Locked micro-allocation: 0.2

## Notes

- Baseline policy remains immutable (`baseline_v1_7e77aa3`).
- Candidate stored separately at `calibrated_policy_candidate.json`.
- No WDE/ECSE/Coverage/Insurance/freeze changes.
- No production writes. NOT DEPLOYED.
