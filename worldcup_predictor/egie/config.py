"""EGIE ingest manifest and provider role configuration."""

from __future__ import annotations

from dataclasses import dataclass

from worldcup_predictor.config.competitions import PREMIER_LEAGUE, get_competition

EGIE_VERSION = "egie_v0.1_phase1ab"
EGIE_PHASE = "1B"

PROVIDER_API_FOOTBALL = "api_football"
PROVIDER_SPORTMONKS = "sportmonks"

# API-Football — authoritative in EGIE Phase 1B
API_FOOTBALL_RESOURCE_TYPES: tuple[str, ...] = (
    "fixtures",
    "events",  # goals + cards
    "lineups",
    "injuries",
    "standings",
    "fixture_statistics",
)

# Sportmonks — schema-ready for EGIE 1C (not ingested in 1B)
SPORTMONKS_RESOURCE_TYPES: tuple[str, ...] = (
    "xg",
    "pressure_index",
    "news",
    "player_statistics",
    "team_statistics",
    "fixture_statistics",
    "odds",
    "predictions",
)

ALL_EGIE_RESOURCE_TYPES: tuple[str, ...] = API_FOOTBALL_RESOURCE_TYPES + SPORTMONKS_RESOURCE_TYPES


@dataclass(frozen=True)
class EgieIngestJobSpec:
    """Manifest entry for one competition ingest job."""

    job_key: str
    provider: str
    competition_key: str
    league_id: int
    season: int
    resource_types: tuple[str, ...]
    notes: str = ""


PREMIER_LEAGUE_API_FOOTBALL_JOB = EgieIngestJobSpec(
    job_key="api_football_premier_league",
    provider=PROVIDER_API_FOOTBALL,
    competition_key=PREMIER_LEAGUE.key,
    league_id=PREMIER_LEAGUE.league_id,
    season=PREMIER_LEAGUE.season,
    resource_types=API_FOOTBALL_RESOURCE_TYPES,
    notes="Phase 1B — fixtures, events, lineups, injuries, standings, fixture statistics.",
)

INGEST_JOB_REGISTRY: dict[str, EgieIngestJobSpec] = {
    PREMIER_LEAGUE_API_FOOTBALL_JOB.job_key: PREMIER_LEAGUE_API_FOOTBALL_JOB,
}


def get_ingest_job(job_key: str) -> EgieIngestJobSpec:
    spec = INGEST_JOB_REGISTRY.get(job_key)
    if spec is None:
        raise KeyError(f"Unknown EGIE ingest job: {job_key}")
    return spec


def resolve_competition_season(competition_key: str, season: int | None = None) -> tuple[str, int, int]:
    comp = get_competition(competition_key)
    if comp is None:
        raise ValueError(f"Unknown competition_key: {competition_key}")
    use_season = int(season if season is not None else comp.season)
    return comp.key, comp.league_id, use_season
