# PHASE 51H — EGIE Historical Backtest Report

**Status:** completed  
**Mode:** Read-only — SQLite + EGIE PostgreSQL raw store; no API calls, no PostgreSQL prediction writes, no deploy

**Competition:** `premier_league`  
**Data policy:** `db_only_no_external_api_no_persist`  
**Window:** 2024-06-22 → 2026-06-22 (730 days lookback)

## Methodology

- Finished PL fixtures with goal-event data (Phase A ingest) from SQLite
- Features built **as-of kickoff** (leakage-safe `before_kickoff` filters)
- Engine: existing `EliteGoalTimingEngine` — **no threshold or model changes**
- Evaluation: `evaluate_goal_timing_prediction()` (First Goal Team, Goal Range, Goal Minute)
- `backtest_mode()` blocks all external API calls

## Sample

| Metric | Count |
|--------|------:|
| Fixtures scanned | 359 |
| Published predictions | 349 |
| NO_PICK | 10 |
| Evaluable published | 349 |
| Errors | 0 |

## Accuracy (published + evaluable)

| Market | Win rate | Soft win rate | Correct | Wrong | Partial |
|--------|----------|---------------|--------:|------:|--------:|
| First Goal Team | 50.8% | — | 100 | 97 | 0 |
| Goal Range | 27.8% | — | 97 | 252 | 0 |
| Goal Minute | 3.4% | 33.8% | 8 | 231 | 110 |

*First Goal Team: 152 fixtures scored `pending` when the engine predicted `none` but a goal occurred — excluded from win-rate denominator (correct+wrong only).*

## League breakdown

### `premier_league` (n=349)
- Team: 50.8%
- Range: 27.8%
- Minute soft: 33.8%

## DQ bucket win rate (team market)

- `dq_0_55_0_65`: 50.8% (n=349)

## Confidence bucket win rate (team market)

- `conf_0_50_0_65`: 76.9% (n=29)
- `conf_gte_0_65`: 48.9% (n=320)

## Calibration (confidence vs hit rate)

### first_goal_team
- `conf_0_50_0_65`: hit 76.9%, soft 76.9%, mean conf 0.6086, n=13
- `conf_gte_0_65`: hit 48.9%, soft 48.9%, mean conf 0.65, n=184

### goal_range
- `conf_0_50_0_65`: hit 13.8%, soft 13.8%, mean conf 0.6035, n=29
- `conf_gte_0_65`: hit 29.1%, soft 29.1%, mean conf 0.65, n=320

### goal_minute
- `conf_0_50_0_65`: hit 4.2%, soft 20.7%, mean conf 0.6035, n=29
- `conf_gte_0_65`: hit 3.3%, soft 35.0%, mean conf 0.65, n=320

## Run locally

```bash
python scripts/egie_phase51h_historical_backtest.py --limit 380
python scripts/validate_phase51h_egie_historical_backtest.py
```

## Artifacts

- Metrics JSON: `artifacts\phase51h_egie_backtest.json`
- Per-fixture JSONL: `artifacts\phase51h_egie_backtest.jsonl`

**No deployment. Read-only historical data.**
