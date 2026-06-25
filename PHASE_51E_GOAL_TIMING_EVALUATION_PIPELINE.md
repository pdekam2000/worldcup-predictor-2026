# PHASE 51E — Goal Timing Evaluation Pipeline

**Status:** Implemented  
**Date:** 2026-06-20  
**Scope:** Prediction → evaluation → learning loop only (no engine/threshold/retrain changes)

---

## Objective

Complete the Elite Goal Timing Intelligence Engine (EGIE) loop:

1. Persist evaluations to PostgreSQL `goal_timing_evaluations`
2. Automatic finish detection for published picks
3. Automatic evaluation for three markets: **First Goal Team**, **Goal Range**, **Goal Minute**
4. API surfaces: `/history`, `/accuracy`, `/performance`
5. Dashboard integration with recent evaluations and accuracy summary
6. Learning statistics for operational feedback

---

## Architecture

```mermaid
flowchart LR
  subgraph predict [Prediction - unchanged]
    P[goal_timing_predictions]
  end
  subgraph sqlite [SQLite fixtures]
    F[fixtures + fixture_results + goal_events]
  end
  subgraph loop [Phase 51E]
    R[result_refresh.py]
    E[evaluation_job.py]
    L[learning_stats.py]
    PG[(goal_timing_evaluations)]
  end
  subgraph api [API]
    H[/history]
    A[/accuracy]
    PF[/performance]
    D[/dashboard]
  end
  P --> R
  R -->|API-Football optional| F
  F --> E
  P --> E
  E --> PG
  PG --> L
  PG --> H
  L --> A
  L --> PF
  PG --> D
```

### Data boundaries (preserved)

| Layer | Storage | Role |
|-------|---------|------|
| Predictions | PostgreSQL `goal_timing_predictions` | Phase 51D engine output |
| Fixtures / events | SQLite | Finish detection + actuals |
| Evaluations | PostgreSQL `goal_timing_evaluations` | Phase 51E learning loop |
| Legacy WC archive | SQLite `worldcup_stored_predictions` | **Not used** for EGIE |

---

## New modules

| Module | Responsibility |
|--------|----------------|
| `worldcup_predictor/goal_timing/outcome_adapter.py` | Map `FixtureOutcome` → `actual_first_goal_team` (home/away/none) + effective minute |
| `worldcup_predictor/goal_timing/result_refresh.py` | Finish detection + API refresh for picks past kickoff |
| `worldcup_predictor/goal_timing/evaluation_job.py` | `run_goal_timing_evaluations()`, `run_goal_timing_learning_loop()` |
| `worldcup_predictor/goal_timing/learning_stats.py` | Winrate aggregates by market, league, DQ, confidence, predicted team |
| `worldcup_predictor/goal_timing/history_service.py` | API serialization for history/accuracy/performance |

### Repository extensions (`GoalTimingRepository`)

- `save_evaluation()` — UPSERT on `prediction_id` (unique)
- `get_evaluation_by_prediction_id()` / `get_evaluation_by_fixture()`
- `list_evaluations_joined()` — prediction + evaluation join for UI/API
- `list_published_predictions()` — all published picks (upcoming + finished)
- `count_evaluations()`

---

## Evaluation logic (unchanged)

Uses existing `evaluate_goal_timing_prediction()` in `worldcup_predictor/goal_timing/evaluation.py`:

| Market | Status values | Winrate rule |
|--------|---------------|--------------|
| First Goal Team | correct / wrong / pending | `correct / (correct + wrong)` |
| Goal Range | correct / wrong / pending | same |
| Goal Minute | correct / partial / wrong / pending | strict winrate excludes partial; **soft_winrate** includes partial |

Minute tolerance bands and range buckets come from `goal_timing/config.py` — **not modified**.

---

## Automatic loop

### 1. Finish detection (`refresh_goal_timing_fixture_results`)

- Scans published `goal_timing_predictions` where `match_date <= now`
- Skips fixtures already finished with complete outcome backfill
- Optionally calls API-Football (`max_api_calls` cap, default 50)
- Persists fixture, result, and goal events to SQLite

### 2. Evaluation (`run_goal_timing_evaluations`)

- Resolves outcome via `FixtureOutcomeResolver`
- Builds actuals via `outcome_adapter`
- Calls `evaluate_goal_timing_prediction()`
- Persists to `goal_timing_evaluations`
- Skips unchanged rows when statuses match (idempotent)

