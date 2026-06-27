# PHASE A15 — PredOps Core Report

**Status:** `PREDOPS_DEPLOYED_OK`  
**Date:** 2026-06-25  
**Mode:** Analyze → Implement → Validate → Deploy → Report  
**Scope:** Orchestration, queue, snapshots, metadata, read APIs, admin UI, display gating — **no changes** to WDE math, EGIE math, scoring formulas, model weights, calibration, or subscription billing.

---

## Executive Summary

Phase A15 introduces **PredOps Core**: an autonomous prediction operations layer that maintains coverage via a **persistent priority queue**, creates **immutable versioned snapshots** (never silent overwrites), extracts **full market + EGIE metadata** with Tier A/B comparison fields, enforces **kickoff-based refresh policy**, and exposes **owner/admin dashboards** plus public read APIs.

| Metric | Result |
|--------|--------|
| Validation | **39/39 PASS** |
| Deploy | **DEPLOYED_OK** |
| Snapshots backfilled | **56** |
| WC 7-day snapshot coverage | **100%** |
| Combo eligible legs | **0** (all `no_bet` — engine output, not PredOps) |

---

## Architecture Summary

```mermaid
flowchart TB
  Timer[Hourly systemd timer] --> CLI[predops-run CLI]
  CLI --> Sync[sync_queue_from_fixtures]
  Sync --> Queue[(predops_queue)]
  CLI --> Claim[claim_next_jobs]
  Claim --> Pipeline[run_and_store_prediction]
  Pipeline --> Snap[create_snapshot_from_payload]
  Snap --> DB[(predops_snapshots)]
  DB --> UI[Match Center / Detail / Combo]
  DB --> API[/api/predops/*]
  API --> Admin[/admin/predops]
```

**Module:** `worldcup_predictor/predops/`

| Component | Role |
|-----------|------|
| `store.py` | SQLite queue + snapshot persistence |
| `engine.py` | Enqueue, process jobs, backfill |
| `snapshots.py` | Immutable snapshot creation + deltas |
| `markets.py` | Full market extraction (prediction / no_pick / unavailable) |
| `egie_snapshot.py` | EGIE metadata block |
| `refresh_policy.py` | TTL + immediate refresh triggers |
| `priority.py` | Queue bands: <3h → <12h → <24h → <72h → <7d |
| `coverage.py` | Coverage states + model/EGIE stats |
| `combo_readiness.py` | Bettable leg eligibility |
| `scheduler.py` | Hourly cycle + state file |
| `public_sanitize.py` | Strip debug from public API |

---

## Database Changes

**SQLite (`PHASE_A15_DDL` in `migrations.py`):**

| Table | Purpose |
|-------|---------|
| `predops_queue` | Persistent jobs — dedup via `job_key`, retry/backoff |
| `predops_snapshots` | Append-only snapshots; `is_latest` flag per fixture |
| `predops_scheduler_runs` | Scheduler audit trail |

**Snapshot fields:** `snapshot_id`, `fixture_id`, `generated_at`, `trigger_reason`, `previous_snapshot_id`, `payload_json`, `markets_json`, `egie_json`, `deltas_json`, `coverage_state`, `engine_version`

**Market snapshot deltas:** `changed_markets`, `confidence_delta`, `data_delta`, `odds_delta`, `lineup_delta`, `weather_delta`

---

## Queue Behavior

- **Priority:** kickoff <3h (1) → <12h (2) → <24h (3) → <72h (4) → <7d (5) → later (6)
- **Dedup:** `job_key = fixture_id:competition_key` — no duplicate active jobs
- **Retry:** max 3 attempts, exponential backoff via `next_retry_at`
- **States:** `queued`, `generating`, `completed`, `failed`
- **Dry run:** enqueues only, no pipeline execution
- **Production test:** deploy ran `--max-jobs 4` (0 processed — all fresh after backfill)

---

## Refresh Policy

| Kickoff window | Refresh interval |
|----------------|------------------|
| >7d | 24h |
| 3–7d | 12h |
| 24–72h | 6h |
| 3–24h | 2h |
| <3h | 30m |

**Immediate triggers:** official lineups, major odds move, injury update, weather change, engine version drift, stale snapshot.

**Finished fixtures:** skipped by `should_enqueue_refresh` (`finished_fixture`).

---

## Coverage Before / After

| Metric | Before A15 | After deploy |
|--------|------------|--------------|
| PredOps snapshots | 0 | **56** (backfill) |
| WC fixtures (7d) | 18 | 18 |
| Snapshot coverage | 0% | **100%** |
| Stored predictions | 18 | 18 |
| Combo eligible legs | 0 | 0 |

### Coverage states (production, 7-day window)

| State | Count |
|-------|-------|
| `no_bet` | 18 |
| `completed` (fresh) | 0 |
| `missing` | 0 |
| `queued` | 0 |

All 18 World Cup fixtures have latest snapshots; all are `no_bet` per existing engine policy.

---

## Tier A/B Coverage

- **model_tier A:** elite/production picks (from `pick_tier`, `best_available_pick`)
- **model_tier B:** legacy `detailed_markets` paths
- **confidence_tier:** separate field (`high` / `medium` / `low`) — never conflated with `model_tier`
- **Dual comparison per market:** `tier_a_prediction`, `tier_b_prediction`, `final_selected_prediction` with `agreement_status`

Public APIs strip Tier A/B debug; admin routes expose full snapshot history.

