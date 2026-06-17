from __future__ import annotations

from worldcup_predictor.competition.competition_service import CompetitionService
from worldcup_predictor.config.settings import Settings
from worldcup_predictor.schedule.worldcup_schedule_service import WorldCupScheduleService

__all__ = ["create_schedule_service", "build_schedule_service"]


def create_schedule_service(
    settings: Settings,
    *,
    competition_key: str | None = None,
    season: int | None = None,
) -> WorldCupScheduleService:
    """Build a schedule service configured for the requested competition."""
    from dataclasses import replace

    service = CompetitionService()
    comp = service.get_competition(competition_key)
    if season is not None:
        comp = replace(comp, season=season)
    features = service.get_supported_features(comp.key)
    return WorldCupScheduleService(
        settings,
        competition=comp,
        supports_groups=bool(features["supports_groups"]),
        supports_table=bool(features["supports_table"]),
        supports_knockout=bool(features["supports_knockout"]),
    )


def build_schedule_service(
    settings: Settings,
    competition_key: str | None = None,
    season: int | None = None,
) -> WorldCupScheduleService:
    """Create schedule service with optional season override (GUI / hot-reload safe)."""
    service = create_schedule_service(settings, competition_key=competition_key)
    if season is not None:
        if hasattr(service, "season"):
            service.season = season
        elif hasattr(service, "set_season"):
            service.set_season(season)
    return service
