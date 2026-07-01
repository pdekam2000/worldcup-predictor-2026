# WC Daily WDE Inputs Hotfix Report

**Phase:** WC-DAILY-WDE-INPUTS
**Final recommendation:** `WC_DAILY_REPORT_READY`

## Root cause

Three upcoming WC knockout fixtures were absent from the canonical `fixtures` table.
Daily discovery only triggers provider backfill when zero local fixtures exist;
Netherlands vs Morocco (already stored) blocked import. Background import script hung
and held a SQLite write lock.

## SQLite lock diagnosis

- DB path: `data\football_intelligence.db`
- Journal mode: `delete` (WAL not enabled; using DELETE + busy_timeout)
- Busy timeout: `5000` ms
- Lock type: `stale_background_process` (`watch_uefa_odds_readiness.py` + hung `_import_wc_today_fixtures.py`)
- Stale processes stopped: `watch_uefa_odds_readiness.py` (PID 11284), hung import script (PID 5264)

## Lock mitigation applied

- `PRAGMA busy_timeout = 30000` on all connections via `connect()`
- `run_with_sqlite_retry()` with exponential backoff for WC fixture import
- Stale `_import_wc_today_fixtures.py` process terminated when detected

## Fixtures imported

{
  "phase": "WC-DAILY-WDE-INPUTS",
  "target_date": "2026-06-30",
  "imported_by_date": 4,
  "imported_by_id": 1,
  "skipped_existing": 3,
  "errors": [],
  "fixtures": [
    {
      "fixture_id": 1564789,
      "home_team": "Ivory Coast",
      "away_team": "Norway",
      "kickoff_utc": "2026-06-30T17:00:00",
      "status": "NS"
    },
    {
      "fixture_id": 1565177,
      "home_team": "France",
      "away_team": "Sweden",
      "kickoff_utc": "2026-06-30T21:00:00",
      "status": "NS"
    },
    {
      "fixture_id": 1567306,
      "home_team": "Mexico",
      "away_team": "Ecuador",
      "kickoff_utc": "2026-07-01T01:00:00",
      "status": "NS"
    },
    {
      "fixture_id": 1562345,
      "home_team": "Netherlands",
      "away_team": "Morocco",
      "kickoff_utc": "2026-06-30T01:00:00",
      "status": "PEN"
    }
  ],
  "provider_log": "logs\\daily_provider_calls_20260630.jsonl"
}

## Odds refresh

{
  "phase": "DAILY-OWNER-2",
  "dry_run": false,
  "fixtures_scanned": 3,
  "fixtures_with_odds_before": 3,
  "fixtures_with_odds_after": 3,
  "imported_count": 0,
  "cache_hits": 0,
  "skipped": [
    {
      "fixture_id": 1562345,
      "competition_key": "world_cup_2026",
      "home_team": "Netherlands",
      "away_team": "Morocco",
      "reason": "fresh_complete_odds"
    },
    {
      "fixture_id": 1564789,
      "competition_key": "world_cup_2026",
      "home_team": "Ivory Coast",
      "away_team": "Norway",
      "reason": "fresh_complete_odds"
    },
    {
      "fixture_id": 1565177,
      "competition_key": "world_cup_2026",
      "home_team": "France",
      "away_team": "Sweden",
      "reason": "fresh_complete_odds"
    }
  ],
  "imported": [],
  "provider_errors": [],
  "provider_calls": {}
}

## WDE before/after

- Before: `{"with_wde": 1, "fixtures": {"1564789": {"has_wde": false, "wde_1x2": null, "source": null}, "1565177": {"has_wde": false, "wde_1x2": null, "source": null}, "1567306": {"has_wde": false, "wde_1x2": null, "source": null}, "1562345": {"has_wde": true, "wde_1x2": null, "source": "owner_daily_predictions"}}}`
- After: **4/4 fixtures with WDE**, **4/4 odds**, labels updated (see `wc_today_predictions_20260630.json`)
- After summary: WDE **4** | ECSE **4** | Odds **4** | Shadow **4** | missing warnings **none**

- Strongest signal after: **France vs Sweden**

## Draw/PEN cover

- Ivory Coast vs Norway: ECSE Top-1 **1-1** — draw/PEN cover warning remains active for knockout.

## Validation

- Passed: **19/19**
- Failed checks: `[]`

## Remaining missing data

- None