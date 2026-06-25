# PHASE 51F — EGIE Auto Evaluation Scheduler Report

**PHASE_51F_STATUS = PRODUCTION_ACTIVE**

**Date:** 2026-06-22  
**Server:** `91.107.188.229` / `https://footballpredictor.it.com`  
**App path:** `/opt/worldcup-predictor`

---

## Summary

Phase 51F installs a **systemd timer** that runs the EGIE goal-timing evaluation loop every **30 minutes** on production. Finished Premier League picks are refreshed, evaluated, and persisted to `goal_timing_evaluations` without manual intervention. The loop is **idempotent** — reruns skip unchanged evaluations.

---

## Deliverables

| Item | Path / unit |
|------|-------------|
| Service | `egie-goal-timing-evaluation.service` |
| Timer | `egie-goal-timing-evaluation.timer` |
| CLI entry | `main.py egie-goal-timing-evaluation` |
| Install script | `scripts/install_phase51f_egie_eval_timer.sh` |
| Deploy script | `scripts/deploy_phase51f_production.sh` |
| Smoke script | `scripts/deploy_phase51f_smoke.sh` |
| Validation | `scripts/validate_phase51f_egie_auto_evaluation.py` |

### Schedule

```
OnCalendar=*-*-* *:00,30:00
Persistent=true
RandomizedDelaySec=120
```

---

## Job behavior

Each run (`run_production_egie_goal_timing_evaluation`):

1. **Refresh** — `refresh_goal_timing_fixture_results()` for published picks past kickoff (API cap: 50)
2. **Evaluate** — `run_goal_timing_evaluations()` for finished fixtures
3. **Persist** — UPSERT into `goal_timing_evaluations` (unique on `prediction_id`)
4. **Stats** — `build_goal_timing_learning_stats()` (served by `/accuracy` and `/performance`)

### Logging (journald / stdout)

Structured `INFO` lines:

- `egie_goal_timing_evaluation_start`
- `goal_timing_result_refresh` — scanned, api_fetches, fixtures_updated, results_updated, outcomes_persisted, skipped_*, errors
- `goal_timing_evaluation_pass` — scanned, evaluated, updated, skipped_*, pending, errors
- `egie_goal_timing_evaluation_done`
- `egie_goal_timing_learning_stats sample_size=…`

Human-readable summary via CLI:

```
Phase 51F — EGIE goal timing auto evaluation
  Scanned picks: …
  Evaluated (new): …
  Skipped (unchanged): …
  …
```

---

## Deployment

### Backup

`/opt/worldcup-predictor/backups/deploy-phase51f-20260622-155322`

- Pre-deploy git commit: `a6053cda09439b24cc7554f47f74cc85d849ec74`
- SQLite snapshot: `football_intelligence.db`
- `.env.production` copy

### Hotfix during deploy

Production `FixtureOutcome` was missing extended fields (`first_goal_team`, `goal_events`). Deployed:

- `worldcup_predictor/api/prediction_history_evaluation.py`
- `worldcup_predictor/goal_timing/outcome_adapter.py` (defensive `getattr`)
- `worldcup_predictor/database/repository.py` — `update_fixture_outcome_detail()` for outcome persistence

### Timer status (post-deploy)

```
● egie-goal-timing-evaluation.timer — enabled, active (waiting)
NEXT: every :00 and :30 UTC (+ up to 120s jitter)
```

---

## Validation results

### Smoke (`deploy_phase51f_smoke.sh`) — **SMOKE_ALL_PASS**

| Check | Result |
|-------|--------|
| Timer enabled | PASS |
| Timer active | PASS |
| Manual job runs | PASS |
| Idempotent skip on rerun | PASS |
| No duplicate evaluations (count stable at 1) | PASS |
| `GET /api/goal-timing/history` | 200 |
| `GET /api/goal-timing/accuracy` | 200 |
| `GET /api/goal-timing/performance` | 200 |
| `GET /api/goal-timing/dashboard` | 200 |
| `GET /api/health` | 200 |

### First production evaluation

| Field | Value |
|-------|-------|
| Fixture | Sheffield Utd vs Tottenham (`1035553`) |
| First goal team | correct |
| Goal range | correct |
| Goal minute | partial |
| Sample size | 1 |

### Idempotency

Second and third manual runs: `Skipped (unchanged): 1`, evaluation count remained **1**.

### Upcoming picks

**48** picks skipped as `not finished` (2026/27 PL season) — expected until matches complete.

---

## API smoke (production)

```json
// GET /api/goal-timing/accuracy
{"sample_size":1,"overall":{"first_goal_team_winrate":1.0,"goal_range_winrate":1.0,...}}
```

```json
// GET /api/goal-timing/history — 1 item (Sheffield Utd vs Tottenham)
```

---

## Operator commands

```bash
# Manual run
sudo -u www-data bash -lc 'cd /opt/worldcup-predictor && set -a && source .env.production && set +a && .venv/bin/python main.py egie-goal-timing-evaluation'

# Timer status
systemctl status egie-goal-timing-evaluation.timer
systemctl list-timers egie-goal-timing-evaluation.timer

# Logs
journalctl -u egie-goal-timing-evaluation.service -f

# Rollback
sudo systemctl disable --now egie-goal-timing-evaluation.timer
sudo rm /etc/systemd/system/egie-goal-timing-evaluation.{service,timer}
sudo systemctl daemon-reload
```

---

## What was NOT changed

- Goal timing **prediction engine** (`engine.py`)
- DQ threshold (`MIN_DATA_QUALITY_FOR_PREDICTION`)
- Model weights / retrain pipelines
- World Cup `worldcup-evaluate-results` timer (runs in parallel, separate scope)

---

## Files added / modified (repo)

**New**

- `deployment/systemd/egie-goal-timing-evaluation.service`
- `deployment/systemd/egie-goal-timing-evaluation.timer`
- `worldcup_predictor/goal_timing/auto_evaluation_job.py`
- `scripts/install_phase51f_egie_eval_timer.sh`
- `scripts/deploy_phase51f_production.sh`
- `scripts/deploy_phase51f_smoke.sh`
- `scripts/pack_phase51f_deploy.sh`
- `scripts/validate_phase51f_egie_auto_evaluation.py`

**Modified**

- `main.py` — `egie-goal-timing-evaluation` command
- `worldcup_predictor/cli/commands.py` — `run_egie_goal_timing_auto_evaluation_command`
- `worldcup_predictor/goal_timing/evaluation_job.py` — pass logging
- `worldcup_predictor/goal_timing/result_refresh.py` — pass logging
- `worldcup_predictor/database/repository.py` — `update_fixture_outcome_detail`
- `worldcup_predictor/goal_timing/outcome_adapter.py` — defensive outcome fields

---

**PHASE_51F_STATUS = PRODUCTION_ACTIVE**
