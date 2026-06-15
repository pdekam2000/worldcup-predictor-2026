"""Weighted data-quality scoring for MatchIntelligenceReport (0–100)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.data_quality.transparency import (
    CORE_WEIGHTS,
    LIVE_WEIGHTS,
    SUPPLEMENTAL_WEIGHTS,
    DataQualityDetail,
)
from worldcup_predictor.domain.fixture import Fixture
from worldcup_predictor.domain.intelligence import MatchIntelligenceReport, TeamIntelligence

# Backward-compatible alias
WEIGHTS = CORE_WEIGHTS


class DataQualityBreakdown:
    """Legacy wrapper — prefer DataQualityDetail from explain_data_quality()."""

    def __init__(self, detail: DataQualityDetail) -> None:
        self._detail = detail

    @property
    def components(self) -> dict[str, int]:
        return self._detail.components

    @property
    def max_total(self) -> int:
        return self._detail.max_total

    @property
    def total(self) -> int:
        return self._detail.display_total

    @property
    def score_ratio(self) -> float:
        return self._detail.score_ratio

    def to_dict(self) -> dict[str, Any]:
        return {
            "components": self.components,
            "total": self.total,
            "max_total": self.max_total,
            "score_ratio": self.score_ratio,
            "pre_match_total": self._detail.pre_match_total,
            "live_total": self._detail.live_total,
            "post_match_total": self._detail.post_match_total,
        }


def _team_has_form(team: TeamIntelligence, recent: list[dict[str, Any]] | None) -> bool:
    if team.form:
        return True
    return bool(recent)


def _team_has_stats(team: TeamIntelligence, fixture_stats: dict[str, Any] | None) -> bool:
    if team.statistics:
        return True
    if fixture_stats and fixture_stats.get("items"):
        return True
    return False


def score_data_quality_components(
    report: MatchIntelligenceReport,
) -> tuple[dict[str, int], dict[str, int]]:
    """Score each component from real loaded data only. Returns (points, max_points)."""
    fixture: Fixture | None = report.fixture
    components: dict[str, int] = {key: 0 for key in CORE_WEIGHTS}
    component_max: dict[str, int] = dict(CORE_WEIGHTS)
    for key, max_pts in LIVE_WEIGHTS.items():
        components[key] = 0
        component_max[key] = max_pts
    for key, max_pts in SUPPLEMENTAL_WEIGHTS.items():
        components[key] = 0
        component_max[key] = max_pts

    if fixture and fixture.id and fixture.home_team and fixture.away_team:
        components["fixture_identity"] = CORE_WEIGHTS["fixture_identity"]
    if fixture and fixture.home_team_id and fixture.away_team_id:
        components["team_ids"] = CORE_WEIGHTS["team_ids"]

    if report.standings_context and report.standings_context.get("available"):
        components["standings_context"] = CORE_WEIGHTS["standings_context"]

    home_recent = report.home_recent_fixtures or []
    away_recent = report.away_recent_fixtures or []
    if _team_has_form(report.home_team, home_recent) and _team_has_form(report.away_team, away_recent):
        components["recent_form"] = CORE_WEIGHTS["recent_form"]
    elif _team_has_form(report.home_team, home_recent) or _team_has_form(report.away_team, away_recent):
        components["recent_form"] = CORE_WEIGHTS["recent_form"] // 2

    has_injury_data = bool(
        (report.home_team.injuries and report.home_team.injuries.players)
        or (report.away_team.injuries and report.away_team.injuries.players)
    )
    if "injuries" not in report.missing_data and has_injury_data:
        components["injuries"] = CORE_WEIGHTS["injuries"]

    if report.odds and report.odds.available:
        components["odds"] = CORE_WEIGHTS["odds"]

    if _team_has_stats(report.home_team, report.fixture_statistics) or _team_has_stats(
        report.away_team, report.fixture_statistics
    ):
        components["stats"] = CORE_WEIGHTS["stats"]

    if report.lineups and report.lineups.get("available"):
        components["lineups"] = CORE_WEIGHTS["lineups"]

    if report.weather and report.weather.get("available"):
        components["weather"] = CORE_WEIGHTS["weather"]

    if report.referee:
        components["referee"] = CORE_WEIGHTS["referee"]

    # Live / post-match components — only when data exists
    if report.fixture_events:
        components["fixture_events"] = LIVE_WEIGHTS["fixture_events"]
    live_stats = report.fixture_statistics or {}
    if live_stats.get("items") and live_stats.get("source") in (
        "rapid_football_stats",
        "live",
        "api_football",
    ):
        status = (getattr(fixture, "status", None) or "NS").upper() if fixture else "NS"
        if status not in {"NS", "TBD", "PST", "CANC"}:
            components["match_statistics_live"] = LIVE_WEIGHTS["match_statistics_live"]

    rapid = (report.supplemental_sources or {}).get("rapid_football_stats") or {}
    rapid_xg = (report.supplemental_sources or {}).get("rapid_xg_statistics") or {}
    rapid_weather = (report.supplemental_sources or {}).get("rapid_open_weather") or {}

    has_xg = bool(rapid.get("xg") or rapid.get("npxg"))
    has_xg = has_xg or bool(
        rapid_xg.get("xg") or rapid_xg.get("npxg") or rapid_xg.get("fixture_detail")
    )
    if has_xg:
        if components["stats"] < CORE_WEIGHTS["stats"]:
            components["stats"] = CORE_WEIGHTS["stats"]
        components["supplemental_xg"] = SUPPLEMENTAL_WEIGHTS["supplemental_xg"]

    if rapid.get("player_statistics"):
        components["supplemental_player_stats"] = SUPPLEMENTAL_WEIGHTS["supplemental_player_stats"]

    if rapid.get("team_squad"):
        components["supplemental_squad"] = SUPPLEMENTAL_WEIGHTS["supplemental_squad"]

    if rapid.get("prematch_odds") or rapid.get("live_odds") or rapid.get("historical_odds"):
        if components["odds"] < CORE_WEIGHTS["odds"]:
            components["odds"] = CORE_WEIGHTS["odds"]
        components["supplemental_odds"] = SUPPLEMENTAL_WEIGHTS["supplemental_odds"]

    if rapid_xg.get("upcoming_odds"):
        if components["odds"] < CORE_WEIGHTS["odds"]:
            components["odds"] = CORE_WEIGHTS["odds"]
        components["supplemental_odds"] = max(
            components.get("supplemental_odds", 0),
            SUPPLEMENTAL_WEIGHTS["supplemental_odds"],
        )

    if rapid_weather.get("weather") and not components["weather"]:
        components["weather"] = CORE_WEIGHTS["weather"]
        components["supplemental_weather"] = SUPPLEMENTAL_WEIGHTS["supplemental_weather"]
    elif (
        report.weather
        and report.weather.get("available")
        and report.weather.get("provider") == "rapid_open_weather"
    ):
        components["supplemental_weather"] = SUPPLEMENTAL_WEIGHTS["supplemental_weather"]

    return components, component_max


def compute_data_quality_breakdown(report: MatchIntelligenceReport) -> DataQualityBreakdown:
    from worldcup_predictor.data_quality.transparency import explain_data_quality

    detail = explain_data_quality(report)
    return DataQualityBreakdown(detail)


def form_string_from_recent(recent: list[dict[str, Any]], team_id: int) -> list[str]:
    """Build W/D/L form from API-Football recent fixture payloads."""
    letters: list[str] = []
    for item in recent[:10]:
        goals = item.get("goals", {}) or {}
        teams = item.get("teams", {}) or {}
        home = teams.get("home", {}) or {}
        away = teams.get("away", {}) or {}
        home_id = home.get("id")
        away_id = away.get("id")
        home_g = goals.get("home")
        away_g = goals.get("away")
        if home_g is None or away_g is None:
            continue
        if team_id == home_id:
            if home_g > away_g:
                letters.append("W")
            elif home_g < away_g:
                letters.append("L")
            else:
                letters.append("D")
        elif team_id == away_id:
            if away_g > home_g:
                letters.append("W")
            elif away_g < home_g:
                letters.append("L")
            else:
                letters.append("D")
    return letters
