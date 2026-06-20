"""Phase 24A/24B — trace promotion adapter constants (weights unchanged)."""

from __future__ import annotations

CONFIG_VERSION = "24a-v1"
CONFIG_VERSION_24B = "24b-v1"
CONFIG_VERSION_24C = "24c-v1"

# Bounded deltas (Phase 23B / 24A spec)
MAX_LINEUP_SCORE_DELTA = 8.0
MAX_LINEUP_EDGE_DELTA = 0.04
MAX_CONFIDENCE_BOOST = 2.0
MAX_CONFIDENCE_REDUCE = 4.0
MAX_CUMULATIVE_PROMOTION_CONF_DELTA = 6.0

# Phase 24B — tournament context → motivation_psychology
MAX_MOTIVATION_SCORE_DELTA = 6.0
MAX_MOTIVATION_EDGE_DELTA = 0.025
MAX_CONTEXT_CONFIDENCE_BOOST = 1.5
MAX_CONTEXT_CONFIDENCE_REDUCE = 2.0
MIN_GROUP_CONTEXT_STRENGTH = 36.0
WEIGHTS_MOT_BLEND = (0.50, 0.30, 0.20)  # mot_psych, tour_intel_pressure, context_avg

# Composite blend weights (sum = 1.0)
WEIGHTS_OFFICIAL = (0.75, 0.15, 0.10)  # lineup_v2, expected_xi, lineup_confidence
WEIGHTS_EXPECTED = (0.15, 0.70, 0.15)  # expected leads when no official XI

PROMOTION_AGENT_KEY = "expected_lineup_agent"
PROMOTION_FACTOR_KEY = "lineup_strength"
CONTEXT_PROMOTION_AGENT_KEY = "tournament_context_agent"
CONTEXT_PROMOTION_FACTOR_KEY = "motivation_psychology"

# Phase 24C — xG → tactics_matchup
MAX_XG_TACTICS_SCORE_DELTA = 6.0
MAX_XG_TACTICS_OVER_DELTA = 0.15
MIN_XG_CONFIDENCE_GATE = 50.0
MAX_XG_DISAGREEMENT = 0.35
XG_PROMOTION_AGENT_KEY = "xg_intelligence_agent"
XG_PROMOTION_FACTOR_KEY = "tactics_matchup"

# Phase 24C — Sportmonks prediction → confidence/audit only
MAX_SPORTMONKS_CONFIDENCE_REDUCE = 6.0
MAX_SPORTMONKS_CONFIDENCE_BOOST = 0.0
MIN_SPORTMONKS_CONFIDENCE_GATE = 55.0
SPORTMONKS_PROMOTION_AGENT_KEY = "sportmonks_prediction_agent"
