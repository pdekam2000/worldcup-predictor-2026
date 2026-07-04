# FULL AUTO PIPELINE AUDIT REPORT

**Phase:** PROJECT-RECOVERY — Part D  
**Date:** 2026-07-02  
**Mode:** Read-only architecture audit

---

## Goal vs current state

| # | Desired behavior | Status | Notes |
|---|------------------|--------|-------|
| 1 | Discover all eligible matches | **PARTIAL** | Owner daily + autonomous discovery exist; not one unified scheduler |
| 2 | Predict all upcoming matches | **PARTIAL** | WC background + owner daily + prefetch; manual triggers |
| 3 | Store every prediction | **EXISTS** | `worldcup_stored_predictions` + ECSE snapshots |
| 4 | Fetch real result after finish | **EXISTS** | `result_refresh.py`, ECSE result sync, API-Football |
| 5 | Compare prediction vs actual | **EXISTS** | auto_eval, yesterday_eval, knockout_eval |
| 6 | Store evaluation hit/miss | **EXISTS** | `worldcup_prediction_evaluations` |
| 7 | Archive / performance dashboard | **EXISTS** | Owner UI + admin accuracy API |
| 8 | Learning / model improvement | **PARTIAL** | Capture + advisory analytics; **no auto retrain/promote** |

**Self-improving loop verdict:** Predict → store → evaluate **works**. Adapt (confidence) **partial**. Retrain/promote **missing**.

---

## 1. Match discovery & fixture sync

| Component | Path | Status |
|-----------|------|--------|
| Owner fixture discovery | `worldcup_predictor/owner_daily/fixture_discovery.py` | EXISTS |
| Owner predict/eval discovery | `worldcup_predictor/owner_predict_eval/fixture_discovery.py` | EXISTS |
| Autonomous discovery | `worldcup_predictor/autonomous/fixture_discovery.py` | EXISTS |
| European feed import | `worldcup_predictor/data_import/european_fixture_feed.py` | EXISTS |
| CLI | `scripts/owner_find_today_fixtures.py`, `scripts/run_daily_owner_prediction_cycle.py` | EXISTS |

**Competitions (owner daily):** `world_cup_2026`, `champions_league`, `europa_league`, `conference_league`, `premier_league`, `bundesliga`

**Gap:** No systemd timer for owner discovery; WC background assumes fixtures already in DB.

---

## 2. Daily prediction jobs

| Pipeline | Entry | Storage | Scheduled? |
|----------|-------|---------|------------|
| Owner daily (generates) | `scripts/owner_daily_predictions.py`, `run_daily_owner_prediction_cycle.py` | `worldcup_stored_predictions` (`source=owner_daily_predictions`) | **Manual/cron only** |
| Owner predict/eval (report) | `scripts/run_owner_daily_prediction_and_eval.py` | Reads DB | Manual |
| WC background | `main.py daily-worldcup-predict` | `worldcup_stored_predictions` (`source=background`) | Timer exists, **not enabled** |
| Prematch | `main.py auto-prematch` | `PredictionHistoryStore` (separate) | Manual |
| Prefetch | `main.py predops-run` | Stored predictions | Hourly timer, opt-in |
| Autonomous Phase 61 | `main.py autonomous_once` | Autonomous store | Hourly timer, **disabled** |

**Gap:** Three parallel orchestrators; owner daily not on production cron.

---

## 3. Stored predictions

| Item | Status |
|------|--------|
| Schema | `worldcup_predictor/database/migrations.py` (Phase 33/44) |
| Repository | `worldcup_predictor/database/repository.py` |
| Store layer | `worldcup_predictor/automation/worldcup_background/prediction_store.py` |
| Owner writes | `worldcup_predictor/owner_daily/predictions.py` |
| API read | `worldcup_predictor/api/routes/matches.py` |
| Production count | **48 rows** |
| Local count | **185 rows** |

---

## 4. Result sync

| Component | Path | Status |
|-----------|------|--------|
| Core refresh | `worldcup_predictor/automation/worldcup_background/result_refresh.py` | EXISTS |
| Auto-eval integration | `auto_evaluation_job.py` calls refresh first | EXISTS |
| Owner ECSE sync | `worldcup_predictor/owner_daily/result_sync.py` | EXISTS |
| CLI | `main.py worldcup-refresh-results` | EXISTS |

**Gap:** Result sync not continuous on production unless eval timer installed.

---

