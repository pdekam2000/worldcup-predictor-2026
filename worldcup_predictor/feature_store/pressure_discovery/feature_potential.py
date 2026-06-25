"""EGIE target feature potential from pressure evidence."""

from __future__ import annotations

from typing import Any

Potential = str  # VERY_HIGH | HIGH | MEDIUM | LOW | NONE

EGIE_TARGETS = (
    "first_goal_team",
    "goal_minute",
    "goal_range",
    "next_goal_team",
    "team_goals",
    "live_goal_probability",
)


def _has_minute_pressure(evidence: dict[str, Any]) -> bool:
    return float(evidence.get("sample_pressure_rate") or 0) > 0.5 and float(
        evidence.get("avg_unique_minutes") or 0
    ) >= 30


def _has_pre_match_proxy(evidence: dict[str, Any]) -> bool:
    return bool(evidence.get("dangerous_attacks_in_statistics")) or float(
        evidence.get("statistics_rate") or 0
    ) > 0.5


def build_feature_potential_matrix(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    minute_ok = _has_minute_pressure(evidence)
    pre_ok = _has_pre_match_proxy(evidence)
    live_ok = bool(evidence.get("pressure_endpoint_accessible"))
    hist_ok = float(evidence.get("historical_sample_coverage_pct") or 0) > 30

    def _rate(
        *,
        very_high: bool = False,
        high: bool = False,
        medium: bool = False,
        low: bool = False,
    ) -> Potential:
        if very_high:
            return "VERY_HIGH"
        if high:
            return "HIGH"
        if medium:
            return "MEDIUM"
        if low:
            return "LOW"
        return "NONE"

    rows: list[dict[str, Any]] = []

    # First Goal Team — pre-match rolling pressure from prior fixtures; minute-0 rows exist
    fg = _rate(
        high=pre_ok and hist_ok,
        medium=pre_ok or (minute_ok and hist_ok),
        low=live_ok,
    )
    rows.append(
        {
            "egie_target": "first_goal_team",
            "potential_value": fg,
            "rationale": "Minute-0 pressure rows + statistics proxies; unlike xG, directly models early dominance",
            "requires": "rolling_pressure_pre_match aggregation",
        }
    )

    rows.append(
        {
            "egie_target": "goal_minute",
            "potential_value": _rate(very_high=minute_ok and hist_ok, high=minute_ok, medium=live_ok),
            "rationale": "Minute-by-minute pressure timeline maps to goal timing hazard",
            "requires": "full timeline + event linkage",
        }
    )

    rows.append(
        {
            "egie_target": "goal_range",
            "potential_value": _rate(medium=minute_ok or pre_ok, low=hist_ok),
            "rationale": "Match intensity / sustained pressure correlates with total goals; weaker than xG top10",
            "requires": "match-level pressure integrals",
        }
    )

    rows.append(
        {
            "egie_target": "next_goal_team",
            "potential_value": _rate(very_high=minute_ok and live_ok, high=minute_ok, medium=pre_ok),
            "rationale": "Live pressure asymmetry is primary Sportmonks use case",
            "requires": "live timeline + participant mapping",
        }
    )

    rows.append(
        {
            "egie_target": "team_goals",
            "potential_value": _rate(medium=pre_ok and hist_ok, low=minute_ok),
            "rationale": "Pressure complements O/U; xG showed +3% with top5 — pressure may add live signal only",
            "requires": "pre-match rolling aggregates",
        }
    )

    rows.append(
        {
            "egie_target": "live_goal_probability",
            "potential_value": _rate(very_high=minute_ok and live_ok, high=minute_ok, medium=live_ok),
            "rationale": "Core in-play momentum metric; not available from xG pre-match stack",
            "requires": "live feed + minute updates",
        }
    )

    return rows
