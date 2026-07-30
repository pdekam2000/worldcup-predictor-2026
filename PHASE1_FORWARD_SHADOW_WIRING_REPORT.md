# PHASE 1 — PARITY + FORWARD-SHADOW WIRING REPORT

## Part A — Parity

| Env | Commit |
|-----|--------|
| Diff `cfe6a62..4ee0a03` | helpers/docs only (no runtime/model/schema behavior) |
| Production before | `cfe6a62` |
| Production after Part A | `4ee0a03` |
| Canonical regression after Part A | PASS |

## Part B — Wiring

### Architecture / execution flow

1. Owner daily `run_daily_predictions` completes WDE+ECSE for a fixture.
2. `maybe_capture_after_prediction_persistence` commits canonical freeze.
3. Immediately afterward (still non-blocking for canonical): `maybe_run_l2f_forward_shadow`.
4. Hook checks kill switch / mode / owner scope / freeze status.
5. Loads fixture + canonical lambdas + odds row (no invention).
6. Runs `run_shadow_pipeline` under a hard timeout in a worker thread.
7. Persists Lambda V2 / Exact V2 rows only in `lambda_v2_shadow_outputs`.
8. Upserts job row in `l2f_forward_shadow_jobs` (`success|skipped|blocked|failed`).
9. Canonical freeze/API path never waits on shadow success; exceptions are swallowed.

### Flags

- `L2F_FORWARD_SHADOW_MODE=shadow|off` (default `shadow`)
- `L2F_FORWARD_SHADOW_KILL_SWITCH=true` disables without touching canonical
- `L2F_FORWARD_SHADOW_TIMEOUT_SEC` (default 8)

### Idempotency

- Job unique key: `(fixture_id, freeze_id, run_id)`
- Successful jobs skip re-execution (`already_success_idempotent`)
- Shadow rows use `INSERT OR IGNORE` on `(fixture_id, model_id, shadow_hash)`

## Promotion / historical expansion

**Not performed.** Shadow-only; backfill mode exists but was not started.
