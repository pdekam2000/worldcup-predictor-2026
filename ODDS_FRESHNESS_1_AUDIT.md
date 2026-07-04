# ODDS-FRESHNESS-1 — System Audit

Audited: **2026-07-04 00:32:17 UTC**

## Odds Tables

| Table | Rows | Distinct fixtures | Newest | Oldest |
|-------|-----:|------------------:|--------|--------|
| odds_snapshots | 2242 | 901 | sportmonks_wc2026_2026-06-28 | 2026-06-13T14:44:54.699530 |

## Source Coverage

- **live**: 652 snapshots
- **cache**: 540 snapshots
- **api_gap_cache_import**: 519 snapshots
- **sportmonks**: 316 snapshots
- **oddalerts_csv_policy**: 197 snapshots
- **euro_c3_api-football_watch**: 8 snapshots
- **euro_c2_sportmonks_import**: 6 snapshots
- **daily_owner_api-football_import**: 2 snapshots
- **phase31e_cache_backfill**: 1 snapshots
- **euro_c3_sportmonks_watch**: 1 snapshots

## WC Fixture Freshness Segments

| Status | Count |
|--------|------:|
| FRESH_ODDS | 44 |
| ODDS_FRESHNESS_UNKNOWN | 119 |
| ODDS_MISSING | 1 |
| REQUIRES_FRESH_ODDS | 0 |
| STALE_ODDS | 183 |

- Missing odds: **1**
- Stale odds: **183**
- Fresh odds: **44**

## ECSE/WDE Impact Fields

- lambda_home/lambda_away (ECSE — odds-implied goals)
- top_10_scorelines_json ranking (ECSE)
- one_x_two / over_under / btts (WDE)
- End Result Top3/Top5 candidate ordering

- ECSE snapshots: **18**
- WDE stored predictions: **185**

## Quota Risk

Uncontrolled refresh avoided; use --max-provider-calls and cache-first import.
Recommended max provider calls per run: **20**

## Integration Points

- Odds fetch: owner_daily/odds_import.py, owner_daily/provider_fetch.py, clients/api_football.py, providers/oddalerts_provider.py, providers/sportmonks_provider.py
- Storage: ['odds_snapshots table']
- ECSE feed: build_ecse_live_prediction / lambda from odds_snapshots
- WDE feed: PredictPipeline / odds_snapshots + api cache
