# FULL-PROJECT-SYNC-2 — Local Change Inventory

**Workspace:** Local PC · baseline commit `9ca89f0`

## Summary

| Category | Modified tracked | New untracked |
|----------|------------------|---------------|
| Production backend | 7 files | 12+ modules |
| Frontend | 6 files | 1 component |
| API routes | 1 file | — |
| Prediction pipeline | 3 files | 4 scripts |
| Odds freshness | 2 files | 6 modules + 3 scripts |
| Fixture sync | 1 file | 2 scripts + wc_schedule_sync |
| ECSE research | 1 file | ecse_rerank, eval_coverage, top10*, top3* |
| Validators | — | 12 scripts |
| Documentation | — | 30+ phase reports |
| Runtime (exclude) | 9 data/* paths | — |

## Modified tracked source (commit)

### Frontend (Owner UI — OWNER-PREDICTIONS-UI-2)
- `base44-d/src/components/match-center/EcseExactScorePanel.jsx`
- `base44-d/src/components/match-center/PredictionExpandPanel.jsx`
- `base44-d/src/lib/planGating.js`, `predictionDetailProUtils.js`, `trustCopy.js`
- `base44-d/src/pages/MatchDetailPage.jsx`

### Backend / pipeline
- `scripts/run_production_prediction_pipeline.py`
- `worldcup_predictor/api/routes/ecse_display.py`
- `worldcup_predictor/owner/euro_c_odds_import.py`
- `worldcup_predictor/owner/production_pipeline/runner.py`
- `worldcup_predictor/owner_daily/cycle.py`
- `worldcup_predictor/owner_daily/predictions.py`
- `worldcup_predictor/research/ecse_match_display.py`

## New untracked source (commit)

### Odds freshness (ODDS-FRESHNESS-1, ODDS-TIMESTAMP-NORMALIZATION-1)
- `worldcup_predictor/odds/freshness_*.py`, `timestamp_normalization.py`
- `scripts/run_odds_freshness_refresh.py`, `validate_odds_freshness_1.py`, `validate_odds_timestamp_normalization_1.py`, `audit_odds_timestamp_formats.py`

### Fixture sync (FIXTURE-SYNC-1)
- `worldcup_predictor/owner_daily/wc_schedule_sync.py`
- `scripts/sync_wc_upcoming_fixtures.py`, `audit_wc_fixture_schedule.py`, `validate_fixture_sync_1.py`, `find_next_knockout_fixture.py`

### Controlled predictions / match eval
- `scripts/discover_controlled_knockout_predictions_2.py`, `run_controlled_knockout_predictions_2.py`, `inspect_controlled_knockout_predictions_2.py`, `validate_controlled_knockout_predictions_2.py`
- `scripts/capture_match_eval_1567310_prematch.py`, `inspect_match_eval_1567310_result.py`, `validate_match_eval_1567310_1.py`

### Research (shadow-only, no promotion)
- `worldcup_predictor/research/ecse_rerank/`
- `worldcup_predictor/research/eval_coverage/`
- `worldcup_predictor/research/top10_coverage/`
- `worldcup_predictor/research/top10_to_top3_selector/`
- `worldcup_predictor/research/top3_endresult_optimizer/`
- Matching `scripts/run_*_1.py` and `scripts/validate_*_1.py`

### Frontend new
- `base44-d/src/components/match-center/EndResultCandidatesPanel.jsx`

## Excluded from commit

| Class | Examples | Reason |
|-------|----------|--------|
| DB | `data/*.db` | gitignore / canonical on Hetzner |
| Runtime data | `data/shadow/*.jsonl`, `data/cache/`, sportmonks dumps | gitignore |
| Secrets | `.env`, `.env.production` | gitignore |
| Generated runtime | `PRODUCTION_PIPELINE_LAST_RUN.md`, `ODDS_FRESHNESS_1_LAST_RUN.md` | pipeline output |
| Artifacts | `artifacts/` | gitignore |
| Accidental | `C:UserskamanDesktoppostgres_backup.sql` (on Hetzner only) | forbidden |

## Phases covered

CLAUDE-OPS-1 · OWNER-PREDICTIONS-UI-2 · ECSE-RERANK-1 · TOP3-ENDRESULT-OPTIMIZER-1 · TOP10-COVERAGE-1 · TOP10-TO-TOP3-SELECTOR-1 · EVAL-COVERAGE-1 · ODDS-FRESHNESS-1 · ODDS-TIMESTAMP-NORMALIZATION-1 · FIXTURE-SYNC-1 · NEXT-KNOCKOUT-FRESH-ODDS-1/1B · MATCH-EVAL-1567310-1 · CONTROLLED-KNOCKOUT-PREDICTIONS-2

**Missing:** `validate_controlled_knockout_predictions_3.py` (not created — CONTROLLED-KNOCKOUT-PREDICTIONS-3 not started)