### CLI

```bash
python scripts/egie_phase51e_goal_timing_evaluation.py
python scripts/egie_phase51e_goal_timing_evaluation.py --full --limit 200 --max-api-calls 50
```

### API trigger

```http
POST /api/goal-timing/evaluations/run?limit=200&max_api_calls=50
```

Recommended: cron/systemd every 30–60 minutes after match windows (same pattern as WC `auto_evaluation_job`, but **separate** scope).

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/goal-timing/history` | Paginated evaluated predictions |
| GET | `/api/goal-timing/accuracy` | Market-level winrates |
| GET | `/api/goal-timing/performance` | Full learning statistics |
| GET | `/api/goal-timing/dashboard` | Picks + `recent_evaluations` + `accuracy_summary` |
| POST | `/api/goal-timing/evaluations/run` | Manual/scheduled loop trigger |

Query params: `limit`, `offset`, `competition_key` (where applicable).

---

## Learning statistics (`/performance`)

- **by_market** — first_goal_team, goal_range, goal_minute
- **by_league** — per `competition_key`
- **by_dq_bucket** — `dq_lt_0_45`, `dq_0_45_0_55`, `dq_0_55_0_65`, `dq_gte_0_65`
- **by_confidence_bucket** — `conf_lt_0_50`, `conf_0_50_0_65`, `conf_gte_0_65`
- **by_predicted_first_goal_team** — home / away / none

DQ threshold `0.45` is used only for **reporting buckets** — prediction gate unchanged.

---

## Frontend (Phase 51E)

| Route | Page |
|-------|------|
| `/goal-timing/history` | `GoalTimingHistoryPage` — live evaluation cards |
| `/goal-timing/accuracy` | `GoalTimingAccuracyPage` — market winrates |
| `/goal-timing/performance` | `GoalTimingPerformancePage` — bucket tables |
| `/goal-timing/dashboard` | Recent evaluations + accuracy summary |

API helpers in `base44-d/src/api/saasApi.js`: `fetchGoalTimingHistory`, `fetchGoalTimingAccuracy`, `fetchGoalTimingPerformance`.

---

## Validation

```bash
python scripts/validate_phase51e_goal_timing_evaluation.py
```

Checks: evaluation math, 0-0 actuals, learning stats shape, API routes, report file.

---

## Production notes

- **48 upcoming PL picks** (2026/27) will evaluate only after those fixtures finish and results are refreshed.
- **380 finished PL 2023/24 fixtures** in SQLite can be evaluated if matching predictions exist in PostgreSQL.
- Phase A goal events (303 rows) improve minute/team resolution for overlapping fixture IDs.
- No changes to `engine.py`, `MIN_DATA_QUALITY_FOR_PREDICTION`, or model weights.

---

## Files changed / added

**Backend**

- `worldcup_predictor/goal_timing/outcome_adapter.py` (new)
- `worldcup_predictor/goal_timing/result_refresh.py` (new)
- `worldcup_predictor/goal_timing/evaluation_job.py` (new)
- `worldcup_predictor/goal_timing/learning_stats.py` (new)
- `worldcup_predictor/goal_timing/history_service.py` (new)
- `worldcup_predictor/goal_timing/storage/repository.py` (extended)
- `worldcup_predictor/api/routes/goal_timing.py` (extended)

**Scripts**

- `scripts/egie_phase51e_goal_timing_evaluation.py` (new)
- `scripts/validate_phase51e_goal_timing_evaluation.py` (new)

**Frontend**

- `base44-d/src/pages/goalTiming/GoalTimingHistoryPage.jsx`
- `base44-d/src/pages/goalTiming/GoalTimingAccuracyPage.jsx` (new)
- `base44-d/src/pages/goalTiming/GoalTimingPerformancePage.jsx` (new)
- `base44-d/src/pages/goalTiming/GoalTimingDashboardPage.jsx`
- `base44-d/src/components/goalTiming/GoalTimingPageShell.jsx`
- `base44-d/src/api/saasApi.js`
- `base44-d/src/App.jsx`
- `base44-d/src/lib/navConfig.js`

---

## What was NOT changed

- `worldcup_predictor/goal_timing/engine.py`
- `worldcup_predictor/goal_timing/config.py` thresholds
- ML retrain / calibration pipelines
- Legacy `worldcup_stored_predictions` archive path
