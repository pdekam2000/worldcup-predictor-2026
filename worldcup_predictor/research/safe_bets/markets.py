"""PHASE SAFE-BETS-1 — Market classification and normalization."""

from __future__ import annotations

import re
from typing import Any

PHASE = "SAFE-BETS-1"

ALLOWED_MARKET_TYPES = frozenset(
    {
        "double_chance",
        "team_to_score",
        "goals_ou",
        "btts",
        "corners_ou",
        "team_corners",
        "cards_ou",
        "own_goal",
        "asian_handicap",
        "other_allowed",
    }
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().strip())


def classify_market(market_name: str, selection: str) -> str | None:
    """Return market_type if scannable, else None to skip."""
    n = _norm(market_name)
    s = _norm(selection)

    if "double chance" in n:
        if "corner" in n:
            return None
        return "double_chance"
    if "own goal" in n:
        return "own_goal"
    if "both teams" in n or n == "btts":
        return "btts"
    if "asian handicap" in n or n == "handicap":
        return "asian_handicap"
    if "card" in n and ("over" in s or "under" in s):
        return "cards_ou"
    if "corner" in n:
        if "home corner" in n or "away corner" in n or "team" in n:
            return "team_corners"
        if "over" in s or "under" in s:
            return "corners_ou"
        return None
    if any(x in n for x in ("team score", "to score a goal", "team to score")):
        return "team_to_score"
    if "home team score" in n or "away team score" in n:
        return "team_to_score"
    if ("goals over" in n or "goals over/under" in n or n == "goals over/under") and (
        "first half" not in n and "second half" not in n
    ):
        if re.search(r"over|under", s):
            return "goals_ou"
    if n in {"match winner", "1x2", "match result"}:
        return None
    if "total - home" in n or "total - away" in n:
        if "over" in s or "under" in s:
            return "goals_ou"
    if "handicap result" in n and "asian" not in n:
        return None
    return None


def normalize_market_label(market_name: str, market_type: str) -> str:
    return f"{market_type}:{_norm(market_name)}"


def normalize_selection(selection: str) -> str:
    return _norm(selection).replace(":", "-")


def market_usefulness_bonus(market_type: str) -> float:
    return {
        "double_chance": 8.0,
        "team_to_score": 10.0,
        "goals_ou": 6.0,
        "btts": 6.0,
        "corners_ou": 7.0,
        "team_corners": 5.0,
        "cards_ou": 4.0,
        "own_goal": 3.0,
        "asian_handicap": 5.0,
    }.get(market_type, 0.0)


def is_trivial_trap_market(market_type: str, market_name: str, selection: str) -> tuple[bool, str]:
    """Detect low-value trap markets (not just low odds)."""
    n = _norm(market_name)
    s = _norm(selection)

    if market_type == "goals_ou":
        if re.search(r"over\s*0\.5", s) or s == "over 0.5":
            return True, "trivial_over_0_5_goals"
        if re.search(r"under\s*[5-9]\.5", s):
            return True, "trivial_under_high_goals_line"
    if market_type == "corners_ou":
        if re.search(r"over\s*[0-3](?:\.5)?$", s) or re.search(r"over\s*[0-3]\s*$", s):
            return True, "trivial_over_low_corners"
        if re.search(r"under\s*1[5-9]", s):
            return True, "trivial_under_extreme_corners"
    if "total corners (3 way)" in n:
        return True, "corner_3way_noise"
    if market_type == "team_to_score" and s in {"yes", "no"} and "home" not in n and "away" not in n:
        pass
    if "offsides" in n or "shotongoal" in n.replace(" ", ""):
        return True, "non_core_market"
    return False, ""
