"""Constants and promotion gates for football-strength / Lambda V2 research."""

from __future__ import annotations

FEATURE_SCHEMA_VERSION = "fsf-prematch-v1"
LAMBDA_FLOOR = 0.15
LAMBDA_CEIL = 6.0

FORWARD_MIN_GLOBAL = 250
FORWARD_MIN_COMPLETE_FEATURE = 100
FORWARD_MIN_ACTUAL_4PLUS = 75
FORWARD_MIN_ACTUAL_5PLUS = 40
FORWARD_MIN_MULTI_LINE_MARKET = 100

HIGH_SCORE = 5
LOW_SCORE = 2
SEVERE_ERR = 2.0

# Shadow table names (never canonical freezes)
SHADOW_TABLE = "lambda_v2_shadow_outputs"
DERIVED_FORM_TABLE = "derived_historical_team_form_snapshots"
TOTALS_SNAPSHOT_TABLE = "totals_market_shadow_snapshots"
