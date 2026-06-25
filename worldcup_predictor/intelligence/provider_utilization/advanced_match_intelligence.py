"""Advanced match intelligence from Sportmonks metrics — Phase 46D."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.intelligence.provider_utilization.models import AdvancedMatchIntelligence
from worldcup_predictor.intelligence.sportmonks_xg_intelligence_engine import parse_sportmonks_xg_from_fixture
from worldcup_predictor.providers.sportmonks_consumption import SPORTMONKS_SUPPLEMENTAL_KEY


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _stat_value(flat: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        val = _float(flat.get(key))
        if val is not None:
            return val
    return None


def build_advanced_match_intelligence(report: MatchIntelligenceReport) -> AdvancedMatchIntelligence:
    """Derive attacking/defensive edges from Sportmonks xG and statistics."""
    supplemental = getattr(report, "supplemental_sources", None) or {}
    sm_block = supplemental.get(SPORTMONKS_SUPPLEMENTAL_KEY) or {}
    raw = sm_block.get("raw_fixture") if isinstance(sm_block, dict) else None
    if not isinstance(raw, dict):
        raw = sm_block if isinstance(sm_block, dict) else {}

    xg_block = parse_sportmonks_xg_from_fixture(raw) if raw else None
    xg_home = xg_away = xga_home = xga_away = None
    if isinstance(xg_block, dict):
        xg_home = _float(xg_block.get("home_xg"))
        xg_away = _float(xg_block.get("away_xg"))

    stat_flat = sm_block.get("statistics_flat") if isinstance(sm_block, dict) else {}
    if not isinstance(stat_flat, dict):
        stat_flat = {}

    shots_home = _stat_value(stat_flat, "home_shots_total", "home_shots")
    shots_away = _stat_value(stat_flat, "away_shots_total", "away_shots")
    shots_on_home = _stat_value(stat_flat, "home_shots_on_target", "home_shots_on")
    shots_on_away = _stat_value(stat_flat, "away_shots_on_target", "away_shots_on")
    goals_home = _stat_value(stat_flat, "home_goals", "home_score")
    goals_away = _stat_value(stat_flat, "away_goals", "away_score")

    if xg_home is None and xg_block and isinstance(xg_block, dict):
        xg_home = _float(xg_block.get("expected_goals_home"))
        xg_away = _float(xg_block.get("expected_goals_away"))

    available = any(v is not None for v in (xg_home, xg_away, shots_home, shots_away))

    shot_quality_home = round(shots_on_home / shots_home, 3) if shots_home and shots_on_home is not None else None
    shot_quality_away = round(shots_on_away / shots_away, 3) if shots_away and shots_on_away is not None else None

    attack_eff_home = round(xg_home / shots_home, 3) if xg_home is not None and shots_home else None
    attack_eff_away = round(xg_away / shots_away, 3) if xg_away is not None and shots_away else None

    xga_home = xg_away
    xga_away = xg_home

    def_eff_home = round(1.0 - min(1.0, (xg_away or 0) / max(0.1, goals_home or 1)), 3) if xg_away is not None else None
    def_eff_away = round(1.0 - min(1.0, (xg_home or 0) / max(0.1, goals_away or 1)), 3) if xg_home is not None else None

    attacking_edge_home = round((xg_home or 0) - (xg_away or 0), 3) if xg_home is not None and xg_away is not None else None
    attacking_edge_away = round(-attacking_edge_home, 3) if attacking_edge_home is not None else None
    defensive_edge_home = round((xga_home or 0) - (xga_away or 0), 3) if xga_home is not None and xga_away is not None else None
    defensive_edge_away = round(-defensive_edge_home, 3) if defensive_edge_home is not None else None

    xg_momentum = None
    if xg_home is not None and xg_away is not None:
        total = xg_home + xg_away
        xg_momentum = round((xg_home - xg_away) / max(0.1, total), 3) if total > 0 else 0.0

    expected_scoring_pressure = round(xg_home + xg_away, 3) if xg_home is not None and xg_away is not None else None

    return AdvancedMatchIntelligence(
        attacking_edge_home=attacking_edge_home,
        attacking_edge_away=attacking_edge_away,
        defensive_edge_home=defensive_edge_home,
        defensive_edge_away=defensive_edge_away,
        xg_home=xg_home,
        xg_away=xg_away,
        xga_home=xga_home,
        xga_away=xga_away,
        xg_momentum=xg_momentum,
        expected_scoring_pressure=expected_scoring_pressure,
        shot_quality_home=shot_quality_home,
        shot_quality_away=shot_quality_away,
        attack_efficiency_home=attack_eff_home,
        attack_efficiency_away=attack_eff_away,
        defensive_efficiency_home=def_eff_home,
        defensive_efficiency_away=def_eff_away,
        source="sportmonks",
        available=available,
    )
