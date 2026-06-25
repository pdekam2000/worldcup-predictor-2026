"""Attach weather intelligence to predictions — Phase 43."""

from __future__ import annotations

import json
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.intelligence.weather_intelligence_engine import build_weather_intelligence


def resolve_weather_from_report(
    report: MatchIntelligenceReport | None,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    _ = settings or get_settings()
    if report is None:
        return build_weather_intelligence(None)
    fixture = report.fixture
    venue = fixture.venue if fixture else None
    kickoff = fixture.kickoff_utc.isoformat() if fixture and fixture.kickoff_utc else None
    weather = report.weather or {}
    if weather.get("available"):
        return build_weather_intelligence(weather, venue=venue, kickoff_utc=kickoff)
    supplemental = (report.supplemental_sources or {}).get("rapid_open_weather") or {}
    rapid = supplemental.get("weather") if isinstance(supplemental, dict) else None
    if isinstance(rapid, dict) and rapid.get("available"):
        return build_weather_intelligence(rapid, venue=venue, kickoff_utc=kickoff)
    return build_weather_intelligence(None, venue=venue, kickoff_utc=kickoff)


def attach_weather_to_prediction(
    prediction: MatchPrediction,
    report: MatchIntelligenceReport | None,
    *,
    settings: Settings | None = None,
) -> MatchPrediction:
    block = resolve_weather_from_report(report, settings=settings)
    prediction.metadata = dict(prediction.metadata or {})
    prediction.metadata["weather_intelligence"] = json.dumps(block, ensure_ascii=False)
    return prediction


def load_weather_from_prediction(prediction: MatchPrediction) -> dict[str, Any] | None:
    raw = (prediction.metadata or {}).get("weather_intelligence")
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(str(raw))
    except (json.JSONDecodeError, TypeError):
        return None
