from __future__ import annotations

from worldcup_predictor.config.settings import Settings
from worldcup_predictor.schedule.worldcup_schedule_service import WorldCupScheduleService


def load_tournament_context(context, settings: Settings | None = None) -> None:
    """Load tournament overview into agent context if not already present."""
    if context.shared.get("tournament_context"):
        return
    active_settings = settings or context.settings
    service = WorldCupScheduleService(active_settings)
    overview = service.get_tournament_overview()
    context.shared["tournament_context"] = overview
    context.shared["schedule_health"] = overview.health


def fixture_tournament_context(context, fixture_id: int) -> dict[str, object]:
    overview = context.shared.get("tournament_context")
    if overview is None:
        load_tournament_context(context)
        overview = context.shared.get("tournament_context")
    if overview is None:
        return {}
    return overview.context_for_fixture(fixture_id)
