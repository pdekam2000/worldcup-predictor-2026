# IMPLEMENT-1 — Existing Pipeline Commands Audit

**Phase:** IMPLEMENT-1 Part A  
**Date:** 2026-07-02

---

## Summary

The production master runner (`scripts/run_production_prediction_pipeline.py`) composes these existing commands. **No WDE formula changes.** Shadow paths remain owner-only.

---

## Core owner daily pipeline

| Command | Purpose | Status | Prod safe? | API risk | DB write | Schedule |
|---------|---------|--------|------------|----------|----------|----------|
| `scripts/run_daily_owner_prediction_cycle.py` | Full cycle: result sync, discovery, odds, predictions, reports | EXISTS | **Yes** (with quotas) | Medium (bounded) | Yes | Daily 06:00 Vienna |
| `scripts/owner_daily_predictions.py` | Same cycle via CLI wrapper | EXISTS | Yes | Medium | Yes | On demand |
| `scripts/run_owner_daily_prediction_and_eval.py` | Today predictions report + yesterday eval | EXISTS | **Yes** | Low (cache-first) | Read + eval writes | After daily predict |
| `scripts/evaluate_owner_yesterday_predictions.py` | Yesterday-only evaluation | EXISTS | Yes | Low | Eval writes | Daily evening |
| `scripts/build_owner_daily_control_panel.py` | Owner control panel markdown/json | EXISTS | Yes | None | Read-only | After daily predict |
| `scripts/run_owner_daily_full_refresh.py` | Full refresh + validation + panel | EXISTS | Caution (heavy) | High if forced | Yes | Manual only |
| `scripts/validate_owner_daily_prediction_and_eval.py` | Validator for owner daily | EXISTS | Yes | None | Read-only | After runs |

---

## Fixture discovery & sync

| Command | Purpose | Status | Prod safe? | API risk | DB write | Schedule |
|---------|---------|--------|------------|----------|----------|----------|
| `worldcup_predictor/owner_daily/fixture_discovery.py` | Discover fixtures (SQLite first, API fallback) | EXISTS | Yes | Medium | Upsert fixtures | Via daily cycle |
| `scripts/owner_find_today_fixtures.py` | CLI fixture finder | EXISTS | Yes | Medium | Yes | Manual |
| `scripts/import_daily_odds.py` | Daily odds import | EXISTS | Yes | Medium | odds_snapshots | Via cycle |
| `scripts/sync_ecse_snapshot_results.py` | ECSE snapshot result sync | EXISTS | Yes | Low | fixture_results | Hourly/daily |
| `main.py worldcup-refresh-results` | WC stored prediction result refresh | EXISTS | Yes | Low-Med | fixture_results | Hourly |

---

## Prediction storage

| Command | Purpose | Status | Prod safe? | API risk | DB write | Schedule |
|---------|---------|--------|------------|----------|----------|----------|
| `worldcup_predictor/owner_daily/predictions.py` | WDE + ECSE daily predictions → `worldcup_stored_predictions` | EXISTS | **Yes** | Via PredictPipeline | Yes (skip existing) | Daily |
| `main.py daily-worldcup-predict` | WC background predictions | EXISTS | Yes | Medium | Yes | Optional 06:00 UTC |
| `main.py predops-run` | Multi-comp prefetch | EXISTS | Caution | High | Yes | Hourly opt-in |

---

## Result sync & evaluation

| Command | Purpose | Status | Prod safe? | API risk | DB write | Schedule |
|---------|---------|--------|------------|----------|----------|----------|
| `worldcup_predictor/owner_daily/result_sync.py` | ECSE sync + WDE/ECSE eval | EXISTS | **Yes** | Low | Evaluations | Hourly |
| `main.py worldcup-auto-evaluation` | Refresh + quarantine + evaluate stored preds | EXISTS | **Yes** | Low | Evaluations | Every 30 min |
| `scripts/evaluate_owner_knockout_predictions.py` | Knockout WDE/ECSE/manual eval | EXISTS | Yes | Low | Eval jsonl | Manual |
| `scripts/validate_ecse_snapshot_result_sync.py` | ECSE sync validator | EXISTS | Yes | None | Read-only | CI |

