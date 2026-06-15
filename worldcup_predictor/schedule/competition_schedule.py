from __future__ import annotations

from worldcup_predictor.competition.competition_service import CompetitionService
from worldcup_predictor.config.settings import Settings
from worldcup_predictor.schedule.worldcup_schedule_service import WorldCupScheduleService


def create_schedule_service(
    settings: Settings,
    *,
    competition_key: str | None = None,
) -> WorldCupScheduleService:
    """Build a schedule service configured for the requested competition."""
    service = CompetitionService()
    comp = service.get_competition(competition_key)
    features = service.get_supported_features(comp.key)
    return WorldCupScheduleService(
        settings,
        competition=comp,
        supports_groups=bool(features["supports_groups"]),
        supports_table=bool(features["supports_table"]),
        supports_knockout=bool(features["supports_knockout"]),
    )
