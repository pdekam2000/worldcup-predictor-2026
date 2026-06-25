"""UEFA club league definitions — Sportmonks league ids (Euro Club Tournaments plan)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UefaClubLeague:
    key: str
    name: str
    sportmonks_league_id: int
    priority: int


UEFA_CLUB_LEAGUES: tuple[UefaClubLeague, ...] = (
    UefaClubLeague("champions_league", "Champions League", 2, 1),
    UefaClubLeague("europa_league", "Europa League", 5, 2),
    UefaClubLeague("conference_league", "Europa Conference League", 2286, 3),
    UefaClubLeague("uefa_super_cup", "UEFA Super Cup", 1326, 4),
)

LEAGUE_ID_TO_KEY: dict[int, str] = {lg.sportmonks_league_id: lg.key for lg in UEFA_CLUB_LEAGUES}

# Full Sportmonks includes for Phase API-H ingest (verified on CL 168925).
UEFA_FULL_INCLUDES = (
    "participants;scores;state;events.type;events.period;statistics.type;"
    "lineups.player;lineups.details.type;formations;xGFixture.type;pressure;"
    "odds.bookmaker;odds.market;predictions.type;form"
)

DATA_DIR = "data/egie/uefa_club"
RAW_CACHE_DIR = f"{DATA_DIR}/raw"
SURVIVAL_DATASET_PATH = f"{DATA_DIR}/uefa_survival_dataset.parquet"