---

## OddAlerts / ECSE shadow (owner-only)

| Command | Purpose | Status | Prod safe? | API risk | DB write | Schedule |
|---------|---------|--------|------------|----------|----------|----------|
| `scripts/run_daily_oddalerts_ecse_owner_pipeline.py` | Gmail/CSV/monitor shadow pipeline | EXISTS | Yes (shadow) | Low | Shadow tables | Daily optional |
| `scripts/validate_daily_oddalerts_ecse_owner_pipeline.py` | Validator | EXISTS | Yes | None | Read-only | After run |
| `scripts/validate_ecse_oddalerts_owner_lab.py` | Owner lab validator | EXISTS | Yes | None | Read-only | CI |

---

## Learning / adaptive / performance

| Command | Purpose | Status | Prod safe? | API risk | DB write | Schedule |
|---------|---------|--------|------------|----------|----------|----------|
| `worldcup_predictor/learning/learning_capture.py` | Capture at predict time | EXISTS | Yes | None | learning_records_v2 | Automatic |
| `worldcup_predictor/learning/self_learning_engine_v2.py` | Advisory learning report | EXISTS | **Yes** | None | Read-only | Daily |
| `worldcup_predictor/adaptive_confidence/engine.py` | Confidence adjustment in scoring | EXISTS | Yes (in-path) | None | None | Automatic |
| `main.py egie-goal-timing-evaluation` | EGIE goal timing eval | EXISTS | Yes | Low | Eval rows | 30 min opt-in |
| `/api/owner/performance-center` | Owner performance UI | EXISTS | Yes | None | Read-only | Always |

---

## Archive / history

| Command | Purpose | Status | Prod safe? | API risk | DB write | Schedule |
|---------|---------|--------|------------|----------|----------|----------|
| `worldcup_predictor/automation/worldcup_background/auto_evaluation_job.py` | Production auto eval + summary rebuild | EXISTS | Yes | Low | Eval + summary | Hourly |
| `worldcup_predictor/api/archive_evaluation_join.py` | Archive status join | EXISTS | Yes | None | Read-only | API |

---

## Existing systemd (not enabled by default)

| Unit | Calls | Schedule |
|------|-------|----------|
| `worldcup-evaluate-results.timer` | `main.py worldcup-auto-evaluation` | Every 30 min |
| `worldcup-daily-predict.timer` | `main.py daily-worldcup-predict` | 06:00 UTC (plan only) |
| `worldcup-auto-cycle.timer` | `main.py worldcup-auto-cycle` | 6× daily (plan only) |

---

## New IMPLEMENT-1 master runner

| Command | Purpose |
|---------|---------|
| `scripts/run_production_prediction_pipeline.py` | Unified production runner with lock, modes, reports |
| `scripts/validate_implement_1_production_pipeline.py` | IMPLEMENT-1 validation suite |
| `deployment/systemd/worldcup-prediction-daily.*` | Daily predict timer (not enabled) |
| `deployment/systemd/worldcup-results-hourly.*` | Hourly eval timer (not enabled) |

---

## Master runner mode mapping

| Mode | Steps executed |
|------|----------------|
| `daily` | Today cycle + tomorrow predictions + results/eval + owner eval + control panel + learning + shadow monitor |
| `hourly` | Results sync + WC auto eval + owner eval |
| `results-only` | Same as hourly |
| `predictions-only` | Discovery + predictions only (no result sync) |
| `eval-only` | Results + eval + owner eval |
| `--dry-run` | All steps with `no_provider_calls` / dry flags — no DB writes |

---

*Composed into IMPLEMENT-1 master runner — no replacement of underlying engines.*
