# Odds Storage Source Matrix

| Source | Table/Cache | Writer | Readers (before hotfix) | Key fields | Timestamp field | Fixture ID | Provider | Market | Bookmaker | Canonical | Legacy | Prediction freshness reads |
|--------|---------------|--------|-------------------------|------------|-----------------|------------|----------|--------|-----------|-----------|--------|---------------------------|
| Production DB odds snapshots | `odds_snapshots` | `FootballIntelligenceRepository.save_snapshot`, daily import, `strict_live_refresh` | `_latest_odds_snapshot`, filter `_match_odds`, freshness metadata | `fixture_id`, `competition_key`, `snapshot_at`, `payload_json` | Column `snapshot_at`; payload `fetched_at_utc` | `fixture_id` (API-Football ID) | `payload.provider` | Parsed from `bookmakers[].bets[].name` | Median across bookmakers | **Yes** | No | **Yes (after hotfix via canonical bridge)** |
| Legacy latest snapshot helper | `odds_snapshots` (same table) | — | `_latest_odds_snapshot` | `id`, `snapshot_at`, `payload` | Column only | `fixture_id` | payload | parsed lines | parsed | No (helper only) | Yes | Was indirect via column-only read |
| Provider response cache | `.cache/api_football/*.json` | API client | Importers only | hashed request | file mtime | in response | api-football | raw | raw | No | Yes | No |
| Owner odds cache | in-request dict | `controlled_owner_odds_lookup` | GPT filter Tier B | home/draw/away | `odds_timestamp` | fixture_id | provider | implicit 1X2 | count | No | No | No (ephemeral) |
| WDE odds evidence | prediction payload | runtime after gate | model output | flat probabilities | snapshot ref | fixture_id | from freshness | 1X2 | — | No | No | No |
| Filter fixture payload | HTTP response | `filterMatchesByOdds` | GPT Actions | `odds.home/draw/away` | not always propagated | fixture_id | audit only | implicit | bookmaker_count | No | No | No |
| In-memory refreshed result | `refresh_live_odds` return | `strict_live_refresh` | `refresh_gate` | provider, snapshot_at | `fetched_at_utc` in return | fixture_id | provider | match_winner | count | No | No | No unless persisted |
| Canonical snapshot service | `odds_snapshots` via `get_latest_valid_1x2_odds_snapshot` | — | filter, freshness, refresh gate, owner odds | full diagnostic struct | `extract_odds_fetched_at_utc` | `fixture_id` | required for fresh | `FULL_TIME_1X2` | median + count | **Yes** | No | **Yes** |

## Canonical choice

**Single canonical persisted representation:** latest valid row in `odds_snapshots` selected by `get_latest_valid_1x2_odds_snapshot()`.

Legacy `_latest_odds_snapshot` remains for import compatibility but must not independently determine freshness.
