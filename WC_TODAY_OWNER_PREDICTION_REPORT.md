# WC Today Owner Prediction Report

**Date (Europe/Vienna):** 2026-06-30
**Competition:** world_cup_2026
**Final recommendation:** `WC_TODAY_REPORT_READY`

## Pipeline executed

1. `python scripts/run_daily_owner_prediction_cycle.py --timezone Europe/Vienna --fetch-missing-odds ...`
2. `python scripts/owner_daily_predictions.py --date today --timezone Europe/Vienna --competitions world_cup_2026 --limit 10 --include-shadow`
3. `python scripts/build_wc_today_owner_report.py`
4. `python scripts/validate_wc_today_owner_predictions.py`

## Summary

- Fixtures in WC report: **4**
- WDE coverage: **4**
- ECSE coverage: **4**
- Odds coverage: **4**
- Shadow data: **4**
- Validation: **16/16** checks passed

## Expected fixtures (owner task)

| Match | In report | ECSE Top-1 | WDE 1X2 | Label |
|-------|-----------|------------|---------|-------|
| Ivory Coast vs Norway | yes | 1-1 | draw | MEDIUM_SIGNAL |
| France vs Sweden | yes | 3-0 | home_win | STRONG_SIGNAL |
| Mexico vs Ecuador | yes | 1-0 | home_win | MEDIUM_SIGNAL |

## Missing data warnings

- —

## Reports

- Markdown: `reports\owner\wc_today_predictions_20260630.md`
- JSON: `reports\owner\wc_today_predictions_20260630.json`
- Validation artifact: `artifacts\wc_today_owner_predictions_validation.json`
- Daily cycle report: `reports/owner/daily_predictions_20260630.md`

## Notes

- Owner/internal only. No public prediction output changed.
- WDE, ECSE, EGIE, and billing logic unchanged.
- SQLite write probe succeeded — no lock during this run.
- All 3 expected knockout fixtures plus Netherlands vs Morocco (finished PEN) included.
- Mexico vs Ecuador kickoff is **2026-07-01 03:00 CEST** (late-night Vienna slot); included via expected-fixture resolver.
- Ivory Coast vs Norway: ECSE Top-1 **1-1** + WDE draw — **Draw/PEN risk** cover applies.
- France vs Sweden: **STRONG_SIGNAL** — WDE home_win + ECSE 3-0 align (confidence 79.4).

## Validation failures (0)

- None