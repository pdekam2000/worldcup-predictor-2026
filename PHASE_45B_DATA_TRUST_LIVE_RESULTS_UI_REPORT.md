# Phase 45B — Data Trust, Live Results, and UI Fix Report

**Status:** PRODUCTION_ACTIVE  
**Date:** 2026-06-21  
**Server:** https://footballpredictor.it.com

## Root causes

| Issue | Root cause |
|-------|------------|
| 100% Performance Center accuracy | Only **2** rows in `worldcup_prediction_evaluations`, both Phase 33/35 validation/test data |
| “Home vs Away” / 2-1 on NS fixtures | Test fixtures **1489393** and **1539007** evaluated before real match completion |
| Learning Dashboard 100% | Fixture-level outcomes attributed to all agents/markets with **n=2** |
| Only 12 predictions visible | Global archive (`worldcup_stored_predictions`) is authoritative since Phase 33; legacy sources never migrated to public archive |
| Stale results after kickoff | Auto-evaluation read local SQLite/JSONL only; did not refresh fixture status from API-Football |
| Dashboard grey text blocks | Likely browser translation overlay on chart labels; mitigated with `translate="no"` and unique gradient id |

## Bogus / test rows found

| fixture_id | Teams | Status | Eval | Reason |
|-----------|-------|--------|------|--------|
| 1489393 | Home vs Away | NS | correct / 2-1 | `known_validation_fixture` |
| 1539007 | Home vs Away | NS | correct / 2-1 | `known_validation_fixture` |

## Quarantine behavior (no hard delete)

- Added columns: `is_quarantined`, `evaluation_source`, `quarantine_reason`
- `run_evaluation_quarantine_pass()` marks test rows; data preserved
- Public APIs exclude `is_quarantined=1`:
  - `/api/performance/summary`
  - `/accuracy` (Performance Center)
  - Best Tips historical scoring
  - Learning / optimization dashboards
- Admin diagnostics: `GET /admin/accuracy/quarantined` (with warning banner)

## True public accuracy after fix

| Metric | Before | After |
|--------|--------|-------|
| Evaluated (public) | 2 | **0** |
| Overall accuracy | 100% | **null** (empty state) |
| Correct / wrong | 2 / 0 | 0 / 0 |

Public message: **“No completed real prediction evaluations yet.”**

## Live result refresh

- New module: `worldcup_predictor/automation/worldcup_background/result_refresh.py`
- CLI: `python main.py worldcup-refresh-results [--dry-run] [--limit N]`
- Production auto-evaluation timer now: **refresh → quarantine pass → evaluate → rebuild summary**
- Admin rebuild: `POST /admin/accuracy/rebuild?refresh_results=true&evaluate=true`
- UI note: “Results are checked automatically every 30 minutes after matches finish.”

## Learning dashboard trust

- Sample guard: **n < 20 settled** → `insufficient_data: true`
- No Top/Weakest agent rankings or weight suggestions below threshold
- Message: “Learning insights require at least 20 evaluated real predictions.”

## UI fixes

- **Dashboard:** `translate="no"` on Performance Trend panel; unique gradient id; clean empty trend copy
- **Performance Center:** honest empty state (no dev demo in production); 30-minute refresh note
- **Admin Learning:** insufficient-data banner when sample too small
- **Admin Accuracy:** quarantine diagnostic note; team names use `home_team`/`away_team`

## Validation

- Script: `scripts/validate_phase45b_data_trust_live_results_ui.py`
- Local: **21/21 PASS**
- Production post-deploy: **18/21** (UI source checks skipped on dist-only deploy; backend checks PASS)

## Unchanged (per rules)

- Prediction engine, WDE, raw probabilities
- Auth, subscriptions, history, weather
- Stripe **live mode** verified (`stripe_mode: live`)

## Rollback plan

1. Restore backup: `/opt/worldcup-predictor/backups/deploy-phase45b-20260621-193750/`
2. `cp football_intelligence.db` + `env.production` + frontend dist from backup
3. `systemctl restart worldcup-api && systemctl reload nginx`
4. Quarantined rows remain in DB (safe); pre-45B code would show them in public metrics again unless manually cleared
