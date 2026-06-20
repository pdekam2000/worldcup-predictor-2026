"""Phase 12B bridge caps and version — design constants from Phase 12A."""

from __future__ import annotations

CONFIG_VERSION = "12b-v1"

GLOBAL_LAMBDA_CAP = 0.22
LAMBDA_MIN = 0.55
LAMBDA_MAX = 3.8

DQ_DISABLE_BELOW = 45.0
DQ_FULL_AT = 70.0
DQ_SCALE_MIN = 0.35

SPECIALIST_CAPS: dict[str, float] = {
    "market_consensus_agent": 0.10,
    "injury_suspension_intelligence_agent": 0.12,
    "lineup_intelligence_agent": 0.10,
    "sharp_money_intelligence_agent": 0.05,
    "tournament_intelligence_agent": 0.06,
}

GROUP_CAPS: dict[str, float] = {
    "odds": 0.12,
    "squad_health": 0.18,
    "context": 0.10,
}

AGENT_GROUPS: dict[str, str] = {
    "market_consensus_agent": "odds",
    "injury_suspension_intelligence_agent": "squad_health",
    "lineup_intelligence_agent": "squad_health",
    "sharp_money_intelligence_agent": "odds",
    "tournament_intelligence_agent": "context",
}

LIMITED_AGENTS = frozenset({"market_consensus_agent"})

FULL_AGENTS = frozenset(SPECIALIST_CAPS.keys())
