from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CompetitionType = Literal["tournament", "league", "cup", "friendly"]

DEFAULT_COMPETITION_KEY = "world_cup_2026"


@dataclass(frozen=True)
class CompetitionConfig:
    """Competition metadata — registry entry for multi-league support (Phase 39)."""

    key: str
    name: str
    league_id: int
    season: int
    provider: str = "api-football"
    compensation_type: CompetitionType = "tournament"
    country: str = ""
    enabled: bool = True
    learning_profile_key: str = ""
    supports_groups: bool = False
    supports_table: bool = False
    supports_knockout: bool = False
    default_seasons: tuple[int, ...] = ()
    notes: str = ""

    @property
    def display_name(self) -> str:
        return self.name

    @property
    def api_football_league_id(self) -> int:
        return self.league_id

    @property
    def league_id_configured(self) -> bool:
        return self.league_id > 0

    def fixture_query_params(self) -> dict[str, int]:
        """API-Football fixtures query params (backward-compatible with Phase 1–14 clients)."""
        params: dict[str, int] = {}
        if self.api_football_league_id:
            params["league"] = self.api_football_league_id
        if self.season:
            params["season"] = self.season
        return params

    def standings_query_params(self) -> dict[str, int]:
        """API-Football standings query params."""
        params: dict[str, int] = {}
        if self.api_football_league_id:
            params["league"] = self.api_football_league_id
        if self.season:
            params["season"] = self.season
        return params

    def fixture_params(self) -> dict[str, int | str]:
        """Legacy alias — prefer fixture_query_params()."""
        return self.fixture_query_params()


WORLD_CUP_2026 = CompetitionConfig(
    key="world_cup_2026",
    name="FIFA World Cup 2026",
    league_id=1,
    season=2026,
    country="International",
    enabled=True,
    learning_profile_key="world_cup",
    compensation_type="tournament",
    supports_groups=True,
    supports_table=False,
    supports_knockout=True,
    default_seasons=(2018, 2022),
    notes="Default tournament mode — group tables and knockout stages.",
)

PREMIER_LEAGUE = CompetitionConfig(
    key="premier_league",
    name="Premier League",
    league_id=39,
    season=2024,
    country="England",
    enabled=True,
    learning_profile_key="premier_league",
    compensation_type="league",
    supports_groups=False,
    supports_table=True,
    supports_knockout=False,
    default_seasons=(2021, 2022, 2023, 2024, 2025),
    notes="English top flight — league table standings.",
)

BUNDESLIGA = CompetitionConfig(
    key="bundesliga",
    name="Bundesliga",
    league_id=78,
    season=2024,
    country="Germany",
    enabled=True,
    learning_profile_key="bundesliga",
    compensation_type="league",
    supports_groups=False,
    supports_table=True,
    supports_knockout=False,
    default_seasons=(2021, 2022, 2023, 2024, 2025),
    notes="German top flight — league table standings.",
)

LA_LIGA = CompetitionConfig(
    key="la_liga",
    name="La Liga",
    league_id=140,
    season=2024,
    country="Spain",
    enabled=True,
    learning_profile_key="la_liga",
    compensation_type="league",
    supports_groups=False,
    supports_table=True,
    supports_knockout=False,
    default_seasons=(2021, 2022, 2023, 2024, 2025),
    notes="Spanish top flight — league table standings.",
)

SERIE_A = CompetitionConfig(
    key="serie_a",
    name="Serie A",
    league_id=135,
    season=2024,
    country="Italy",
    enabled=True,
    learning_profile_key="serie_a",
    compensation_type="league",
    supports_groups=False,
    supports_table=True,
    supports_knockout=False,
    default_seasons=(2021, 2022, 2023, 2024, 2025),
    notes="Italian top flight — league table standings.",
)

LIGUE_1 = CompetitionConfig(
    key="ligue_1",
    name="Ligue 1",
    league_id=61,
    season=2024,
    country="France",
    enabled=True,
    learning_profile_key="ligue_1",
    compensation_type="league",
    supports_groups=False,
    supports_table=True,
    supports_knockout=False,
    default_seasons=(2021, 2022, 2023, 2024, 2025),
    notes="French top flight — league table standings.",
)

