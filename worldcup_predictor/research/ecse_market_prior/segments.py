"""Competition segment labels for market prior pooling."""

from __future__ import annotations

import re


DOMESTIC_CODES = frozenset(
    {
        "EN1", "EN2", "EN3", "EN4", "SP1", "SP2", "IT1", "IT2", "FR1", "FR2",
        "DE1", "DE2", "NL1", "BE1", "PT1", "TR1", "GR1", "RU1", "SC1", "PL1",
        "US1", "US2", "BR1", "BR2", "JP1", "JP2", "MX1", "AR1", "AU1", "CN1",
    }
)


def competition_segment(league: str, source_file: str = "", country: str = "") -> str:
    league_u = (league or "").upper().strip()
    text = f"{league_u} {source_file} {country}".lower()
    if any(x in text for x in ("world cup", "worldcup", "fifa", "wc ")):
        return "world_cup_major"
    if any(x in text for x in ("euro ", "euro20", "copa america", "nations league", "qualif", "international")):
        return "national_teams"
    if any(x in text for x in ("champions", "europa", "conference", "uefa", "cl1", "el1")):
        return "uefa_club"
    if league_u in DOMESTIC_CODES or re.match(r"^[A-Z]{2}\d$", league_u):
        return "domestic_leagues"
    if "football-" in source_file.lower() and not any(
        x in source_file.lower() for x in ("champions", "europa", "world")
    ):
        return "domestic_leagues"
    return "global"
