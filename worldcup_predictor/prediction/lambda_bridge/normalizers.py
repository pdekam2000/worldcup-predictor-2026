"""Map specialist signals to raw Δλ before safety envelope."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.domain.specialist import MatchSpecialistReport, SpecialistSignal


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _impact_dict(sig: SpecialistSignal | None) -> dict[str, Any]:
    if not sig or not sig.signals:
        return {}
    raw = sig.signals.get("prediction_impact")
    return raw if isinstance(raw, dict) else {}


def _partial_scale(sig: SpecialistSignal) -> float:
    if sig.status == "partial":
        reason = (sig.status_reason or "").lower()
        if "heuristic" in reason:
            return 0.6
        return 0.75
    return 1.0


def normalize_market_consensus(sig: SpecialistSignal | None) -> tuple[float, float, str]:
    if not sig or not sig.is_usable:
        return 0.0, 0.0, "unavailable"
    s = sig.signals
    home_imp = s.get("home_implied_probability")
    away_imp = s.get("away_implied_probability")
    if home_imp is None or away_imp is None:
        return 0.0, 0.0, "missing_implied"
    try:
        hi, ai = float(home_imp), float(away_imp)
        if hi > 1.0:
            hi /= 100.0
        if ai > 1.0:
            ai /= 100.0
    except (TypeError, ValueError):
        return 0.0, 0.0, "invalid_implied"
    spread = hi - ai
    scale = _partial_scale(sig)
    # Calibrated: ~0.15 max at extreme spread, not linear /25
    dh = _clamp(spread * 0.28 * scale, -0.10, 0.10)
    da = _clamp(-spread * 0.28 * scale, -0.10, 0.10)
    return dh, da, f"spread={spread:.3f}"


def normalize_injury_v2(sig: SpecialistSignal | None) -> tuple[float, float, str]:
    if not sig or not sig.is_usable:
        return 0.0, 0.0, "unavailable"
    impact = _impact_dict(sig)
    if not impact:
        return 0.0, 0.0, "no_impact"
    try:
        ha = float(impact.get("home_adjustment", 0) or 0)
        aa = float(impact.get("away_adjustment", 0) or 0)
    except (TypeError, ValueError):
        return 0.0, 0.0, "invalid_impact"
    scale = _partial_scale(sig)
    # Impact adjustments are on ±10 scale; map to λ with dampening
    dh = _clamp(ha / 80.0 * scale, -0.12, 0.05)
    da = _clamp(aa / 80.0 * scale, -0.12, 0.05)
    return dh, da, f"home_adj={ha:.1f} away_adj={aa:.1f}"


def normalize_lineup_v2(sig: SpecialistSignal | None) -> tuple[float, float, str]:
    if not sig or not sig.is_usable:
        return 0.0, 0.0, "unavailable"
    impact = _impact_dict(sig)
    home_side = (sig.signals.get("home") or {}) if sig.signals else {}
    away_side = (sig.signals.get("away") or {}) if sig.signals else {}
    try:
        hs = float(home_side.get("lineup_strength", 50))
        aws = float(away_side.get("lineup_strength", 50))
    except (TypeError, ValueError):
        hs, aws = 50.0, 50.0
    if impact:
        try:
            ha = float(impact.get("home_adjustment", 0) or 0)
            aa = float(impact.get("away_adjustment", 0) or 0)
        except (TypeError, ValueError):
            ha, aa = 0.0, 0.0
        dh = _clamp(ha / 100.0, -0.10, 0.10)
        da = _clamp(aa / 100.0, -0.10, 0.10)
    else:
        delta = (hs - aws) / 200.0
        dh = _clamp(delta, -0.08, 0.08)
        da = _clamp(-delta, -0.08, 0.08)
    scale = _partial_scale(sig)
    return dh * scale, da * scale, f"strength={hs:.0f}/{aws:.0f}"


def normalize_sharp_money(sig: SpecialistSignal | None, *, odds_primary_used: bool) -> tuple[float, float, str]:
    if odds_primary_used:
        return 0.0, 0.0, "dedup_odds_cluster"
    if not sig or not sig.is_usable:
        return 0.0, 0.0, "unavailable"
    impact = _impact_dict(sig)
    if not impact:
        return 0.0, 0.0, "no_impact"
    try:
        ha = float(impact.get("home_adjustment", 0) or 0)
        aa = float(impact.get("away_adjustment", 0) or 0)
        strength = float(sig.signals.get("consensus_strength", 50) or 50)
    except (TypeError, ValueError):
        return 0.0, 0.0, "invalid_impact"
    if strength < 55:
        return 0.0, 0.0, "low_market_confidence"
    scale = _partial_scale(sig) * 0.5
    dh = _clamp(ha / 120.0 * scale, -0.05, 0.05)
    da = _clamp(aa / 120.0 * scale, -0.05, 0.05)
    return dh, da, f"sharp_adj={ha:.1f}/{aa:.1f}"


def normalize_tournament(sig: SpecialistSignal | None) -> tuple[float, float, str]:
    if not sig or not sig.is_usable:
        return 0.0, 0.0, "unavailable"
    impact = _impact_dict(sig)
    if not impact:
        return 0.0, 0.0, "no_impact"
    try:
        ha = float(impact.get("home_adjustment", 0) or 0)
        aa = float(impact.get("away_adjustment", 0) or 0)
    except (TypeError, ValueError):
        return 0.0, 0.0, "invalid_impact"
    scale = _partial_scale(sig)
    dh = _clamp(ha / 150.0 * scale, -0.06, 0.06)
    da = _clamp(aa / 150.0 * scale, -0.06, 0.06)
    return dh, da, f"tournament={ha:.1f}/{aa:.1f}"


NORMALIZERS = {
    "market_consensus_agent": lambda spec, **kw: normalize_market_consensus(
        spec.signal("market_consensus_agent") if spec else None
    ),
    "injury_suspension_intelligence_agent": lambda spec, **kw: normalize_injury_v2(
        spec.signal("injury_suspension_intelligence_agent") if spec else None
    ),
    "lineup_intelligence_agent": lambda spec, **kw: normalize_lineup_v2(
        spec.signal("lineup_intelligence_agent") if spec else None
    ),
    "sharp_money_intelligence_agent": lambda spec, **kw: normalize_sharp_money(
        spec.signal("sharp_money_intelligence_agent") if spec else None,
        odds_primary_used=kw.get("odds_primary_used", False),
    ),
    "tournament_intelligence_agent": lambda spec, **kw: normalize_tournament(
        spec.signal("tournament_intelligence_agent") if spec else None
    ),
}


def collect_raw_contributions(
    specialist_report: MatchSpecialistReport | None,
    *,
    active_agents: frozenset[str],
) -> list[tuple[str, float, float, str, bool, str | None]]:
    if not specialist_report:
        return []
    rows: list[tuple[str, float, float, str, bool, str | None]] = []
    odds_primary = "market_consensus_agent" in active_agents
    for agent in active_agents:
        normalizer = NORMALIZERS.get(agent)
        if not normalizer:
            continue
        sig = specialist_report.signal(agent)
        if not sig or not sig.is_usable:
            rows.append((agent, 0.0, 0.0, "", False, "unavailable"))
            continue
        if "low_data_confidence" in (sig.signals.get("risk_flags") or []):
            pass
        dh, da, note = normalizer(specialist_report, odds_primary_used=odds_primary)
        if agent == "sharp_money_intelligence_agent" and note == "dedup_odds_cluster":
            rows.append((agent, 0.0, 0.0, note, False, "dedup_odds_cluster"))
            continue
        cap = 0.10
        from worldcup_predictor.prediction.lambda_bridge.config import SPECIALIST_CAPS

        cap = SPECIALIST_CAPS.get(agent, 0.10)
        if "low_data_confidence" in (sig.signals.get("risk_flags") or []):
            dh *= 0.5
            da *= 0.5
        dh = _clamp(dh, -cap, cap)
        da = _clamp(da, -cap, cap)
        rows.append((agent, dh, da, note, True, None))
    return rows
