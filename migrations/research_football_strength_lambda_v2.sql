-- Additive research/shadow schemas (safe; do not alter frozen_predictions)
-- Apply only after review. Rollback: DROP TABLE IF EXISTS ...
CREATE TABLE IF NOT EXISTS derived_historical_team_form_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  fixture_id INTEGER NOT NULL,
  team_name TEXT NOT NULL,
  home_or_away_role TEXT NOT NULL,
  cutoff_timestamp TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  feature_schema_version TEXT NOT NULL,
  snapshot_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS totals_market_shadow_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  fixture_id INTEGER,
  line REAL NOT NULL,
  over_odds REAL,
  under_odds REAL,
  created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lambda_v2_shadow_outputs (
  shadow_id TEXT PRIMARY KEY,
  fixture_id INTEGER NOT NULL,
  model_id TEXT NOT NULL,
  shadow_hash TEXT NOT NULL,
  created_at_utc TEXT NOT NULL
);
