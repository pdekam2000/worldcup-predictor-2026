# Prediction Job Worker Regression — Root Cause

Date: 2026-07-10  
Release before hotfix: `d7d0505`

## Failure

`startPredictionJob` failed with:

```
cannot access local variable 'tier' where it is not associated with a value
```

## Exact failing line

`worldcup_predictor/gpt_actions/worker.py` line **134** (pre-fix):

```python
prediction_scope=_per_fixture_prediction_scope(prediction_scope, tier),
```

`tier` was assigned on line **139**, after the call.

## Why tier is unbound

Python evaluates `fixture_allowed_for_prediction(..., prediction_scope=_per_fixture_prediction_scope(prediction_scope, tier))` before any assignment in the loop body. Because `tier` is assigned later in the same `for` scope, the name is treated as local but unbound at reference time → `UnboundLocalError` caught by worker `except Exception` and stored as job `error`.

## Scopes affected

| Path | Affected? |
|------|-----------|
| Tier A `prediction_scope=production` | **YES** |
| Tier B `prediction_scope=owner_shadow` | **YES** |
| Owner unified `prediction_scope=owner` | **YES** |
| Explicit `fixture_ids` | **YES** |
| Filter-resolved fixture list | **YES** |

**All** prediction job paths through `execute_prediction_job` were broken — not Tier-A-only.

## Queued jobs

Jobs enqueue successfully (`202`) but fail immediately when the worker thread runs — status becomes `failed` with the error string. Queued state is transient.

## Duplicate work risk

No duplicate predictions were created — failure occurs before `mcp_runtime.run_fixture_prediction`. Retrying with a new job_id would not duplicate completed work because no work completed. Idempotency keys return the same job record but the broken worker still failed on each run.

## Fix

Move `tier = fixture_tier(daily.competition_key)` **before** `fixture_allowed_for_prediction(...)`.

Minimal one-line reorder; no routing semantic change.
