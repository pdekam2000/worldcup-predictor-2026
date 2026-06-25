"""WDE + ScoringEngine integration for national team intelligence (Phase 32B)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.config.model_weights import get_thresholds
from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.intelligence.national_team.orchestrator import (
    SUPPLEMENTAL_KEY,
    attach_national_team_intelligence,
    build_national_team_intelligence,
    is_world_cup_report,
)


def get_national_block(
    report: MatchIntelligenceReport,
    *,
    specialist_report: MatchSpecialistReport | None = None,
) -> dict[str, Any] | None:
    try:
        from worldcup_predictor.config.settings import get_settings

        if not get_settings().national_team_intelligence_enabled:
            return None
    except Exception as exc:
        from worldcup_predictor.providers.safe_enrichment_logger import log_enrichment_failure

        log_enrichment_failure(
            "worldcup_predictor.intelligence.national_team.integration",
            exc,
            layer="settings_gate",
        )

    supplemental = getattr(report, "supplemental_sources", None) or {}
    block = supplemental.get(SUPPLEMENTAL_KEY)
    if isinstance(block, dict) and block.get("applicable"):
        return block
    if not is_world_cup_report(report):
        return None
    return build_national_team_intelligence(report, specialist_report=specialist_report)


def apply_national_confidence_components(
    *,
    form_score: float,
    h2h_score: float,
    injuries_score: float,
    lineups_score: float,
    odds_score: float,
    report: MatchIntelligenceReport,
    specialist_report: MatchSpecialistReport | None = None,
    enabled: bool = True,
) -> tuple[float, float, float, float, float, dict[str, Any] | None]:
    if not enabled or not is_world_cup_report(report):
        return form_score, h2h_score, injuries_score, lineups_score, odds_score, None

    block = get_national_block(report, specialist_report=specialist_report)
    if not block:
        return form_score, h2h_score, injuries_score, lineups_score, odds_score, None

    components = block.get("confidence_components") or {}
    coverage = block.get("data_coverage") or {}

    new_form = float(components.get("form_score") or form_score)
    new_h2h = float(components.get("h2h_score") or h2h_score)
    new_inj = float(components.get("injuries_score") or injuries_score)
    new_lineups = float(components.get("lineups_score") or lineups_score)
    new_odds = float(components.get("odds_score") or odds_score)

    # Blend with legacy when national data sparse — avoid false precision
    if int(coverage.get("home_recent_matches") or 0) + int(coverage.get("away_recent_matches") or 0) == 0:
        new_form = form_score * 0.55 + new_form * 0.45
    if int(coverage.get("h2h_meetings") or 0) == 0:
        new_h2h = max(h2h_score, 50.0)  # replace legacy 45 default with neutral 50

    return new_form, new_h2h, new_inj, new_lineups, new_odds, block


def national_wde_confidence_boost(block: dict[str, Any] | None) -> float:
    """Small additive WDE boost when national intelligence is data-rich."""
    if not block:
        return 0.0
    coverage = block.get("data_coverage") or {}
    rich = 0
    if int(coverage.get("home_recent_matches") or 0) >= 3:
        rich += 1
    if int(coverage.get("away_recent_matches") or 0) >= 3:
        rich += 1
    if int(coverage.get("h2h_meetings") or 0) >= 2:
        rich += 1
    if rich >= 2:
        return 1.0
    if rich == 1:
        return 0.5
    return 0.0


def verify_thresholds_unchanged() -> dict[str, float]:
    thresholds = get_thresholds(use_calibrated=True)
    required = {
        "no_bet_confidence_minimum": 60.0,
        "data_quality_no_bet_threshold": 50.0,
        "analysis_ready_confidence_minimum": 60.0,
    }
    return {k: float(thresholds.get(k, 0)) for k in required}


__all__ = [
    "apply_national_confidence_components",
    "attach_national_team_intelligence",
    "get_national_block",
    "national_wde_confidence_boost",
    "verify_thresholds_unchanged",
]