## 5. Evaluation engines

| Engine | Script / CLI | Auto? | Production use |
|--------|--------------|-------|----------------|
| WC auto evaluation | `main.py worldcup-auto-evaluation` | Opt-in timer | Not confirmed enabled |
| Owner yesterday eval | `run_owner_daily_prediction_and_eval.py` | Manual | Validators pass |
| Knockout eval | `evaluate_owner_knockout_predictions.py` | Manual | Needs artifact on server |
| ECSE OddAlerts shadow eval | shadow pipeline scripts | Manual | Local only (197 preds) |
| EGIE goal timing | `main.py egie-goal-timing-evaluation` | Opt-in timer | Separate market |

**Known issue:** Eval reports show `WAITING_FOR_RESULT` when DB/API not refreshed (e.g. USA 2-0 was correct in API cache but not in local DB eval).

---

## 6. Learning loops

| Component | Path | Auto-improve? |
|-----------|------|---------------|
| Learning capture | `worldcup_predictor/learning/learning_capture.py` | Writes `learning_records_v2` |
| Self-learning v2 | `worldcup_predictor/learning/self_learning_engine_v2.py` | **Advisory only** |
| Adaptive confidence | `worldcup_predictor/adaptive_confidence/engine.py` | Adjusts scoring confidence |
| Model coach | `worldcup_predictor/learning/model_coach_agent.py` | Recommendations only |
| Elite shadow learning | `elite_self_learning/learning_store.py` | Shadow JSONL only |
| WDE/EGIE retrain | — | **Explicitly disabled** (`WDE_RETRAINED: False`) |

---

## 7. Scheduled jobs (`deployment/systemd/`)

| Unit | Schedule | Default |
|------|----------|---------|
| `worldcup-api.service` | always | **ACTIVE** |
| `worldcup-evaluate-results.timer` | 30 min | Opt-in (`install_phase44a_eval_timer.sh`) |
| `worldcup-daily-predict.timer` | 06:00 UTC | **Not enabled** |
| `worldcup-auto-cycle.timer` | 6× daily | **Not enabled** |
| `worldcup-prediction-prefetch.timer` | hourly | Manual enable |
| `worldcup-autonomous.timer` | hourly | Disabled |
| `egie-goal-timing-evaluation.timer` | 30 min | Opt-in |

**Missing systemd units for:**
- `run_daily_owner_prediction_cycle.py`
- `run_owner_daily_prediction_and_eval.py`
- `evaluate_owner_knockout_predictions.py`

---

## 8. Owner dashboard / UI

**API:** `worldcup_predictor/api/routes/owner.py` — overview, monitoring, performance-center, health-dashboard, research-lab, promotion/status, ECSE shadow lab

**Frontend:** `base44-d/src/pages/owner/*` — Command Center, Performance, Model Center, ECSE panels

**Gap:** No one-click “run owner daily cycle” in UI; scheduler toggle targets autonomous timer, not owner daily.

---

## Coverage by provider / competition

| Scope | Covered? | How |
|-------|----------|-----|
| World Cup 2026 | **Yes** | Owner daily, WC background, ECSE live |
| UCL / UEL / UECL | **Yes** | Owner daily competitions list |
| Premier League / Bundesliga | **Yes** | Owner daily + OddAlerts shadow (local) |
| API-Football fixtures/results | **Yes** | Primary provider |
| Sportmonks enrichment | **Yes** | Dumps + enrichment tables |
| OddAlerts ECSE shadow | **Partial** | Local research; prod table empty |
| All eligible matches automatically | **No** | Requires manual/cron owner cycle |

---

## What is missing for full self-improving loop

1. **Unified production scheduler** — owner daily predict + result sync + eval on timer  
2. **Continuous result refresh** — enable `worldcup-evaluate-results.timer` or equivalent  
3. **Prediction coverage** — run owner cycle on production so all eligible fixtures get stored preds  
4. **Eval artifact sync** — knockout/manual artifacts on server path  
5. **Closed learning loop** — retrain/promotion gates remain manual by design  
6. **DB parity** — production missing local shadow/research rows (optional import)

---

## Recommendation (Part D)

**NEED_PIPELINE_IMPLEMENTATION** — code exists; production automation and eval refresh are not fully wired.

---

*See also: `DAILY_OWNER_PREDICTION_CYCLE_REPORT.md`, `CODEBASE_CONSOLIDATION_2_DEPLOY_REPORT.md`*