CHAMPIONS_LEAGUE = CompetitionConfig(
    key="champions_league",
    name="UEFA Champions League",
    league_id=2,
    season=2024,
    country="Europe",
    enabled=True,
    learning_profile_key="champions_league",
    compensation_type="cup",
    supports_groups=True,
    supports_table=False,
    supports_knockout=True,
    default_seasons=(2021, 2022, 2023, 2024, 2025),
    notes="UEFA Champions League — group and knockout stages.",
)

EUROPA_LEAGUE = CompetitionConfig(
    key="europa_league",
    name="UEFA Europa League",
    league_id=3,
    season=2024,
    country="Europe",
    enabled=True,
    learning_profile_key="europa_league",
    compensation_type="cup",
    supports_groups=True,
    supports_table=False,
    supports_knockout=True,
    default_seasons=(2021, 2022, 2023, 2024, 2025),
    notes="UEFA Europa League — group and knockout stages.",
)

CONFERENCE_LEAGUE = CompetitionConfig(
    key="conference_league",
    name="UEFA Conference League",
    league_id=848,
    season=2024,
    country="Europe",
    enabled=True,
    learning_profile_key="conference_league",
    compensation_type="cup",
    supports_groups=True,
    supports_table=False,
    supports_knockout=True,
    default_seasons=(2021, 2022, 2023, 2024, 2025),
    notes="UEFA Conference League — group and knockout stages.",
)

INTERNATIONAL_FRIENDLIES = CompetitionConfig(
    key="international_friendlies",
    name="International Friendlies",
    league_id=667,
    season=2024,
    country="International",
    enabled=False,
    learning_profile_key="international_friendlies",
    compensation_type="friendly",
    supports_groups=False,
    supports_table=False,
    supports_knockout=False,
    default_seasons=(2022, 2023, 2024),
    notes="Friendly fixtures — disabled in European league mode.",
)

COMPETITION_REGISTRY: dict[str, CompetitionConfig] = {
    WORLD_CUP_2026.key: WORLD_CUP_2026,
    PREMIER_LEAGUE.key: PREMIER_LEAGUE,
    BUNDESLIGA.key: BUNDESLIGA,
    LA_LIGA.key: LA_LIGA,
    SERIE_A.key: SERIE_A,
    LIGUE_1.key: LIGUE_1,
    CHAMPIONS_LEAGUE.key: CHAMPIONS_LEAGUE,
    EUROPA_LEAGUE.key: EUROPA_LEAGUE,
    CONFERENCE_LEAGUE.key: CONFERENCE_LEAGUE,
    INTERNATIONAL_FRIENDLIES.key: INTERNATIONAL_FRIENDLIES,
}

_KEY_ALIASES: dict[str, str] = {
    "worldcup_2026": WORLD_CUP_2026.key,
    "world-cup-2026": WORLD_CUP_2026.key,
    "world_cup": WORLD_CUP_2026.key,
}


def normalize_competition_key(key: str | None) -> str:
    if not key:
        return DEFAULT_COMPETITION_KEY
    normalized = key.strip().lower().replace("-", "_")
    return _KEY_ALIASES.get(normalized, normalized)


def get_competition(key: str | None = None) -> CompetitionConfig:
    comp_key = normalize_competition_key(key)
    if comp_key not in COMPETITION_REGISTRY:
        known = ", ".join(sorted(COMPETITION_REGISTRY))
        raise KeyError(f"Unknown competition: {key!r}. Known: {known}")
    return COMPETITION_REGISTRY[comp_key]


def list_competition_keys(*, enabled_only: bool = False) -> list[str]:
    keys = sorted(COMPETITION_REGISTRY.keys())
    if not enabled_only:
        return keys
    return [k for k in keys if COMPETITION_REGISTRY[k].enabled]
