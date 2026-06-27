# PHASE A14 — Background Prediction Prefetch Engine

**Status:** DEPLOYED_OK  
**Date:** 2026-06-25  
**Mode:** Analyze → Implement → Validate → Deploy → Report  
**Scope:** Orchestration and scheduling only — **no changes** to WDE, EGIE, scoring engine, prediction models, calibration, or confidence logic.

---

## Executive Summary

Phase A14 adds a **multi-competition background prediction prefetch engine** that runs hourly, prioritizes fixtures by kickoff proximity, refreshes stale predictions intelligently, and exposes an **Owner Prefetch Coverage** dashboard. Production deploy completed with the hourly systemd timer enabled.

| Metric | Result |
|--------|--------|
| Validation | **22/22 PASS** |
| Deploy | **DEPLOYED_OK** |
| Hourly timer | `worldcup-prediction-prefetch.timer` **active** |
| First production cycle | 12 predictions generated, 0 errors |
| World Cup 7-day coverage | **100%** (18/18) before and after |

**Combo Tips** remain empty because all stored predictions are `no_bet: true` (pre-existing engine behavior from Phase A13A audit). Prefetch ensures summaries are cached and fresh; it does not change pick logic.

---

## Part 1 — Coverage Target

### Target competitions

| Competition | Key |
|-------------|-----|
| World Cup 2026 | `world_cup_2026` |
| Champions League | `champions_league` |
| Europa League | `europa_league` |
| Conference League | `conference_league` |
| Premier League | `premier_league` |
| La Liga | `la_liga` |
| Serie A | `serie_a` |
| Bundesliga | `bundesliga` |
| Ligue 1 | `ligue_1` |

Each upcoming fixture (7-day window) should have **prediction, summary, best pick, confidence, value rating** stored before users visit Match Center or Combo Tips.

### Production coverage (7-day window)

#### Before first prefetch cycle

| Competition | Fixtures | Predictions | Coverage | Fresh | Stale | Missing |
|-------------|----------|-------------|----------|-------|-------|---------|
| World Cup 2026 | 18 | 18 | **100%** | 1 | 17 | 0 |
| All others | 0 | 0 | — | — | — | — |
| **Totals** | **18** | **18** | **100%** | **1** | **17** | **0** |

#### After first prefetch cycle (max 12 per run)

| Competition | Fixtures | Predictions | Coverage | Fresh | Stale | Missing |
|-------------|----------|-------------|----------|-------|-------|---------|
| World Cup 2026 | 18 | 18 | **100%** | **12** | **6** | 0 |
| All others | 0 | 0 | — | — | — | — |
| **Totals** | **18** | **18** | **100%** | **12** | **6** | **0** |

**Coverage delta:** Fresh predictions increased from 1 → 12 (+11). Stale decreased from 17 → 6. No missing fixtures.

Domestic leagues and UEFA competitions show **0 fixtures** in the 7-day window (off-season / no upcoming matches in schedule cache). When seasons resume, the hourly prefetch will backfill automatically.

---

## Part 2 — Background Prefetcher

### New module

```
worldcup_predictor/automation/prediction_prefetch/
├── __init__.py
├── engine.py          # run_prefetch_cycle — uses existing run_and_store_prediction
├── scheduler.py       # run_prefetch_scheduler_once — cycle + state snapshot
├── coverage.py        # collect_upcoming_fixtures, build_coverage_report
├── priority.py        # kickoff bands <12h / <24h / <48h / <7d
└── smart_refresh.py   # signal fingerprints, lineup window, engine version drift
```

### Scheduler

| Setting | Default | Location |
|---------|---------|----------|
| Window | 7 days | `prediction_prefetch_window_days` |
| Max per cycle | 24 | `prediction_prefetch_max_per_cycle` |
| Throttle | `api_throttle_delay_seconds` | between predictions |

**CLI:** `python main.py prefetch-predictions [--window-days N] [--max-per-cycle N]`

