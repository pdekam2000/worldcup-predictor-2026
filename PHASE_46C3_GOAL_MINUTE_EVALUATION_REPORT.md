# Phase 46C-3 — Goal Minute Evaluation Report

**Status:** `PHASE_46C3_STATUS = PRODUCTION_ACTIVE`  
**Date:** 2026-06-21  
**Scope:** Goal Minute market evaluation using Phase 46C-1 persisted `first_goal_minute` / goal events

---

## Summary

Goal Minute evaluation is now part of the advanced evaluation pipeline. No changes were made to the prediction engine, WDE, stored prediction payloads, or core 1X2/O/U/BTTS/DC evaluators. Phase 46C-2 markets (HT, Correct Score, First Goal Team, Goalscorer) remain unchanged.

---

## Evaluation policy

### Minute band prediction

Standard bands (via `market_consistency_timing.py`):

| Band | Range |
|------|-------|
| 0-15 | 0–15 |
| 16-30 | 16–30 |
| 31-45 | 31–45 |
| 46-60 | 46–60 |
| 61-75 | 61–75 |
| 76-90+ | 76+ (includes stoppage/ET normalized to 90) |

- **Correct** if effective first-goal minute falls inside predicted band  
- **Wrong** if outside  
- **Unavailable** if no goal and prediction does not explicitly say no goal

Band takes priority when `detailed_markets.first_goal.minute_range` is a valid band.

### Exact minute prediction

When only `expected_minute` is set (or range is a bare integer):

- Default tolerance: **±5 minutes**
- **Correct** if `|actual − predicted| ≤ 5`
- **Wrong** if outside tolerance

### Stoppage time policy

| Raw event | Effective minute | Band effect |
|-----------|------------------|-------------|
| 45+N (first-half stoppage) | 45 | Counts in 31–45 |
| 90+N (second-half stoppage) | 90 | Counts in 76–90+ |
| Minute > 90 (extra time) | 90 | Counts in 76–90+ |

Reason field documents normalization: `stoppage_normalized:45->45` etc.

### No-goal matches (0-0)

- Actual first goal minute = null  
- Market **unavailable** unless prediction explicitly supports no goal (`no_goal` token) → **correct**

### Missing data

- Missing `first_goal_minute` → **unavailable**, not wrong  
- Missing prediction → **unavailable**

---

## Implementation

| Component | Change |
|-----------|--------|
| `goal_minute_evaluator.py` | **NEW** — band/exact/stoppage/no-goal logic |
| `advanced_market_evaluator.py` | wires `goal_minute` into `evaluate_advanced_markets` |
| `migrations.py` | `PHASE46C3_EVAL_COLUMNS` |
| `repository.py` | `market_goal_minute_status`, `market_goal_minute_actual`, `market_goal_minute_predicted` |
| `accuracy_summary.py` | `market_goal_minute` stats |
| `performance_center.py` | Goal Minute in breakdown (only when total > 0) |
| `prediction_archive_detail.py` | Goal Minute row with eval status/colors |
| `result_evaluation_job.py` | Re-eval when `market_goal_minute_status` missing |

---

## Validation

Script: `scripts/validate_phase46c3_goal_minute_evaluation.py`

**Result: 23/23 PASS** (local + production)

Tests cover: band correct/wrong, exact ±5, 0-0 unavailable, missing minute unavailable, stoppage 45+/90+, HT/CS/FG/GS unchanged, core markets unchanged, no WDE/scoring engine, DB persistence, Performance Center real samples only.

---

## Production notes

After deploy, 4 finished fixtures re-evaluated. Most legacy imports lack `minute_range` on `first_goal` → **unavailable** (not wrong). Evaluations appear in history detail as Goal Minute rows with gray/yellow unavailable styling.

Performance Center shows Goal Minute only when settled samples exist; n < 20 → `reliability_level: low` / “Insufficient data” in UI.

---

## Files

- `worldcup_predictor/automation/worldcup_background/goal_minute_evaluator.py`
- `scripts/validate_phase46c3_goal_minute_evaluation.py`
- `scripts/phase46c3_post_deploy.py`
- `scripts/phase46c3_production_smoke.py`
- `scripts/deploy_phase46c3_production.sh`
