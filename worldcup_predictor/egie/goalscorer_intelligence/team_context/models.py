"""Phase 54R team context enrichment models."""

from __future__ import annotations

from typing import Literal

from worldcup_predictor.egie.goalscorer_ml_shadow.models import (
    FEATURE_GROUP_A,
    FEATURE_GROUP_B,
    FEATURE_GROUP_C,
    FEATURE_GROUP_D,
)

TEAM_CONTEXT_COLUMNS: tuple[str, ...] = (
    "team_attack_strength",
    "team_defensive_weakness",
    "team_recent_goals_scored",
    "team_recent_goals_conceded",
    "team_rolling_xg",
    "team_rolling_xga",
    "team_league_position",
    "team_elo_strength",
    "team_home_attack",
    "team_away_attack",
    "is_home",
    "is_favorite",
    "is_underdog",
    "team_attacking_share",
)

PLAYER_ONLY_COLUMNS = FEATURE_GROUP_A + FEATURE_GROUP_B + FEATURE_GROUP_C
PLAYER_LINEUP_COLUMNS = PLAYER_ONLY_COLUMNS + FEATURE_GROUP_D
PLAYER_TEAM_COLUMNS = PLAYER_LINEUP_COLUMNS + TEAM_CONTEXT_COLUMNS
PLAYER_TEAM_ODDS_COLUMNS = PLAYER_TEAM_COLUMNS + ("odds_implied_feature",)

FEATURE_GROUPS: dict[str, tuple[str, ...]] = {
    "player_only": PLAYER_ONLY_COLUMNS,
    "player_lineup": PLAYER_LINEUP_COLUMNS,
    "player_team": PLAYER_TEAM_COLUMNS,
    "player_team_odds": PLAYER_TEAM_ODDS_COLUMNS,
}

UEFA_LEAGUE_IDS: dict[int, str] = {
    2: "champions_league",
    5: "europa_league",
    2286: "conference_league",
}

WC_LEAGUE_ID = 732

BASELINE_54Q_UEFA_TOP3 = 0.5658
BASELINE_54Q_OVERALL_TOP3 = 0.5712
ELITE_THRESHOLD = 0.65

VALID_RECOMMENDATIONS = frozenset(
    {
        "GOALSCORER_HIGH_VALUE",
        "GOALSCORER_ELITE_PATH",
        "GOALSCORER_MAXED_OUT",
    }
)

FeatureVerdict = Literal["positive", "neutral", "harmful"]
