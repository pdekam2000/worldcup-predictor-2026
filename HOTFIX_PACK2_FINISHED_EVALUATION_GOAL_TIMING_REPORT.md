# HOTFIX PACK 2 — Finished Evaluation + Goal Timing Report

**Date:** 2026-06-26  
**Status:** `FINISHED_EVALUATION_AND_GOAL_TIMING_FIXED`  
**Server:** `91.107.188.229` / https://footballpredictor.it.com

---

## Executive summary

Two trust-critical issues were fixed without modifying WDE, EGIE scoring math, prediction models, calibration, or billing.

| Issue | Root cause | Fix |
|-------|------------|-----|
| Finished matches not showing correct/wrong | **Evaluation scheduler broken** — repository methods `list_worldcup_stored_prediction_rows`, `get_worldcup_prediction_evaluation`, and `upsert_worldcup_prediction_evaluation` were missing from production `repository.py` | Restored repository methods; re-ran evaluation job |
| UI not showing evaluation on Match Detail / Match Center | Evaluation data only available via authenticated `/api/history`; predict payload had no eval block | Public `GET /api/matches/{id}/evaluation`; attach `match_evaluation` to predict payload + match center rows |
| Goal Timing dashboard mostly `0-15` | **Tie-break bug**: `max()` on uniform probabilities always picks first bucket `0-15`; missing DQ picks still stored/displayed range | Weighted-average tie-break; hide bucket when `no_prediction_flag`; expose `bucket_source` / `bucket_is_default` |
| EGIE picks endpoint 500 | PostgreSQL insert failures on duplicate fixture + NULL `hybrid_confidence_snapshot` JSON cast | Upsert-by-fixture in goal timing repository; safe JSON null; per-fixture error isolation |

---

## Part A — Finished match evaluation audit

### Root cause (critical)

`run_evaluate_worldcup_results()` called repository methods that **did not exist** on the deployed `FootballIntelligenceRepository`:

- `list_worldcup_stored_prediction_rows()` → scheduler never listed stored predictions
- `get_worldcup_prediction_evaluation()` → every per-fixture eval crashed
- `upsert_worldcup_prediction_evaluation()` → evaluations could not be persisted

**Result:** Auto-evaluation job failed silently on every cycle; finished matches stayed `pending` in archive/UI.

### Production re-evaluation (post-fix)

```
scanned: 56, evaluated: 0, updated: 4, skipped: 52, errors: 0
```

Evaluations table grew from broken state to **4 production rows** with full market columns. Further finished fixtures will evaluate automatically on subsequent scheduler runs.

---

## Part B — Auto-evaluate finished fixtures

- Script: `scripts/hotfix_pack2_re_evaluate_finished.py`
- Uses existing `evaluate_stored_prediction` + real `FixtureOutcomeResolver` scores only
- Markets persisted: 1X2, O/U, BTTS, DC, safe/value/aggressive picks, HT, correct score, first goal team, goalscorer, goal minute

---

## Part C — Green / red website display

| Layer | Change |
|-------|--------|
| API | `match_evaluation` block on cached predict payloads via `attach_match_evaluation()` |
| API | `GET /api/matches/{fixture_id}/evaluation` (public, no auth) |
| Match Center | Finished rows include `result_status`, `final_score`, `match_evaluation` |
| Match Detail | Loads public evaluation; merges into `displayData` |
| Markets UI | `PredictionMarketsPro` shows green/red/purple borders per `evaluationStatus` |
| Elite Match Card | CORRECT / WRONG / PARTIAL badge + score on finished matches |

---

## Part D — Goal Timing 0–15 audit

| Question | Finding |
|----------|---------|
| Is 0–15 real model output? | Sometimes yes when 16–30 has highest probability (~49%); often **no** |
| UI default? | Dashboard rendered `first_goal_time_range` raw — including placeholders |
| Backend default? | **`max(uniform_probs)` → always `0-15`** (first tuple index) |
| Missing data? | Low-DQ fixtures got `0-15` + `no_prediction_flag=true` simultaneously |
| EGIE 500? | PG insert error on re-predict + NULL hybrid JSON |

