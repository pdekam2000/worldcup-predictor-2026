# Provider Feature Leakage Audit

Rule: `feature_available_at <= prediction_cutoff_at < kickoff_at`

| Feature | Provider | Class | Cutoff rule | Notes |
|---------|----------|-------|-------------|-------|
| odds_home/draw/away | api-football|oddalerts|sportmonks|the-odds-api | SAFE_IF_SNAPSHOT_TIMESTAMP_VALID | snapshot_at <= prediction_cutoff < kickoff | Canonical odds_snapshots; closing odds after kickoff excluded. |
| implied_prob_* | derived_odds | SAFE_IF_SNAPSHOT_TIMESTAMP_VALID | same as odds snapshot | Derived from pre-match 1X2/O-U/BTTS odds only. |
| expectedGoalsHome/Away (CSV) | external_historical_csv | POST_MATCH_ONLY | realized match xG — unavailable pre-kickoff | EXCLUDED from primary shadow fusion; diagnostic upper-bound only. |
| xg_snapshots | sportmonks | SAFE_IF_SNAPSHOT_TIMESTAMP_VALID | snapshot_at <= prediction_cutoff | Sparse coverage; validate timestamp per row. |
| home_form/away_form | api-football | SAFE_PREMATCH | form computed from matches before cutoff | Requires explicit form-as-of date in enrichment. |
| fixture_enrichment.statistics_json | api-football | POST_MATCH_ONLY | match statistics after FT | Shots/possession/pressure from completed match — leakage. |
| lineups_json | api-football | SAFE_IF_SNAPSHOT_TIMESTAMP_VALID | lineup snapshot <= 4h pre-kickoff typical | Lineup release timing must be validated per fixture. |
| injuries | api-football | SAFE_IF_SNAPSHOT_TIMESTAMP_VALID | injury list as-of prediction cutoff | Injury updates after cutoff are leakage. |
| standings/motivation | api-football|sportmonks | SAFE_PREMATCH | standings before kickoff round | Must use standings as-of prior matchday. |
| pressure_index | sportmonks | LIVE_ONLY | in-match pressure feed | Not for pre-match WDE/ECSE backtest. |
| oddalerts_probability_market_rows | oddalerts_csv | SAFE_IF_SNAPSHOT_TIMESTAMP_VALID | CSV row timestamp / fixture pre-kickoff | Primary OddAlerts path is Gmail CSV import. |
| provider_prediction_model | api-football|sportmonks|oddalerts | SAFE_IF_SNAPSHOT_TIMESTAMP_VALID | provider prediction fetched pre-kickoff | Reference only; not official production pick. |
| closing_odds | any | LEAKAGE_RISK | closing captured at/after kickoff | Never use for pre-match backtest. |

## Excluded from primary shadow fusion

- CSV `expectedGoalsHome/Away` — POST_MATCH_ONLY
- `fixture_enrichment.statistics_json` — POST_MATCH_ONLY
- SportMonks pressure — LIVE_ONLY
- Closing odds without pre-kickoff timestamp — LEAKAGE_RISK

## Safe for primary experiments (this phase)

- Pre-match FT odds from stored historical CSV
- Derived implied probabilities and entropy
- Form proxy derived from pre-match odds shape (not results)
