"""Margin-normalized implied probabilities and favorite orientation."""

from __future__ import annotations

from typing import Literal

FavSide = Literal["HOME", "AWAY"]
FavResult = Literal["WIN", "DRAW", "LOSS"]


def implied_raw(odds: float | None) -> float | None:
    if odds is None or odds < 1.0:
        return None
    return 1.0 / float(odds)


def margin_normalized_probs(
    odds_home: float, odds_draw: float, odds_away: float
) -> tuple[float, float, float]:
    raw = [1.0 / odds_home, 1.0 / odds_draw, 1.0 / odds_away]
    total = sum(raw)
    return raw[0] / total, raw[1] / total, raw[2] / total


def favorite_side(odds_home: float, odds_away: float) -> FavSide:
    return "HOME" if odds_home <= odds_away else "AWAY"


def favorite_frame_probs(
    odds_home: float, odds_draw: float, odds_away: float
) -> tuple[FavSide, float, float, float, tuple[float, float, float]]:
    p_h, p_d, p_a = margin_normalized_probs(odds_home, odds_draw, odds_away)
    side = favorite_side(odds_home, odds_away)
    if side == "HOME":
        return side, p_h, p_d, p_a, (p_h, p_d, p_a)
    return side, p_a, p_d, p_h, (p_a, p_d, p_h)


def normalize_favorite_score(home_goals: int, away_goals: int, fav_side: FavSide) -> str:
    if fav_side == "HOME":
        return f"{home_goals}-{away_goals}"
    return f"{away_goals}-{home_goals}"


def reorient_score_to_home_away(norm_score: str, fav_side: FavSide) -> str:
    parts = norm_score.split("-", 1)
    if len(parts) != 2:
        return norm_score
    fav_g, dog_g = int(parts[0]), int(parts[1])
    if fav_side == "HOME":
        return f"{fav_g}-{dog_g}"
    return f"{dog_g}-{fav_g}"


def parse_scoreline(scoreline: str) -> tuple[int, int] | None:
    if "-" not in scoreline:
        return None
    try:
        h, a = scoreline.split("-", 1)
        return int(h), int(a)
    except ValueError:
        return None


def favorite_result(home_goals: int, away_goals: int, fav_side: FavSide) -> FavResult:
    if home_goals == away_goals:
        return "DRAW"
    if fav_side == "HOME":
        return "WIN" if home_goals > away_goals else "LOSS"
    return "WIN" if away_goals > home_goals else "LOSS"


def winning_margin(home_goals: int, away_goals: int, fav_side: FavSide) -> int:
    if fav_side == "HOME":
        return home_goals - away_goals
    return away_goals - home_goals


def favorite_margin_abs(home_goals: int, away_goals: int, fav_side: FavSide) -> int:
    return abs(winning_margin(home_goals, away_goals, fav_side))
