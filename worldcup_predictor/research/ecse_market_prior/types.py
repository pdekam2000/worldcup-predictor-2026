"""Shared types for ECSE market prior research."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FavSide = Literal["HOME", "AWAY"]
FavResult = Literal["WIN", "DRAW", "LOSS"]


@dataclass(frozen=True)
class MarketPriorRow:
    row_hash: str
    fixture_date: str
    kickoff_utc: str
    league: str
    country: str
    source_file: str
    home_team: str
    away_team: str
    odds_home: float
    odds_draw: float
    odds_away: float
    p_home: float
    p_draw: float
    p_away: float
    fav_side: FavSide
    p_favorite: float
    p_draw_fav: float
    p_underdog: float
    prob_fav: float
    prob_draw: float
    prob_dog: float
    home_goals: int
    away_goals: int
    raw_score: str
    norm_score: str
    fav_result: FavResult
    btts_actual: int
    over_25_actual: int
    total_goals: int
    winning_margin: int
    segment: str
