# Phase 46C-1 — Outcome Persistence Foundation

**Date:** 2026-06-21  
**Status:** COMPLETE — validated locally (21/21), deployed to production  
**Production:** `91.107.188.229` / https://footballpredictor.it.com

---

## Executive summary

Built the outcome storage layer required for Phase 46C advanced market evaluation. Halftime scores, normalized goal events, first-goal outcomes, and match outcome metadata (FT/AET/PEN/etc.) are now persisted idempotently and exposed through `FixtureOutcomeResolver`.

| Environment | Finished fixtures | HT persisted | Goal events | First goal | `outcome_persisted_at` |
|-------------|------------------:|-------------:|------------:|-----------:|------------------------:|
| **Production (after backfill)** | 4 | **4** | **4** | **4** | **4** |
| Local validation DB | 2 | 2 | 2 | 2 | 2 |

Remaining 52 archive rows are **not yet finished** — outcome sync runs automatically when matches complete via existing `worldcup-refresh-results` / auto-evaluation cycle.

---

## What was built

### 1. Schema (Phase 46C-1 migration)

**Extended `fixture_results`:**

| Column | Purpose |
|--------|---------|
| `ht_home_goals` / `ht_away_goals` | Halftime score integers |
| `ht_result` | `home_win` / `draw` / `away_win` |
| `first_goal_team` / `first_goal_player` | First countable goal |
| `first_goal_minute` / `first_goal_extra_minute` | First goal timing |
| `match_outcome_type` | `FT`, `AET`, `PEN`, `CANCELLED`, `ABANDONED`, … |
| `outcome_persisted_at` | Idempotency marker |
| `outcome_source` | e.g. `api-football` |

**New table `fixture_goal_events`:**

| Column | Purpose |
|--------|---------|
| `minute`, `extra_minute` | Event time |
| `team`, `team_id`, `player`, `assist` | Attribution |
| `is_penalty`, `is_own_goal` | Flags from API `detail` |
| `detail` | Raw detail string |
| `sort_index` | Stable ordering |

### 2. Outcomes module

| File | Role |
|------|------|
| `worldcup_predictor/outcomes/models.py` | `GoalEvent`, `ParsedFixtureOutcome` |
| `worldcup_predictor/outcomes/event_parser.py` | Parse API-Football events; skip missed penalties |
| `worldcup_predictor/outcomes/outcome_persistence.py` | Build + persist; backfill detection |

### 3. Extended `FixtureOutcome`

`FixtureOutcome` now includes (optional, backward compatible):

- `ht_score`, `ht_result`, `ht_home_goals`, `ht_away_goals`
- `first_goal_team`, `first_goal_player`, `first_goal_minute`, `first_goal_extra_minute`
- `match_outcome_type`
- `goal_events` (tuple of dicts)

Resolver loads from `fixture_results` + `fixture_goal_events`.

### 4. Refresh / backfill integration

| Function | Behavior |
|----------|----------|
| `refresh_stored_prediction_results()` | On finished fixtures: persist outcomes after result upsert; re-fetch when `needs_outcome_backfill()` |
| `backfill_stored_prediction_outcomes()` | Scan **all** archive rows with finished results; force API sync |

**Quota/cache safety:**

- Reuses existing `ApiFootballClient` TTL cache
- Events fetched only when outcome detail incomplete
- `outcome_persisted_at` prevents repeat event API calls
- Idempotent `DELETE` + `INSERT` for goal events

---

## Validation

### Local automated

Script: `scripts/validate_phase46c1_outcome_persistence.py`  
Result: **21/21 PASS**  
Artifact: `artifacts/phase46c1_outcome_persistence_validation.json`

Covers: event parsing (penalty/OG/missed penalty), HT result, first goal, AET metadata, resolver exposure, idempotent replace, **existing 1X2 eval unchanged**.

### Production backfill

```
Scanned: 56
API fixture fetches: 4
API event fetches: 4
Outcomes persisted: 4
Errors: 0
```

Smoke: `artifacts/phase46c1_production_smoke.json`

---

## Compatibility

| System | Impact |
|--------|--------|
| WDE / prediction engine | **None** — no changes |
| `pick_evaluator.py` | **None** — 1X2/O/U/BTTS/DC unchanged |
| `FixtureOutcome` consumers | **Backward compatible** — new fields default empty |
| Performance Center | **None** until 46C-2 evaluators wired |
| History / archive | **Read-only extension** |

---

## Production deploy

Backup: `/opt/worldcup-predictor/backups/deploy-phase46c1-20260621-201040`

Post-deploy backfill (second patch): 4 finished fixtures fully populated with HT + events + first goal.

---

## Sample persisted outcome (production pattern)

For each finished fixture with goals, stored data includes:

- `ht_score`: e.g. `1-0`
- `ht_result`: e.g. `home_win`
- `first_goal_team`, `first_goal_player`, `first_goal_minute`
- `fixture_goal_events`: ordered rows with penalty/own_goal flags
- `match_outcome_type`: `FT` or `AET`

---

## Next step: Phase 46C-2

Wire advanced evaluators in `pick_evaluator.py` using resolver fields:

- HT 1X2 from `ht_result`
- Correct score from `final_score`
- First goal team / scorer / minute from persisted outcome
- New DB columns on `worldcup_prediction_evaluations`

---

## Key files

| Path |
|------|
| `worldcup_predictor/outcomes/` |
| `worldcup_predictor/database/migrations.py` (PHASE46C1_*) |
| `worldcup_predictor/database/repository.py` |
| `worldcup_predictor/api/prediction_history_evaluation.py` |
| `worldcup_predictor/automation/worldcup_background/result_refresh.py` |
| `scripts/validate_phase46c1_outcome_persistence.py` |
| `scripts/phase46c1_post_deploy.py` |
| `scripts/deploy_phase46c1_production.sh` |
