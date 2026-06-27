"""Classify World Cup fixtures — finals vs qualifiers (data labels only)."""

from __future__ import annotations

from worldcup_predictor.egie.world_cup.config import (
    COMPETITION_TYPE_FINALS,
    COMPETITION_TYPE_FRIENDLY,
    COMPETITION_TYPE_OTHER,
    COMPETITION_TYPE_QUALIFIER,
)

_QUALIFIER_MARKERS = (
    "qualif",
    "qualification",
    "preliminary",
    "play-off",
    "playoff",
    "inter-confederation",
    "inter confederation",
)
_FRIENDLY_MARKERS = ("friendly", "friendlies")


def classify_fixture_competition_type(
    *,
    round_name: str | None = None,
    group_name: str | None = None,
    league_id: int | None = None,
    competition_key: str | None = None,
) -> str:
    text = " ".join(
        str(x or "").lower()
        for x in (round_name, group_name, competition_key)
    )
    if any(m in text for m in _FRIENDLY_MARKERS):
        return COMPETITION_TYPE_FRIENDLY
    if any(m in text for m in _QUALIFIER_MARKERS):
        return COMPETITION_TYPE_QUALIFIER
    if league_id == 1 or "world cup" in text or "world_cup" in text:
        return COMPETITION_TYPE_FINALS
    return COMPETITION_TYPE_OTHER