**Systemd:**
- `deployment/systemd/worldcup-prediction-prefetch.service`
- `deployment/systemd/worldcup-prediction-prefetch.timer` — hourly, `OnBootSec=5min`

**State file:** `data/shadow/prefetch_scheduler_state.json`

---

## Part 3 — Priority Queue

Fixtures sorted by kickoff band (lower = higher priority):

1. Kickoff **< 12h**
2. Kickoff **< 24h**
3. Kickoff **< 48h**
4. Kickoff **< 7d**

Within each band, earliest kickoff first. Fresh predictions are **skipped** unless smart-refresh signals require regeneration.

---

## Part 4 — Smart Refresh

Refresh triggers (orchestration layer only):

| Trigger | Mechanism |
|---------|-----------|
| Missing / invalid payload | `should_refresh_prediction` |
| Stale TTL | `is_prediction_fresh` |
| Engine version change | `_prefetch_signals.engine_version` vs `PREDICTION_ENGINE_VERSION` |
| Lineup window (<6h, no lineups signal) | `lineup_window_refresh` |
| Quality invalid | `is_stored_prediction_quality_valid` |

Signals stamped on payload after generation via `_prefetch_signals` (odds/weather fingerprints, lineup availability).

---

## Part 5 — Coverage Dashboard

**Owner page:** `/owner/prefetch-coverage`

**API:**
- `GET /api/owner/prefetch/coverage?window_days=7`
- `POST /api/owner/prefetch/run-once?window_days=7&max_per_cycle=24`

Displays per-competition: fixtures, predictions, coverage %, fresh, stale, missing, failed, bettable %. Totals and combo readiness summary.

---

## Part 6 — Combo Readiness

`comboGenerator.js` exports `comboReadiness(summary)`:

| Status | Label | Condition |
|--------|-------|-----------|
| `ready` | Ready | Has `best_pick`, not `no_bet` |
| `waiting` | Waiting for prediction | No summary or no pick |
| `no_bet` | No bet | `no_bet: true` |

Combo Builder filters to bettable legs only. **Production:** 18/18 WC predictions → `no_bet` → combo readiness **0 ready**.

---

## Part 7 — Safe Rate Limiting

- **Batching:** `max_per_cycle` cap (default 24/hour)
- **Cache-first:** Skips fresh predictions; uses schedule cache via `aggregate_all_competitions`
- **Throttle:** `api_throttle_delay_seconds` sleep between generations
- **Resume:** State persisted to `prefetch_scheduler_state.json`; timer `Persistent=true`
- **No duplicate writes:** Existing `WorldcupPredictionStore.upsert` + freshness guards

---

## Part 8 — Validation

**Script:** `scripts/validate_phase_a14_prediction_prefetch.py`

```
Phase A14 Prefetch — 22/22 checks PASS
```

| Check | Result |
|-------|--------|
| Prefetch module files | PASS |
| Owner API routes | PASS |
| Owner page wired | PASS |
| comboReadiness | PASS |
| WDE / scoring unchanged | PASS |
| Priority bands | PASS |
| Coverage report shape | PASS |
| Dry prefetch cycle (max 0) | PASS |
| no_bet → no draw in summary | PASS |
| Frontend build | PASS |
| Production smoke (matches, combo) | PASS |

Output: `data/validation/phase_a14_prefetch.json`

---

## Part 9 — Deploy

### Production server

- **Host:** `91.107.188.229` (`/opt/worldcup-predictor`)
- **Frontend:** `/var/www/worldcup/frontend/dist`
- **API:** `worldcup-api` restarted — **active**
- **Timer:** `worldcup-prediction-prefetch.timer` — **active**

### First production cycle

| Metric | Value |
|--------|-------|
| Scanned | 18 |
| Predicted | 12 |
| Skipped (fresh) | 1 |
| Skipped (cap) | 5 |
| Errors | 0 |
| Elapsed | **147,941 ms** (~148 s) |
| Avg latency / prediction | **~12.3 s** |