### Sample production pick (before fix)

```json
"first_goal_time_range": "0-15",
"hybrid_confidence": { "range": { "probability_bar": [
  {"bucket":"0-15","probability":0.2712},
  {"bucket":"16-30","probability":0.4925}
]}}
```

Model probabilities favored **16–30** but displayed bucket was **0–15** due to tie-break on blended priors.

---

## Part E — Goal Timing default fix

- New `goal_timing/bucket_selection.py` — weighted-average tie-break; flags `bucket_is_default`
- `no_prediction_flag` → `first_goal_time_range: null`, label **"Prediction unavailable"**
- API exposes: `bucket_source`, `bucket_is_default`, `bucket_reason`, `first_goal_time_range_label`
- Dashboard uses `formatGoalTimingBucket()` — never shows raw `0-15` for unavailable picks

---

## Part F — EGIE endpoint error

| Endpoint | Before | After |
|----------|--------|-------|
| `/api/goal-timing/picks` | Intermittent 500 | **200** |
| `/api/goal-timing/dashboard` | 200 | **200** |

Fixes: fixture-level upsert in `GoalTimingRepository.save_prediction()`, `hybrid_confidence_snapshot` null → `'null'` JSON, try/except per fixture in `list_today_picks()`.

---

## Files changed

**Backend**
- `worldcup_predictor/database/repository.py` — restored eval CRUD + list alias
- `worldcup_predictor/api/match_evaluation.py` — new
- `worldcup_predictor/api/display_helpers.py` — attach eval to predict
- `worldcup_predictor/api/match_center_aggregator.py` — finished row eval
- `worldcup_predictor/api/routes/matches.py` — public eval endpoint
- `worldcup_predictor/goal_timing/bucket_selection.py` — new
- `worldcup_predictor/goal_timing/models_stat/baseline.py`
- `worldcup_predictor/goal_timing/engine.py`
- `worldcup_predictor/goal_timing/models.py`
- `worldcup_predictor/goal_timing/prediction_service.py`
- `worldcup_predictor/goal_timing/storage/repository.py`
- `worldcup_predictor/api/routes/goal_timing.py`

**Frontend**
- `base44-d/src/api/worldcupApi.js`
- `base44-d/src/pages/MatchDetailPage.jsx`
- `base44-d/src/lib/predictionDetailProUtils.js`
- `base44-d/src/components/prediction-detail-pro/PredictionMarketsPro.jsx`
- `base44-d/src/components/prediction-detail-pro/PredictionHistorySection.jsx`
- `base44-d/src/components/match-center/EliteMatchCard.jsx`
- `base44-d/src/pages/goalTiming/GoalTimingDashboardPage.jsx`

**Scripts**
- `scripts/validate_hotfix_pack2_evaluation_goal_timing.py`
- `scripts/hotfix_pack2_re_evaluate_finished.py`
- `scripts/deploy_hotfix_pack2_production.sh`
- `scripts/_remote_deploy_hotfix_pack2.sh`

---

## Validation

Local + production: **12/12 PASS**

```
FINISHED_EVALUATION_AND_GOAL_TIMING_FIXED
```

---

## Production smoke (post-deploy)

| Check | HTTP |
|-------|------|
| `/api/goal-timing/picks?limit=3` | 200 |
| `/api/goal-timing/dashboard` | 200 |
| `/api/matches/1489409/evaluation` | 200 |
| `/archive` | 200 |
| `/accuracy` | 200 |

Backup: `/opt/worldcup-predictor/backups/hotfix-pack2-20260626-062931`

---

## Rollback plan

1. Restore SQLite: `cp backups/hotfix-pack2-*/football_intelligence.db data/`
2. Restore frontend: `tar xzf backups/hotfix-pack2-*/frontend_dist_pre.tar.gz -C /var/www/worldcup/frontend/`
3. `git checkout` pre-deploy commit from backup `commit.txt`
4. `systemctl restart worldcup-api && systemctl reload nginx`

---

## Untouched (per spec)

- WDE logic
- EGIE scoring math
- Prediction models / calibration
- Billing / subscriptions
