"""PHASE EURO-A — European fixture feed registry (data import only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from worldcup_predictor.config.competitions import (
    CompetitionConfig,
    get_competition,
    normalize_competition_key,
)
from worldcup_predictor.schedule.season_resolver import resolve_active_season

ProviderName = Literal["api-football"]
TimezonePolicy = Literal["utc_storage"]


@dataclass(frozen=True)
class EuroFeedSpec:
    """Per-competition feed metadata for EURO-A import/backfill."""

    competition_key: str
    provider: ProviderName
    provider_league_id: int
    provider_season_id: int | None
    timezone_policy: TimezonePolicy
    supports_fixtures: bool
    supports_results: bool
    supports_odds: bool
    supports_ecse: bool
    supports_wde: bool
    sportmonks_league_id: int | None = None
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "competition_key": self.competition_key,
            "provider": self.provider,
            "provider_league_id": self.provider_league_id,
            "provider_season_id": self.provider_season_id,
            "timezone_policy": self.timezone_policy,
            "supports_fixtures": self.supports_fixtures,
            "supports_results": self.supports_results,
            "supports_odds": self.supports_odds,
            "supports_ecse": self.supports_ecse,
            "supports_wde": self.supports_wde,
            "sportmonks_league_id": self.sportmonks_league_id,
            "notes": self.notes,
        }


# Sportmonks IDs for reference only — live enrichment remains WC-scoped elsewhere.
_SPORTMONKS_LEAGUE_IDS: dict[str, int] = {
    "premier_league": 8,
    "bundesliga": 82,
    "champions_league": 2,
    "europa_league": 5,
    "conference_league": 2286,
}

EURO_A_TARGET_KEYS: tuple[str, ...] = (
    "premier_league",
    "bundesliga",
    "champions_league",
    "europa_league",
    "conference_league",
)

UEFA_CUP_KEYS: tuple[str, ...] = (
    "champions_league",
    "europa_league",
    "conference_league",
)


def _spec_for(comp: CompetitionConfig) -> EuroFeedSpec:
    season = comp.season
    if comp.default_seasons:
        season = comp.default_seasons[-1]
    return EuroFeedSpec(
        competition_key=comp.key,
        provider="api-football",
        provider_league_id=comp.league_id,
        provider_season_id=season,
        timezone_policy="utc_storage",
        supports_fixtures=comp.league_id_configured,
        supports_results=True,
        supports_odds=True,
        supports_ecse=True,
        supports_wde=True,
        sportmonks_league_id=_SPORTMONKS_LEAGUE_IDS.get(comp.key),
        notes=comp.notes,
    )


def get_euro_feed_spec(competition_key: str) -> EuroFeedSpec:
    key = normalize_competition_key(competition_key)
    if key not in EURO_A_TARGET_KEYS:
        raise KeyError(f"Not an EURO-A target competition: {competition_key!r}")
    return _spec_for(get_competition(key))


def list_euro_feed_specs() -> list[EuroFeedSpec]:
    return [get_euro_feed_spec(k) for k in EURO_A_TARGET_KEYS]


def resolve_provider_season(competition_key: str, *, settings=None) -> int:
    """Active API-Football season for imports (provider probe when configured)."""
    return resolve_active_season(competition_key, settings=settings)


def competition_type_for(comp: CompetitionConfig) -> str:
    if comp.compensation_type == "league":
        return "league"
    if comp.compensation_type == "cup":
        return "cup"
    if comp.compensation_type == "friendly":
        return "friendly"
    return "tournament"
