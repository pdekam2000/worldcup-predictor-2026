# PHASE 51G — EGIE Monitoring Dashboard Polish

**PHASE_51G_STATUS = PRODUCTION_ACTIVE**

**Date:** 2026-06-22

---

## Objective

Polish the EGIE monitoring dashboard with a clean white / light-green SaaS UI that displays **only live production data** from PostgreSQL evaluations, SQLite fixtures, and the Phase 51F scheduler.

---

## Backend changes

### New modules

| Module | Role |
|--------|------|
| `goal_timing/dashboard_service.py` | Aggregates monitoring payload |
| `goal_timing/scheduler_state.py` | Persists last run / API refresh to `data/egie/scheduler_state.json` |

### Extended `/api/goal-timing/dashboard`

Returns real fields (no mocks):

```json
{
  "counts": {
    "published_picks": 49,
    "evaluated_picks": 1,
    "pending_picks": 48,
    "no_pick_count": 19,
    "upcoming_picks": 48
  },
  "accuracy": {
    "team_winrate_pct": 100.0,
    "range_winrate_pct": 100.0,
    "minute_soft_winrate_pct": 100.0
  },
  "learning": {
    "dq_bucket_winrate": [...],
    "confidence_bucket_winrate": [...]
  },
  "scheduler": {
    "timer_active": true,
    "last_run_at": "...",
    "last_refresh_at": "...",
    "last_api_calls": 0,
    "next_run_at": "..."
  },
  "no_pick": { "count": 19, "items": [...] },
  "upcoming_picks": [...],
  "recent_evaluations": [...],
  "data_source": "postgresql_sqlite_live"
}
```

### Other API notes

- `list_stored_picks()` — fast read-only picks (no on-demand prediction generation on dashboard load)
- `prediction_monitoring_counts()` / `list_no_pick_predictions()` — repository helpers
- `auto_evaluation_job` writes scheduler state after each run
- Legacy keys preserved: `picks_today`, `accuracy_summary`, `evaluation_count`

### Unchanged

- `engine.py`, thresholds, model weights, Stripe/auth routes

---

## Frontend changes

### `GoalTimingDashboardPage.jsx`

- White cards, emerald accents, responsive grids (`grid-cols-2` → `lg:grid-cols-4`)
- Parallel fetch of all 5 EGIE endpoints with **clean error banner** on failure
- Sections: counts, accuracy, scheduler, DQ/confidence buckets, upcoming picks, recent evaluations, NO_PICK reasons
- Explicit subtitle: *No demo data*

### `GoalTimingPageShell.jsx`

- `variant="monitoring"` — white container, emerald nav pills

### `saasApi.js`

- Ensures `fetchGoalTimingHistory`, `fetchGoalTimingAccuracy`, `fetchGoalTimingPerformance` exported (required on production build)

---

## Validation

```bash
python scripts/validate_phase51g_egie_dashboard_polish.py
```

**Local:** 26/26 PASS  
**Production:** 32/32 PASS

Checks: dashboard shape, live data source, routes, scheduler state, white/emerald theme, mobile grids, all APIs 200, timer active, real counts.

---

## Production snapshot (post-deploy)

| Metric | Value |
|--------|-------|
| Published picks | **49** |
| Evaluated | **1** (Sheffield Utd vs Tottenham) |
| Pending eval | **48** (2026/27 PL upcoming) |
| NO_PICK rows | **19** (with DQ reasons) |
| Upcoming in dashboard | **48** |
| Scheduler timer | **active** |

---

## Files

**Backend:** `dashboard_service.py`, `scheduler_state.py`, `auto_evaluation_job.py`, `prediction_service.py`, `repository.py`, `goal_timing.py` routes  

**Frontend:** `GoalTimingDashboardPage.jsx`, `GoalTimingPageShell.jsx`, `saasApi.js`  

**Scripts:** `validate_phase51g_egie_dashboard_polish.py`, `deploy_phase51g_production.sh`, `deploy_phase51g_smoke.sh`, `pack_phase51g_deploy.sh`