### Post-deploy smoke

| Endpoint | HTTP |
|----------|------|
| `/api/matches?competition=all&include_summary=true` | 200 |
| `/combo-tips` | 200 |
| `/owner/prefetch-coverage` | 200 |

### API usage notes

- API-Football season warnings logged for some league schedule fetches (off-season); schedule cache still serves WC fixtures.
- No provider quota exhaustion observed during first cycle (12 predictions + throttle).

---

## Architecture Diagram

```mermaid
flowchart LR
  Timer[Hourly systemd timer] --> CLI[prefetch-predictions CLI]
  CLI --> Engine[run_prefetch_cycle]
  Engine --> Agg[aggregate_all_competitions]
  Engine --> Priority[sort_fixtures_by_priority]
  Engine --> Fresh{needs generation?}
  Fresh -->|yes| Pipeline[run_and_store_prediction]
  Fresh -->|no| Skip[skip fresh]
  Pipeline --> Store[WorldcupPredictionStore]
  Engine --> Report[build_coverage_report]
  Report --> State[prefetch_scheduler_state.json]
  Report --> OwnerAPI[/api/owner/prefetch/coverage]
  OwnerAPI --> Dashboard[Owner Prefetch Coverage page]
  Store --> MatchCenter[Match Center cached summaries]
  Store --> Combo[Combo Tips readiness]
```

---

## Files Changed / Added

### Backend
- `worldcup_predictor/automation/prediction_prefetch/*` (new)
- `worldcup_predictor/config/settings.py` — prefetch settings
- `worldcup_predictor/database/repository.py` — `list_fixtures_in_kickoff_window`
- `worldcup_predictor/automation/worldcup_background/prediction_runner.py` — `_prefetch_signals` stamp
- `worldcup_predictor/api/routes/owner.py` — coverage + run-once endpoints
- `worldcup_predictor/cli/commands.py` + `main.py` — CLI command

### Frontend
- `base44-d/src/pages/owner/OwnerPrefetchCoveragePage.jsx`
- `base44-d/src/lib/ownerNavConfig.js`
- `base44-d/src/lib/comboGenerator.js` — `comboReadiness`
- `base44-d/src/pages/ComboTipsPage.jsx` — readiness per leg
- `base44-d/src/App.jsx` — route
- `base44-d/src/api/saasApi.js` — API helpers

### Ops
- `deployment/systemd/worldcup-prediction-prefetch.{service,timer}`
- `scripts/validate_phase_a14_prediction_prefetch.py`
- `scripts/run_phase_a14_prefetch.sh`
- `scripts/deploy_phase_a14_production.sh`
- `scripts/deploy_phase_a14_smoke.sh`

---

## Final Recommendation

| Area | Recommendation |
|------|----------------|
| **Prefetch engine** | **Shipped and operational.** Hourly timer will maintain WC coverage and backfill leagues as fixtures appear. |
| **Coverage monitoring** | Use `/owner/prefetch-coverage` weekly; alert if `missing > 0` for active competitions. |
| **Combo Tips** | Empty until engine produces non-`no_bet` picks — **not an A14 issue**. Track bettable % on dashboard. |
| **PL / domestic leagues** | When 2025/26 seasons resume, expect initial burst of missing predictions; timer will clear within ~N hours (`fixtures / max_per_cycle`). |
| **Cap tuning** | Consider raising `PREFETCH_MAX_PER_CYCLE` to 48 during high-volume windows if API quota allows. |
| **Next phase** | Address bettable pick rate in engine/calibration (out of A14 scope) OR run extended prefetch with `max_per_cycle=24` overnight to refresh remaining 6 stale WC rows. |

---

## STOP

Phase A14 complete. Report filed. No further action unless user requests follow-up (e.g. raise prefetch cap, combo engine work).
