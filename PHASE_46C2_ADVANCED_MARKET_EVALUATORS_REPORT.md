# Phase 46C-2 — Advanced Market Evaluators Report

**Status:** `PHASE_46C2_STATUS = PRODUCTION_ACTIVE`  
**Date:** 2026-06-21  
**Scope:** HT Result, Correct Score, First Goal Team, Goalscorer (Goal Minute deferred to 46C-3)

---

## Summary

Phase 46C-2 extends evaluation logic only — no changes to the prediction engine, WDE, stored prediction payloads, or core 1X2/O/U/BTTS/DC evaluators. Four advanced markets are evaluated against Phase 46C-1 persisted outcomes and surfaced in evaluation detail, history archive, and Performance Center (when real settled samples exist).

---

## Implementation

### New module

`worldcup_predictor/automation/worldcup_background/advanced_market_evaluator.py`

| Market | Input (prediction) | Input (outcome) | Missing data policy |
|--------|-------------------|-----------------|---------------------|
| HT Result | `detailed_markets.halftime.selection` / probabilities | `ht_result`, `ht_home_goals`, `ht_away_goals` | `unavailable` |
| Correct Score | Top-1 `detailed_markets.correct_scores` | `final_score`, `match_outcome_type` | Postponed/cancelled → `unavailable`; AET/PEN noted in reason |
| First Goal Team | `detailed_markets.first_goal.team` | `first_goal_team`, goal events | 0-0 + explicit no-goal pick → `correct`; missing outcome with goals → `unavailable` |
| Goalscorer | `detailed_markets.goalscorer.player` | `first_goal_player`, events | Own goal → `unavailable`; low identity confidence → `unavailable` |

Each market returns: `market`, `predicted`, `actual`, `status`, `confidence`, `reason`.

### Wiring

- `pick_evaluator.py` — calls advanced evaluators; adds `advanced_markets` + status keys to evaluation payload
- `result_evaluation_job.py` — re-evaluates when advanced columns/detail missing
- `repository.py` — persists `market_ht_status`, `market_cs_status`, `market_fg_team_status`, `market_goalscorer_status`
- `migrations.py` — `PHASE46C2_EVAL_COLUMNS`
- `accuracy_summary.py` — aggregates advanced market winrates
- `performance_center.py` — includes advanced markets only when `total > 0` (n&lt;20 → `reliability_level: low`)
- `prediction_archive_detail.py` — HT / Correct Score rows + eval status on First Goal / Goalscorer
- Frontend: `PredictionHistoryDetailPage.jsx` (unavailable styling), `AccuracyCenter.jsx` (insufficient data when n&lt;20)

---

## Validation

Script: `scripts/validate_phase46c2_advanced_market_evaluators.py`

**Result: 22/22 PASS** (local + production)

Covers: HT correct/wrong, correct score exact/mismatch, first goal correct/wrong/0-0, goalscorer match/missing/own goal, postponed unavailable, existing core markets unchanged, no WDE/scoring engine imports, performance summary without fake advanced rows.

---

## Production smoke (4 finished fixtures)

After deploy + re-evaluation (`skip_unchanged=False`):

| Fixture | HT | Correct Score | First Goal | Goalscorer |
|---------|-----|---------------|------------|------------|
| 1489369 | unavailable | unavailable | unavailable | unavailable |
| 1489370 | unavailable | **wrong** (pred 1-0, actual 4-1) | unavailable | unavailable |
| 1538999 | unavailable | unavailable | unavailable | unavailable |
| 1539000 | unavailable | **correct** (pred 1-1, actual 1-1) | unavailable | unavailable |

**Notes:**

- Legacy-import payloads often lack `halftime` / `goalscorer` blocks → HT/goalscorer `unavailable` (not wrong).
- First goal / goalscorer outcomes not present on all four fixtures in SQLite at eval time → `unavailable` per policy.
- Correct score shows real settled evaluations where legacy scoreline predictions exist.

---

## Hotfix during deploy

Fixed first-goal logic that incorrectly treated “missing first goal outcome + goals scored” as a 0-0 no-goal match (would have marked `wrong`). Now correctly returns `unavailable` with `first_goal_outcome_missing`.

---

## Files added/changed

| Path | Change |
|------|--------|
| `worldcup_predictor/automation/worldcup_background/advanced_market_evaluator.py` | **NEW** |
| `worldcup_predictor/automation/worldcup_background/pick_evaluator.py` | extended |
| `worldcup_predictor/automation/worldcup_background/result_evaluation_job.py` | re-eval trigger |
| `worldcup_predictor/automation/worldcup_background/accuracy_summary.py` | advanced stats |
| `worldcup_predictor/api/performance_center.py` | market defs |
| `worldcup_predictor/api/prediction_archive_detail.py` | UI payload |
| `worldcup_predictor/database/migrations.py` | eval columns |
| `worldcup_predictor/database/repository.py` | upsert columns |
| `scripts/validate_phase46c2_advanced_market_evaluators.py` | **NEW** |
| `scripts/phase46c2_post_deploy.py` | **NEW** |
| `scripts/phase46c2_production_smoke.py` | **NEW** |
| `scripts/deploy_phase46c2_production.sh` | **NEW** |
| `base44-d/src/pages/PredictionHistoryDetailPage.jsx` | unavailable UI |
| `base44-d/src/pages/AccuracyCenter.jsx` | n&lt;20 handling |

---

## Next phase

**Phase 46C-3** — Goal Minute evaluator with tolerance/band policy.
