# Paid Provider Capability Inventory

Date: 2026-07-12

## Summary

| Provider | Role | Primary storage | Affects WDE | Affects ECSE | Affects backtest |
|----------|------|-----------------|-------------|--------------|------------------|
| API-Football | Primary | `fixtures`, `fixture_enrichment`, `odds_snapshots`, `api_response_cache` | Yes | Yes (odds lambdas) | Yes (cache replay) |
| SportMonks | Enrichment | `sportmonks_fixture_enrichment`, `fs_sportmonks_xg_*`, pressure store | Shadow promotion only | Research/EGIE | xG/pressure backtests |
| OddAlerts | Research/CSV | `oddalerts_probability_market_rows`, shadow tables | No (official) | Shadow/lab only | CSV historical |
| The Odds API | Odds consensus | `odds_api_cache`, `odds_api_usage` | Cross-source quality | No | Cache replay |
| RapidAPI stats/xG | Supplemental | In-memory / supplemental JSON | Agent signals only | No | No |
| Weather | Enrichment | File cache + report embed | Confidence modifier | No | No |

## API-Football endpoints (configured)

| Endpoint | Pre-match | Historical | Cache TTL | Storage | Prediction consumer |
|----------|-----------|------------|-----------|---------|---------------------|
| `fixtures` | Yes | Yes | 1800s | `fixtures` | Discovery, WDE context |
| `odds` | Yes | Limited | 3600s | `odds_snapshots`, enrichment | WDE, ECSE, BTTS, O/U |
| `teams/statistics` | Yes | Yes | 86400s | enrichment | WDE form/strength |
| `fixtures/headtohead` | Yes | Yes | 3600s | enrichment | WDE H2H factor |
| `injuries` | Yes | Yes | 28800s | enrichment | WDE injury factor |
| `fixtures/lineups` | ≤4h pre-KO | Yes | 900–1800s | enrichment | WDE lineup factor |
| `fixtures/statistics` | Post-match | Yes | 1800s | enrichment | **Not pre-match** |
| `standings` | Yes | Yes | 86400s | enrichment | Motivation context |
| `predictions` | Yes | Yes | 3600s | cache only | Reference, not official pick |

**Quota:** Daily live budget via `quota_guard.py`; scheduled odds refresh capped at 20 calls/run.

## SportMonks endpoints

| Include group | Pre-match | Storage | Consumer |
|---------------|-----------|---------|----------|
| participants, statistics, lineups | Yes | `sportmonks_fixture_enrichment` | Enrichment gap-fill |
| xGFixture | Mixed | `fs_sportmonks_xg_*` | EGIE, shadow xG (sparse) |
| pressure | Live/in-match | pressure feature store | Goal-timing research |
| odds, predictions | Pre-match | enrichment JSON | Odds fallback #2 |

## OddAlerts

| Path | Trigger | Storage | Consumer |
|------|---------|---------|----------|
| Gmail CSV import | Daily pipeline | `oddalerts_probability_market_rows` | ECSE shadow, segment calibration |
| Live API | Strict refresh fallback #3 | `oddalerts_odds_history` | Crosswalk-only refresh |
| Shadow tables | Lab runs | `ecse_oddalerts_shadow_*` | Owner shadow API |

## Call triggers (no new calls in this phase)

- On-demand: prediction gate, match intelligence builder, owner daily cycle
- Scheduled: `worldcup-odds-refresh.timer` (30 min, max 20 calls)
- Backfill: result backfill (separate unit, overlap-protected)

**This audit phase:** `provider_calls_made = 0`
