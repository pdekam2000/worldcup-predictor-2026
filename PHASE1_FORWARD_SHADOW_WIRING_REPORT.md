# PHASE 1 — PARITY + FORWARD-SHADOW WIRING REPORT

## Final status

**PHASE1_FORWARD_SHADOW_WIRING_COMPLETE**

## Part A — Parity

| Env | Commit |
|-----|--------|
| Diff `cfe6a62..4ee0a03` | helpers/docs only |
| Production after Part A | `4ee0a03` |
| Production final (Part B) | `73d1215` |
| Local / GitHub tip | `73d1215` |
| Canonical regression | PASS (identical λ with/without O/U 4.5) |

## Part B — Architecture / execution flow

1. Owner daily `run_daily_predictions` completes WDE+ECSE.
2. Canonical freeze via `maybe_capture_after_prediction_persistence`.
3. Non-blocking `maybe_run_l2f_forward_shadow` (try/except hard isolation).
4. Kill switch / mode / owner-scope / freeze-status gates.
5. Worker thread with **own SQLite connection** + process-cached strength store.
6. `run_shadow_pipeline` → form + alternate totals + Lambda V2 + Exact V2.
7. Persist only to additive shadow tables + `l2f_forward_shadow_jobs`.
8. Canonical API/freeze never depends on shadow completion.

### Flags

- `L2F_FORWARD_SHADOW_MODE=shadow|off` (default `shadow`)
- `L2F_FORWARD_SHADOW_KILL_SWITCH` (default false)
- `L2F_FORWARD_SHADOW_TIMEOUT_SEC` (default 90)

## Production smoke (owner_shadow scope, backfill-safe)

Fixtures: `1508819`, `1508818`, `1497638` — all **success**; second call idempotent.

| Metric | Count |
|--------|-------|
| Lambda V2 rows (smoke fixtures aggregate) | 24 |
| Exact V2 rows | 24 |

Artifact: `/opt/worldcup-predictor/backups/infra_deploy/20260730T165735Z/l2f_forward_shadow_smoke.json`

## Not performed

- Model promotion: **no**
- Historical expansion: **no**
- Canonical formula/ranking/UI changes: **no**
