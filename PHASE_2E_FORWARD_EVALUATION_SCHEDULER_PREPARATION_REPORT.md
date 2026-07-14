# Phase 2E — Forward Evaluation Scheduler Preparation Report

**Date:** 2026-07-14  
**Commit:** `28da3e0` — `feat: prepare forward evaluation scheduler`  
**Final status:** `FORWARD_EVALUATION_SCHEDULER_PREPARED_DISABLED`

---

## Part 0 — Source parity

| Step | Result |
|------|--------|
| Diff `1e2928c..1b02be5` | Docs + acceptance script path fix only — **no runtime changes** |
| Production fast-forward | `1b02be5` before Phase 2E |
| Post Phase 2E deploy | Local = Origin = Production = **`28da3e0`** |

---

## Answers (Parts A–U)

### 1. Existing scheduling infrastructure?
See `PHASE_2E_SCHEDULER_INFRASTRUCTURE_AUDIT.md`. Key items: legacy orchestrator (prediction capture), `worldcup-evaluate-results`, odds refresh, daily predict timers. **Production also has** `worldcup-forward-evaluation-daily.timer` and `-weekly.timer` (pre-existing, separate from Phase 2E unit).

### 2. Conflicting timer found?
**Yes — review note:** `worldcup-forward-evaluation-daily.timer` is **enabled** on production and ran today. Phase 2E **did not enable** the new `worldcup-forward-evaluation.timer`. Legacy daily path may still invoke older orchestration — Phase 2E scheduler is a parallel safe path using Phase 2D functions only.

### 3. Canonical orchestrator?
`worldcup_predictor/forward_evaluation/scheduler.py` → `run_forward_evaluation_cycle()`

### 4. Phase 2D functions reused?
- `sync_result_for_fixture()`
- `evaluate_frozen_prediction()` (evaluation_service facade)
- `verify_freeze_integrity()`

### 5. Candidate selection?
Active freezes → scope filter → lookback window → terminal/postponed classification → integrity gate → result availability → evaluation state.

### 6. Limits enforced?
Defaults: `fixture_limit=25`, `lookback_hours=72`, `provider_call_limit=25`, `max_runtime=900s`, max insert caps.

### 7. Overlap prevention?
`scheduler_cycle_lock()` with JSON metadata; returns `FORWARD_EVALUATION_CYCLE_ALREADY_RUNNING`.

### 8. Stale locks?
Age-based recovery (>7200s default) with auditable metadata file.

### 9. Checkpoint/ledger?
`forward_evaluation_runs` table (additive migration) + JSON artifact from CLI.

### 10. Dry-run default?
**Yes** — CLI defaults to dry-run; `--apply` required for writes.

### 11. Apply without explicit flag?
**No** — writes refused unless `--apply`.

### 12. Scopes supported?
`production`, `owner_shadow`, `owner_daily`, `all`

### 13. Tier B owner-only preserved?
**Yes** — eligibility bucket `OWNER_ONLY` for owner_shadow/Tier B.

### 14. Unavailable components excluded?
**Yes** — Phase 2D `NOT_EVALUATED_UNAVAILABLE` semantics unchanged.

### 15. Migration required?
Additive only: `forward_evaluation_runs` table + index.

### 16. Unit files created?
- `deployment/systemd/worldcup-forward-evaluation.service`
- `deployment/systemd/worldcup-forward-evaluation.timer`

### 17. Units installed?
**Yes** — copied to `/etc/systemd/system/`, daemon-reload.

### 18. Timer enabled?
**No** — `worldcup-forward-evaluation.timer` is **disabled**.

### 19. Timer active?
**No** — **inactive**.

### 20. Production dry-run findings?
15 candidates: 12 prematch/invalid, 2 already evaluated, 1 result not available. **Zero writes.**

### 21. Production dry-run wrote anything?
**No.**

### 22. Bounded manual apply?
Limit 5: +1 `actual_results`, +1 `market_evaluations`, +1 ledger row. Repeat apply: **0 inserts**, 3 evaluations reused.

### 23. Repeat idempotent?
**Yes.**

### 24. Predictions regenerated?
**No** — orchestrator/capture not called.

### 25. Freezes modified?
**No** — content hashes unchanged.

### 26. Public accuracy aggregates changed?
**No** — no dashboard modifications.

### 27. Regressions passed?
Phase 2E/2D/2A/2B/2C tests + compileall **PASS** locally.

### 28. Local = Origin = Production?
**Yes** — `28da3e0`

### 29. Scheduler activation approved?
**No** — timer remains **disabled** pending owner approval.

### 30. Final status
`FORWARD_EVALUATION_SCHEDULER_PREPARED_DISABLED`

---

## Validation summary

| Check | Result |
|-------|--------|
| Phase 2E tests (15) | PASS |
| Phase 2D regression | PASS |
| systemd-analyze verify | PASS |
| Timer disabled/inactive | PASS |
| Production dry-run | PASS (no writes) |
| Manual apply (≤5) | PASS |

## STOP boundary

Completed: parity → implement → local validation → commit → push → deploy → disabled unit install → production dry-run → bounded manual apply → timer verification → report.

**Not started:** timer enable, broad batch, historical backfill, public dashboard changes.
