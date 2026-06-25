"""Phase 54S player availability intelligence models."""

from __future__ import annotations

from typing import Literal

from worldcup_predictor.egie.goalscorer_ml_shadow.models import (
    FEATURE_GROUP_A,
    FEATURE_GROUP_B,
    FEATURE_GROUP_C,
    FEATURE_GROUP_D,
)

AVAILABILITY_COLUMNS: tuple[str, ...] = (
    "lineup_confirmed",
    "starter_probability",
    "minutes_last_3",
    "minutes_last_5",
    "minutes_trend",
    "bench_probability",
    "captain",
    "suspended_flag",
    "injury_flag",
    "returned_recently",
    "availability_score",
)

PLAYER_BASE = FEATURE_GROUP_A + FEATURE_GROUP_B + FEATURE_GROUP_C
PLAYER_COLUMNS = PLAYER_BASE
PLAYER_LINEUP_COLUMNS = PLAYER_BASE + FEATURE_GROUP_D
PLAYER_AVAILABILITY_COLUMNS = PLAYER_BASE + AVAILABILITY_COLUMNS
PLAYER_LINEUP_AVAILABILITY_COLUMNS = PLAYER_LINEUP_COLUMNS + tuple(
    c for c in AVAILABILITY_COLUMNS if c not in PLAYER_LINEUP_COLUMNS
)
PLAYER_LINEUP_AVAILABILITY_ODDS_COLUMNS = PLAYER_LINEUP_AVAILABILITY_COLUMNS + ("odds_implied_feature",)

FEATURE_GROUPS: dict[str, tuple[str, ...]] = {
    "player": PLAYER_COLUMNS,
    "player_lineup": PLAYER_LINEUP_COLUMNS,
    "player_availability": PLAYER_AVAILABILITY_COLUMNS,
    "player_lineup_availability": PLAYER_LINEUP_AVAILABILITY_COLUMNS,
    "player_lineup_availability_odds": PLAYER_LINEUP_AVAILABILITY_ODDS_COLUMNS,
}

UEFA_LEAGUE_IDS: dict[int, str] = {
    2: "champions_league",
    5: "europa_league",
    2286: "conference_league",
}

BASELINE_54R_UEFA_TOP3 = 0.6429
BASELINE_54Q_UEFA_TOP3 = 0.5658
ELITE_PATH_THRESHOLD = 0.67

VALID_RECOMMENDATIONS = frozenset(
    {
        "GOALSCORER_HIGH_VALUE",
        "GOALSCORER_ELITE_PATH",
        "GOALSCORER_MAXED_OUT",
    }
)

FeatureVerdict = Literal["positive", "neutral", "harmful"]
