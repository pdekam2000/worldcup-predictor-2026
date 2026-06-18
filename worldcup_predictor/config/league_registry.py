"""Phase 39 — European league registry helpers (extends competitions.py)."""

from __future__ import annotations

from worldcup_predictor.config.competitions import (
    COMPETITION_REGISTRY,
    CompetitionConfig,
    DEFAULT_COMPETITION_KEY,
    get_competition,
    list_competition_keys,
)

COMPETITION_MODE_WORLD_CUP = "world_cup"
COMPETITION_MODE_EUROPEAN = "european_leagues"

EUROPEAN_LEAGUE_KEYS: tuple[str, ...] = (
    "premier_league",
    "la_liga",
    "bundesliga",
    "serie_a",
    "ligue_1",
    "champions_league",
    "europa_league",
    "conference_league",
)

LEARNING_PROFILE_KEYS: tuple[str, ...] = (
    "world_cup",
    *EUROPEAN_LEAGUE_KEYS,
)


def learning_profile_for(competition_key: str | None) -> str:
    comp = get_competition(competition_key)
    return comp.learning_profile_key or comp.key


def list_enabled_competitions(*, european_only: bool = False) -> list[CompetitionConfig]:
    items = [COMPETITION_REGISTRY[k] for k in list_competition_keys()]
    enabled = [c for c in items if c.enabled]
    if european_only:
        return [c for c in enabled if c.key in EUROPEAN_LEAGUE_KEYS]
    return enabled


def list_enabled_european_leagues() -> list[CompetitionConfig]:
    return list_enabled_competitions(european_only=True)


def resolve_competition_by_league_id(league_id: int) -> CompetitionConfig | None:
    for comp in COMPETITION_REGISTRY.values():
        if comp.league_id == league_id and comp.enabled:
            return comp
    return None


def default_competition_for_mode(mode: str) -> str:
    if mode == COMPETITION_MODE_EUROPEAN:
        return EUROPEAN_LEAGUE_KEYS[0]
    return DEFAULT_COMPETITION_KEY


def season_options_for(competition_key: str) -> list[int]:
    comp = get_competition(competition_key)
    if comp.default_seasons:
        return list(comp.default_seasons)
    return [comp.season]
