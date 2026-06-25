"""Classify goalscorer odds rows into player vs team markets."""

from __future__ import annotations

import re
from typing import Any

from worldcup_predictor.egie.goalscorer_odds_acquisition.models import MarketKind

_PLAYER_MARKET_PATTERNS = (
    re.compile(r"^goalscorers?$", re.I),
    re.compile(r"^(anytime|first|last)\s+goal\s+scorer$", re.I),
)

_TEAM_SCOPED_PLAYER_PATTERNS = (
    re.compile(r"^(home|away)\s+(anytime|first|last)\s+goal\s+scorer$", re.I),
)

_TEAM_MARKET_PATTERNS = (
    re.compile(r"team\s+goalscorer", re.I),
)

_OTHER_GOALSCORER_PATTERNS = (
    re.compile(r"player\s+to\s+score", re.I),
    re.compile(r"to\s+score\s+anytime", re.I),
)


def classify_market(market_name: str, *, source: str = "") -> MarketKind:
    """Return market kind for a goalscorer-related market name."""
    name = (market_name or "").strip()
    if not name:
        return "other_goalscorer_related"

    if any(p.search(name) for p in _TEAM_MARKET_PATTERNS):
        return "team_goalscorer"

    if any(p.search(name) for p in _TEAM_SCOPED_PLAYER_PATTERNS):
        return "player_goalscorer_team_scoped"

    if any(p.search(name) for p in _PLAYER_MARKET_PATTERNS):
        return "player_goalscorer"

    if any(p.search(name) for p in _OTHER_GOALSCORER_PATTERNS):
        return "player_goalscorer"

    # Sportmonks uses market_description e.g. "Goalscorers"
    if name.lower() == "goalscorers":
        return "player_goalscorer"

    return "other_goalscorer_related"


def is_goalscorer_market_text(text: str) -> bool:
    """Broad detector for inventory scans."""
    if not text:
        return False
    patterns = (
        r"goal\s*scor",
        r"player\s+to\s+score",
        r"anytime\s+goal",
        r"first\s+goalscorer",
        r"last\s+goalscorer",
        r"team\s+goalscorer",
    )
    return any(re.search(p, text, re.I) for p in patterns)


def split_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Split normalized rows by market kind."""
    out: dict[str, list[dict[str, Any]]] = {
        "player_goalscorer": [],
        "team_goalscorer": [],
        "player_goalscorer_team_scoped": [],
        "other_goalscorer_related": [],
    }
    for row in rows:
        kind = classify_market(str(row.get("market") or row.get("market_name") or ""), source=str(row.get("source") or ""))
        out[kind].append(row)
    return out
