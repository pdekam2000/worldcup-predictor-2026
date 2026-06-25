# HOTFIX — Archive Status Evaluation Join Report

**Status:** PRODUCTION_ACTIVE  
**Date:** 2026-06-22

## Root cause

Archive list rows and detail pages used **two different status sources** than Performance Center:

| Surface | Status source (before) |
|---------|------------------------|
| **Performance Center** | `worldcup_prediction_evaluations` (production auto-eval, quarantine-safe) |
| **Archive list (`scope=all`)** | Merged rows where **personal history** (`evaluate_history_record` → `FixtureOutcomeResolver`) **overrode** global archive rows with `pending` |
| **Archive detail** | On-the-fly `evaluate_stored_prediction()` + resolver — **ignored** persisted evaluation table when match results store was incomplete |

When a user had viewed a match (personal history row) but the live results resolver still returned `pending`, the merged `scope=all` view showed **Pending** even though `worldcup_prediction_evaluations` had `correct`/`wrong` — matching the reported symptom (Performance Center correct, Archive all pending).

Production DB at diagnosis: **55 archive rows**, **4 evaluations** (3 correct, 1 wrong) — backend list join worked for `scope=global` but merge could mask it for `scope=all`.

## Fix

New module: `worldcup_predictor/api/archive_evaluation_join.py`

- Joins `worldcup_prediction_evaluations` by `fixture_id`
- Excludes quarantined evaluations (Phase 45B)
- Main card status follows **1X2 evaluation** when available; `partial` only when 1X2 unsettled but other markets disagree
- Attaches `evaluated_markets_count`, `correct_markets_count`, `wrong_markets_count`, `pending_markets_count`, `row_status_reason`

### Files changed

| File | Change |
|------|--------|
| `archive_evaluation_join.py` | **New** shared join logic |
| `global_prediction_archive.py` | Evaluation-enriched rows; smart merge; stats include `partial` |
| `prediction_archive_detail.py` | Detail uses DB evaluation for market statuses |
| `prediction_history_evaluation.py` | `partial` result type |
| `PredictionHistoryPage.jsx` | Partial badge; market counts on cards; stats row |
| `validate_hotfix_archive_status_evaluation_join.py` | Validation |
| `deploy_hotfix_archive_status.sh` | Deploy script |

**Not changed:** prediction engine, WDE, stored payloads, Stripe, Performance Center aggregation logic.

## Before / after (production)

| Metric | Before (user report) | After |
|--------|----------------------|-------|
| Archive cards (evaluated fixtures) | Pending | Correct / Wrong / Partial from evaluation table |
| Archive summary correct/wrong | 0 / 0 (appeared all pending) | **3 / 1** (matches Performance Center) |
| Pending archive rows | 55 (appeared all pending) | **51** (genuine — no evaluation yet) |
| Performance Center | 3 correct, 1 wrong, 75% | Unchanged |

## Validation

```
Hotfix archive status validation: 16/16 PASS
```

- Archive counts match Performance Center
- Merge does not hide evaluation status
- Global detail shows market `result_status` from DB
- Filters + quarantine rules preserved

## Deploy

- Backup: `/opt/worldcup-predictor/backups/deploy-hotfix-archive-status-<timestamp>`
- API restart + frontend rebuild + nginx reload

## Rollback

Restore from backup: `football_intelligence.db`, `frontend_dist`, `.env.production`, redeploy prior git commit.
