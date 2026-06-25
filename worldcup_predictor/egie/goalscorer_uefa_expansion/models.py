"""Phase 55B UEFA goalscorer odds expansion models."""

from __future__ import annotations

UEFA_LEAGUE_IDS: dict[int, str] = {
    2: "champions_league",
    5: "europa_league",
    2286: "conference_league",
}

WC_LEAGUE_ID = 732

MARKET_TYPES = (
    "anytime_goalscorer",
    "first_goalscorer",
    "last_goalscorer",
    "player_to_score",
    "team_goalscorer",
    "other",
)

VALID_RECOMMENDATIONS = frozenset(
    {
        "GOALSCORER_HIGH_VALUE",
        "GOALSCORER_ELITE_PATH",
        "ODDS_NOT_ENOUGH",
    }
)

BASELINE_54Q_UEFA_TOP3 = 0.5658
BASELINE_54Q_OVERALL_TOP3 = 0.5712
BASELINE_WC_TOP3 = 0.7714
BASELINE_COVERAGE_PCT = 0.03
