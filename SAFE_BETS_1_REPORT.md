# PHASE SAFE-BETS-1 — High Probability Market Scanner

**Status:** Complete (internal / research-only)  
**Date:** 2026-06-29  
**Mode:** Implement → Validate → Report

## Goal

Internal scanner for upcoming fixtures that finds high-probability betting markets, separates meaningful picks from low-value 1.01 traps, and stores research-only outputs in SQLite.

## Scope & Safety

| Constraint | Status |
|---|---|
| Internal only | Yes — no public API routes |
| Research-only storage | `safe_bet_candidates` table |
| No WDE / EGIE / ECSE model changes | Verified |
| No betting automation | CLI scan only |
| No deployment | Scripts + DB only |
| Settings preserved | New flags default `false` / safe values |

## Architecture

```
scripts/run_safe_bets_1.py
    └── worldcup_predictor/research/safe_bets/scanner.py
            ├── discover_fixtures_in_window()      # repo + API-Football fallback
            ├── discover_ecse_snapshot_fixtures()   # ECSE live snapshot supplement
            ├── providers.py                       # odds ingestion
            ├── markets.py                         # market classification
            ├── scoring.py                         # implied prob, buckets, traps
            └── store.py                           # SQLite persistence + API log
```

### Providers (priority order)

1. **SQLite `odds_snapshots`** — cached prematch odds
2. **API-Football live odds** — when `SAFE_BETS_USE_LIVE_API=true`
3. **Sportmonks enrichment cache** — `sportmonks_fixture_enrichment.raw_json`
4. **OddAlerts odds history** — when fixture ID is known (no per-fixture discovery loop)

### Markets scanned

- Double Chance
- Team to Score
- Goals Over/Under
- BTTS
- Corners O/U
- Team Corners
- Cards O/U
- Own Goal No
- Asian Handicap (when available)

### Scoring

- Implied probability: `1 / odds`
- Light de-vig estimate for two-way markets
- Buckets: **90%+**, **85–90%**, **75–85%**
- Trap flags:
  - `odds <= 1.05`
  - Trivial lines (e.g. Over 0.5 goals, extreme unders)
  - High bookmaker margin (when overround known)
- `usefulness_score` combines devigged probability, market type bonus, data quality, trap penalties

## Database

| Table | Purpose |
|---|---|
| `safe_bet_candidates` | Scored picks (UNIQUE `candidate_key`) |
| `safe_bets_scan_runs` | Batch run metadata |
| `safe_bets_api_log` | Provider API call audit trail |

### Candidate fields

`fixture_id`, `match_name`, `kickoff_utc`, `market`, `selection`, `odds`, `implied_probability`, `devigged_probability`, `probability_bucket`, `usefulness_score`, `trap_flag`, `reason`, `provider`, `bookmaker`, `created_at`

## Settings (opt-in)

| Env | Default | Purpose |
|---|---|---|
| `SAFE_BETS_ENABLED` | `false` | Feature gate (orchestrator hook reserved) |
| `SAFE_BETS_HOURS` | `72` | Upcoming window |
| `SAFE_BETS_MIN_IMPLIED` | `0.75` | Minimum implied prob to store |
| `SAFE_BETS_ALLOW_TRIVIAL` | `false` | Allow Over 0.5 / extreme lines |
| `SAFE_BETS_MAX_API_CALLS` | `200` | Per-run API budget |
| `SAFE_BETS_DRY_RUN` | `false` | Scan without persisting |
| `SAFE_BETS_USE_LIVE_API` | `true` | API-Football live fetch |

## CLI

```bash
python scripts/run_safe_bets_1.py --hours 72
python scripts/run_safe_bets_1.py --hours 72 --limit 8 --dry-run
```

## Validation

```bash
python scripts/validate_safe_bets_1.py
```

**Result:** 17/17 PASS

Checks include:
- Implied probability math
- 1.01 trap flagging
- 85%+ meaningful bucket separation
- Duplicate candidate rejection
- API log table accessibility
- No public route exposure
- No ECSE/WDE scoring engine edits

## Production scan (latest)

| Metric | Value |
|---|---|
| Batch ID | `SAFE-BETS-20260629-160655` |
| Fixtures scanned | 8 |
| Candidates stored | 1,613 |
| Traps flagged | 621 |
| Meaningful 85%+ (non-trap) | 532 |
| Bucket 90%+ (non-trap) | 236 |
| Bucket 85–90% (non-trap) | 214 |
| API calls logged | 35 (incl. prior partial run) |
| Validation | 17/17 PASS |

### Trap examples (correctly flagged)

| Match | Market | Selection | Odds | Reason |
|---|---|---|---|---|
| Canada vs Bosnia | goals_ou | Under 5.5 | 1.01 | low_odds_trap;trivial_under_high_goals_line |
| Canada vs Bosnia | goals_ou | Under 4.5 (team) | 1.01 | low_odds_trap |
| Canada vs Bosnia | asian_handicap | Home +1 | 1.01 | low_odds_trap |

### Meaningful non-trap examples (odds > 1.05)

| Match | Market | Selection | Odds | Bucket |
|---|---|---|---|---|
| Canada vs Bosnia | double_chance | Home/Draw (1H) | 1.12–1.14 | 85–90% |
| Canada vs Bosnia | btts | No (1H) | 1.12 | 85–90% |
| Canada vs Bosnia | goals_ou | Under 3.75 | 1.12 | 85–90% |
| Canada vs Bosnia | corners_ou | Under 12.5 | 1.09 | 90%+ |

## Artifacts

- `artifacts/safe_bets_1_latest_scan.json` — latest run summary
- `artifacts/safe_bets_1_report_stats.json` — DB aggregates

## Files added

```
worldcup_predictor/research/safe_bets/
  __init__.py
  ddl.py
  markets.py
  scoring.py
  store.py
  providers.py
  scanner.py
scripts/run_safe_bets_1.py
scripts/validate_safe_bets_1.py
```

## Notes

- Scanner supplements fixture discovery from `ecse_prediction_snapshots` when present.
- Sportmonks odds are read from enrichment cache (`raw_json`), not live premium calls.
- OddAlerts per-fixture discovery was intentionally **not** wired into the scan loop to avoid N× bulk API discovery; history fetch is used only when an ID is already resolved.
- Re-running the scanner skips duplicate `candidate_key` rows (idempotent inserts).
