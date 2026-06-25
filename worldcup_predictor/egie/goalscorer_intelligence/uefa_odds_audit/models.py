"""Phase 54Q-1 UEFA goalscorer odds audit models."""

from __future__ import annotations

from typing import Literal

VALID_RECOMMENDATIONS = frozenset(
    {
        "EXPAND_UEFA_GOALSCORER_ODDS",
        "MODEL_LIMITED",
        "BOTH_LIMITED",
        "GOALSCORER_ALREADY_MAXED",
    }
)

UEFA_LEAGUE_IDS: dict[int, str] = {
    2: "champions_league",
    5: "europa_league",
    2286: "conference_league",
}

WC_LEAGUE_ID = 732

CoverageVerdict = Literal["A_model", "B_odds", "C_both"]
