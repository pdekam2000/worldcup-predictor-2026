"""Canonical specialist status reasons for UI and API transparency."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from worldcup_predictor.domain.intelligence import MatchIntelligenceReport

PROVIDER_NOT_CONFIGURED = "provider_not_configured"
DATA_NOT_PUBLISHED_YET = "data_not_published_yet"
MISSING_REQUIRED_FIXTURE_FIELDS = "missing_required_fixture_fields"
MISSING_LEAGUE_ID = "missing_league_id"
CACHE_HIT = "cache_hit"
LIVE_DATA_AVAILABLE = "live_data_available"
HEURISTIC_PARTIAL = "heuristic_partial"


def endpoint_skip_reason(report: MatchIntelligenceReport | None, endpoint: str) -> str | None:
    if report is None or report.api_inspection is None:
        return None
    for ep in report.api_inspection.endpoints:
        if ep.endpoint == endpoint and ep.skip_reason:
            return ep.skip_reason
    return None


def injuries_status_reason(report: MatchIntelligenceReport) -> str | None:
    skip = endpoint_skip_reason(report, "injuries")
    if skip:
        return skip
    if "injuries" in (report.missing_data or []):
        return DATA_NOT_PUBLISHED_YET
    if report.home_team.injuries and report.home_team.injuries.available:
        src = report.home_team.injuries.source
        if src == "cache":
            return CACHE_HIT
        if src in ("live", "api-football"):
            return LIVE_DATA_AVAILABLE
    return None


def weather_status_reason(report: MatchIntelligenceReport, *, provider_configured: bool) -> str:
    weather = report.weather or {}
    if weather.get("available"):
        src = str(weather.get("source") or weather.get("provider") or "")
        if src == "cache" or weather.get("from_cache"):
            return CACHE_HIT
        return LIVE_DATA_AVAILABLE
    if not provider_configured:
        return PROVIDER_NOT_CONFIGURED
    return DATA_NOT_PUBLISHED_YET


def lineup_status_reason(report: MatchIntelligenceReport) -> str | None:
    lineups = report.lineups or {}
    if lineups.get("skipped") == "far_from_kickoff":
        return DATA_NOT_PUBLISHED_YET
    items = lineups.get("items") or []
    if items:
        return LIVE_DATA_AVAILABLE if not report.is_placeholder else HEURISTIC_PARTIAL
    if not report.fixture or not report.fixture.home_team_id:
        return MISSING_REQUIRED_FIXTURE_FIELDS
    return DATA_NOT_PUBLISHED_YET
