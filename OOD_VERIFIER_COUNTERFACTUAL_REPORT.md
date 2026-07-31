# OOD_VERIFIER_COUNTERFACTUAL_REPORT

**Status:** `OOD_VERIFIER_COUNTERFACTUAL_RESEARCH_COMPLETE`  
**Decision:** `BUILD_OOD_VERIFIER`  
**Baseline commit:** `28fd217`  
**Deployment:** NOT DEPLOYED

## Question

If False OOD decisions had been corrected, would the betting system actually become better?

**Answer / decision:** `BUILD_OOD_VERIFIER`

Rationale: Correcting False OOD improves overlay ROI/profit enough that building a verifier is justified.

## Metrics

- Original overlay ROI: `0.17277978`
- Counterfactual ROI: `0.41060797`
- Perfect OOD ROI: `0.56085642`
- Original DD: `2.4025` → CF `2.4025` → Perfect `2.3`
- Original exposure: `0.282653` → CF `0.486735`
- Recovered profit: `14.8`
- False OOD missed profit total: `14.8`

## Cost-benefit

```json
{
  "research_only": true,
  "potential_roi_improvement": 0.23782819,
  "potential_drawdown_increase": 0.0,
  "potential_exposure_increase": 0.204082,
  "recovered_profit": 14.8,
  "perfect_ood_roi": 0.56085642,
  "perfect_ood_drawdown": 2.3,
  "potential_complexity": "Medium \u2014 verifier on top of existing OOD detector",
  "risk": "Medium \u2014 verifier errors could reintroduce True OOD losses",
  "maintenance_cost": "Medium \u2014 needs ongoing calibration monitoring",
  "expected_benefit": "High",
  "decision_inputs": {
    "improves": true,
    "reaches_baseline": true,
    "perfect_attractive": true,
    "n_false_ood": 68,
    "n_true_ood": 7
  }
}
```

**NOT DEPLOYED** — no OOD Verifier built in this phase.
