"""National team intelligence orchestrator (Phase 32B)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.intelligence.national_team.consensus_engine import consensus_strength_score
from worldcup_predictor.intelligence.national_team.data_resolver import resolve_match_history
from worldcup_predictor.intelligence.national_team.form_engine import (
    build_team_form_metrics,
    national_form_score,
)
from worldcup_predictor.intelligence.national_team.h2h_engine import national_h2h_score
from worldcup_predictor.intelligence.national_team.injury_impact_engine import injury_impact_score
from worldcup_predictor.intelligence.national_team.squad_strength_engine import squad_strength_score

SUPPLEMENTAL_KEY = "national_team_intelligence"


def is_world_cup_report(report: MatchIntelligenceReport) -> bool:
    if report.fixture and getattr(report.fixture, "competition_key", None):
        return str(report.fixture.competition_key) == "world_cup_2026"
    return True


def build_national_team_intelligence(
    report: MatchIntelligenceReport,
    *,
    specialist_report: MatchSpecialistReport | None = None,
) -> dict[str, Any]:
    history = resolve_match_history(report)
    home_id = history.get("home_team_id")
    away_id = history.get("away_team_id")

    home_metrics = build_team_form_metrics(
        team_id=home_id,
        team_name=report.home_team.team_name,
        recent_fixtures=history.get("home_recent_fixtures"),
    )
    away_metrics = build_team_form_metrics(
        team_id=away_id,
        team_name=report.away_team.team_name,
        recent_fixtures=history.get("away_recent_fixtures"),
    )
    form_score, form_detail = national_form_score(home_metrics=home_metrics, away_metrics=away_metrics)
    h2h_score, h2h_detail = national_h2h_score(
        history.get("h2h_meetings"),
        home_team_id=home_id,
        away_team_id=away_id,
    )
    squad_score, squad_detail = squad_strength_score(report)
    injury_score, injury_detail = injury_impact_score(report)
    consensus_score, consensus_detail = consensus_strength_score(report, specialist_report)

    applicable = is_world_cup_report(report)
    return {
        "applicable": applicable,
        "version": "32e",
        "national_form_score": form_score,
        "national_h2h_score": h2h_score,
        "squad_strength_score": squad_score,
        "injury_impact_score": injury_score,
        "consensus_strength_score": consensus_score,
        "team_ids": {"home": home_id, "away": away_id, "source": history.get("id_source")},
        "data_coverage": {
            "home_recent_matches": home_metrics.matches_used,
            "away_recent_matches": away_metrics.matches_used,
            "h2h_meetings": int(h2h_detail.get("meetings_used") or 0),
        },
        "details": {
            "form": form_detail,
            "h2h": h2h_detail,
            "squad": squad_detail,
            "injury": injury_detail,
            "consensus": consensus_detail,
        },
        "confidence_components": {
            "form_score": form_score,
            "h2h_score": h2h_score,
            "injuries_score": injury_score,
            "lineups_score": squad_score,
            "odds_score": consensus_score,
        },
    }


def attach_national_team_intelligence(
    report: MatchIntelligenceReport,
    *,
    specialist_report: MatchSpecialistReport | None = None,
) -> MatchIntelligenceReport:
    if not is_world_cup_report(report):
        return report
    block = build_national_team_intelligence(report, specialist_report=specialist_report)
    supplemental = dict(report.supplemental_sources or {})
    supplemental[SUPPLEMENTAL_KEY] = block
    report.supplemental_sources = supplemental

    home_id = block.get("team_ids", {}).get("home")
    away_id = block.get("team_ids", {}).get("away")
    if home_id and report.home_team.team_id is None:
        report.home_team.team_id = int(home_id)
    if away_id and report.away_team.team_id is None:
        report.away_team.team_id = int(away_id)
    history = resolve_match_history(report)
    if history.get("home_recent_fixtures"):
        report.home_recent_fixtures = history["home_recent_fixtures"]
    if history.get("away_recent_fixtures"):
        report.away_recent_fixtures = history["away_recent_fixtures"]
    if history.get("h2h_meetings") and not (report.head_to_head or {}).get("meetings"):
        report.head_to_head = {"meetings": history["h2h_meetings"], "count": len(history["h2h_meetings"])}
    return report