---

## EGIE Coverage

EGIE block stored per snapshot with: `first_goal_team`, time range, minute estimate, scorers, confidence, reliability, model version, `missing_requirements`, `next_refresh_trigger`.

**Production:** EGIE status predominantly `missing` / `no_pick` in payloads (EGIE not embedded in standard WC pipeline output). No fake values displayed.

---

## Combo Readiness

| Combo type | Ready |
|------------|-------|
| Safe | No |
| Balanced | No |
| Value | No |
| High odds | No |

**Reason:** `too_many_no_pick` — all snapshots have `no_bet: true`.

Combo engine reads **latest predops snapshots** via `load_prediction_payloads` overlay.

---

## APIs

| Route | Access | Purpose |
|-------|--------|---------|
| `GET /api/predops/coverage` | Public (sanitized) | Coverage totals |
| `GET /api/predops/coverage/admin` | Owner | Full coverage + model/EGIE |
| `GET /api/predops/queue` | Owner | Queue stats + jobs |
| `GET /api/predops/snapshots/latest` | Public (sanitized) | Latest snapshot |
| `GET /api/predops/snapshots/history` | Owner | Snapshot history |
| `GET /api/predops/combo-readiness` | Public | Combo leg eligibility |
| `POST /api/predops/run-once` | Owner | Manual cycle |

**CLI:** `python main.py predops-run [--dry-run] [--backfill] [--max-jobs N]`

---

## Frontend

| Path | Component |
|------|-----------|
| `/admin/predops` | `AdminPredOpsPage.jsx` |
| `src/lib/planGating.js` | Free/Starter/Pro display gating (no billing changes) |

**Plan gating (display only):**
- **Free:** best pick only, hide EGIE/tier/reasoning
- **Starter:** core markets, combos, archive basics
- **Pro:** EGIE, model source, Tier A/B, confidence timeline, full archive

---

## Files Changed

### Backend (new)
- `worldcup_predictor/predops/*` (12 modules)
- `worldcup_predictor/api/routes/predops.py`

### Backend (modified)
- `worldcup_predictor/database/migrations.py` — `PHASE_A15_DDL`
- `worldcup_predictor/api/main.py` — predops router
- `worldcup_predictor/api/match_center_helpers.py` — prefer latest snapshot payload
- `worldcup_predictor/automation/worldcup_background/prediction_runner.py` — auto-snapshot on store
- `worldcup_predictor/config/settings.py` — `predops_enabled`, `predops_max_jobs_per_cycle`
- `worldcup_predictor/cli/commands.py`, `main.py` — `predops-run`
- `deployment/systemd/worldcup-prediction-prefetch.service` — now runs `predops-run`

### Frontend
- `base44-d/src/pages/admin/AdminPredOpsPage.jsx`
- `base44-d/src/lib/planGating.js`
- `base44-d/src/App.jsx`, `saasApi.js`, `ownerNavConfig.js`

### Ops
- `scripts/validate_phase_a15_predops_core.py`
- `scripts/remote_deploy_phase_a15.sh`

---

## Validation

```
Phase A15 PredOps — 39/39 checks PASS
```

Key verifications:
- Queue enqueue + no duplicates
- Snapshots created, latest served, history preserved
- All markets have `prediction` / `no_pick` / `unavailable`
- `model_tier` vs `confidence_tier` semantics
- EGIE metadata shape
- No `no_pick` displayed as Draw
- Public sanitization vs owner full metadata
- Dry-run refresh policy
- WDE/scoring unchanged
- Production smoke: health, coverage, combo, matches — all **200**

Output: `data/validation/phase_a15_predops.json`

---

## Deploy Result

| Step | Result |
|------|--------|
| SQLite backup | OK |
| Schema migrate | `schema_ok` |
| Backfill snapshots | **56 created** |
| API restart | active |
| Dry run | 0 errors, 100% coverage |
| Small run (max 4) | 0 processed (fresh) |
| Smoke | health=200, coverage=200, combo=200, predops_page=200 |

**Backup location:** `/opt/worldcup-predictor/backups/phase-a15-<timestamp>/`

---

## Rollback Plan

1. `systemctl stop worldcup-prediction-prefetch.timer`
2. Restore `data/football_intelligence.db` from backup (optional — new tables are additive)
3. Restore frontend dist from backup
4. Revert `worldcup-prediction-prefetch.service` to `prefetch-predictions` if needed
5. `systemctl restart worldcup-api`
6. Set `PREDOPS_ENABLED=false` in `.env.production` to disable snapshot overlay without removing tables

PredOps tables are append-only; rollback does not require dropping schema.

---

## Final Recommendation

| Area | Status |
|------|--------|
| **PredOps orchestration** | **Shipped** — queue, snapshots, refresh, APIs, admin UI |
| **Snapshot coverage** | **100%** for active WC window after backfill |
| **Combo Tips** | Blocked by engine `no_bet` output — address in engine/calibration phase |
| **EGIE in snapshots** | Metadata layer ready; populate when EGIE blocks present in payloads |
| **Domestic leagues** | Auto-enqueue when fixtures appear in 7-day window |

**Final status:** `PREDOPS_DEPLOYED_OK`

Combo emptiness is `BLOCKED_ENGINE_OUTPUT` (orthogonal to PredOps). PredOps infrastructure is production-ready and will surface bettable combos automatically when the engine produces non-`no_bet` picks.

---

## STOP

Phase A15 complete.
