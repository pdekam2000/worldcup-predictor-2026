# Tier B WDE Dependency Failure Reproduction

**Date:** 2026-07-12  
**SHA before fix:** `a0dbdc0504e461f54e5179d905914760d6aa121c`  
**Scope:** owner / owner_shadow / five acceptance fixtures

## Summary

All five fixtures returned `PARTIAL` with `wde_skipped:WDE_DEPENDENCY_FAILED` and `wde_payload_missing` when the owner workflow ran **without production settings bootstrap**.

With `APP_ENV=production` (loading `.env.production`), WDE executes successfully for all five fixtures.

## Root Cause

| Layer | Finding |
|---|---|
| Entry | `scripts/_owner_vienna_1700_workflow_20260712.py` invoked `execute_prediction_job` directly |
| Settings | `get_settings()` loaded `.env` (dev) instead of `.env.production` because `APP_ENV` was unset |
| Gate | `run_daily_wde()` early-exits when `settings.api_football_configured` is false |
| Failure code | Generic `WDE_DEPENDENCY_FAILED` at stage `api_credentials` |
| ECSE | ECSE uses separate path (`build_ecse_live_prediction`) and does not require API key gate |
| Pipeline | `PredictPipeline.run()` succeeds from DB/cache even when API key gate blocks WDE |

## Per-Fixture Reproduction (without APP_ENV)

| fixture_id | competition | tier | prediction_scope | WDE status | failure_code | failure_stage | job_status |
|---|---|---|---|---|---|---|---|
| 1494698 | eliteserien | B | owner_shadow | skipped | WDE_DEPENDENCY_FAILED | api_credentials | partial |
| 1508803 | urvalsdeild | B | owner_shadow | skipped | WDE_DEPENDENCY_FAILED | api_credentials | partial |
| 1508804 | urvalsdeild | B | owner_shadow | skipped | WDE_DEPENDENCY_FAILED | api_credentials | partial |
| 1508805 | urvalsdeild | B | owner_shadow | skipped | WDE_DEPENDENCY_FAILED | api_credentials | partial |
| 1508806 | urvalsdeild | B | owner_shadow | skipped | WDE_DEPENDENCY_FAILED | api_credentials | partial |

## Per-Fixture Reproduction (with APP_ENV=production)

| fixture_id | WDE status | WDE decision | confidence | data_quality | ECSE Top1 |
|---|---|---|---|---|---|
| 1494698 | executed | away_win | 37.8 | OK | 0-2 |
| 1508803 | executed | home_win | 30.5 | OK | 3-0 |
| 1508804 | executed | away_win | 36.7 | OK | 1-1 |
| 1508805 | executed | home_win | 22.4 | OK | 2-0 |
| 1508806 | executed | away_win | 23.7 | OK | 1-1 |

## Comparison with Working Tier B (Allsvenskan)

Fixtures 1494204/1494205/1494208 had **pre-existing stored WDE payloads** from earlier runs with `APP_ENV=production`. The failing five fixtures had **no stored payload** and depended on a fresh WDE run blocked by missing API credentials.

## Not the Root Cause

- Competition normalization (eliteserien / urvalsdeild resolve correctly)
- Tier B registry routing
- API cache path (ECSE and pipeline use DB/cache successfully)
- WDE formula changes
- Missing team history (pipeline returns success when credentials are loaded)
