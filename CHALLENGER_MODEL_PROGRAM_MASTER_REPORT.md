# CHALLENGER MODEL PROGRAM — MASTER REPORT

**Program status:** `CHALLENGER_FORWARD_EVALUATION_ACTIVE`

- Phase 1: `CHALLENGER_FRAMEWORK_READY`
- Phase 2: `CHALLENGER_BACKTEST_FRAMEWORK_READY`
- Phase 3: `GBGM_CHALLENGER_BACKTEST_COMPLETE`
- Phase 4: `CHALLENGER_FORWARD_SHADOW_ACTIVE`
- Phase 5: `CHALLENGER_MORE_DATA_REQUIRED`

## Safety

- WDE / ECSE / BTTS / O/U formulas unchanged
- Public visibility false
- Final decision authority false
- Additive challenger_* tables only
- No automatic production promotion

## Rollback

1. Stop calling Challenger runner from full-day wrapper
2. Leave challenger_* tables in place (or drop only those tables)
3. Canonical freezes and predictions remain authoritative

## Unresolved risks

- Forward sample = 0 completed evaluations
- XGBoost/CatBoost not installed (LightGBM + sklearn compared)
- Historical odds ROI not claimed without matched prematch odds series

```text
CHALLENGER_FORWARD_EVALUATION_ACTIVE
```
