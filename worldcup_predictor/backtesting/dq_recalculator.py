"""Recalculate DataQualityReport after enrichment is applied in backtest replay."""
from __future__ import annotations

from worldcup_predictor.domain.intelligence import DataQualityReport, MatchIntelligenceReport

_WEIGHTS_DEFAULT = {
    "home_form": 15,
    "away_form": 15,
    "lineups": 20,
    "fixture_statistics": 15,
    "odds": 15,
    "head_to_head": 10,
    "injuries": 5,
    "referee": 5,
}

_WEIGHTS_NATIONAL = {
    "home_form": 20,
    "away_form": 20,
    "lineups": 10,
    "fixture_statistics": 10,
    "odds": 25,
    "head_to_head": 10,
    "injuries": 3,
    "referee": 2,
}

NATIONAL_COMPETITIONS = {
    "world_cup_2026", "world_cup", "international",
    "wc_qualification_europe", "wc_qualification_asia",
}


def _weights_for_report(report: MatchIntelligenceReport) -> dict[str, int]:
    comp = ""
    if report.fixture:
        comp = str(report.fixture.competition_key or "")
    if comp in NATIONAL_COMPETITIONS:
        return _WEIGHTS_NATIONAL
    return _WEIGHTS_DEFAULT


def recalculate_data_quality(report: MatchIntelligenceReport) -> None:
    """Recalculate data quality after enrichment is applied."""
    available: list[str] = []
    missing: list[str] = []

    if report.home_team and report.home_team.form:
        available.append("home_form")
    else:
        missing.append("home_form")

    if report.away_team and report.away_team.form:
        available.append("away_form")
    else:
        missing.append("away_form")

    lineups = report.lineups or {}
    if lineups.get("available") and lineups.get("items"):
        available.append("lineups")
    else:
        missing.append("lineups")

    stats = report.fixture_statistics or {}
    if stats.get("items"):
        available.append("fixture_statistics")
    else:
        missing.append("fixture_statistics")

    if report.odds and report.odds.available and report.odds.bookmakers:
        available.append("odds")
    else:
        missing.append("odds")

    h2h = report.head_to_head or {}
    if h2h.get("count", 0) > 0:
        available.append("head_to_head")
    else:
        missing.append("head_to_head")

    home_inj = report.home_team and report.home_team.injuries
    away_inj = report.away_team and report.away_team.injuries
    if (home_inj and home_inj.available) or (away_inj and away_inj.available):
        available.append("injuries")
    else:
        missing.append("injuries")

    if report.fixture and report.fixture.referee:
        available.append("referee")
    else:
        missing.append("referee")

    weights = _weights_for_report(report)
    total_max = sum(weights.values())
    earned = sum(weights.get(f, 0) for f in available)
    score = earned / total_max if total_max else 0.0

    report.data_quality = DataQualityReport(
        score=round(score, 2),
        available_fields=sorted(set(available)),
        missing_fields=sorted(set(missing)),
        breakdown=dict(weights),
        breakdown_total=earned,
        breakdown_max=total_max,
        errors=[],
    )