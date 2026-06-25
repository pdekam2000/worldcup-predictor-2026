"""Odds movement intelligence — Phase 46D extension."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.intelligence.provider_utilization.models import OddsMovementIntelligence
from worldcup_predictor.odds.models import OddsMovementSignal

SHARP_MOVE_PCT = 8.0


def _implied_from_decimal(odd: Any) -> float | None:
    try:
        val = float(odd) if odd is not None else None
    except (TypeError, ValueError):
        return None
    if val is None or val <= 1.0:
        return None
    return 1.0 / val


def _implied_delta(opening: float | None, latest: float | None) -> float | None:
    open_impl = _implied_from_decimal(opening)
    latest_impl = _implied_from_decimal(latest)
    if open_impl is None or latest_impl is None:
        return None
    return round(latest_impl - open_impl, 4)


def _direction_from_delta(delta: float | None, side: str) -> str | None:
    if delta is None:
        return None
    if abs(delta) < 0.01:
        return "flat"
    if delta > 0:
        return f"toward_{side}"
    return f"away_from_{side}"


def build_odds_movement_intelligence(
    *,
    fixture_id: int,
    supplemental: dict[str, Any] | None = None,
    stored_snapshots: list[dict[str, Any]] | None = None,
) -> tuple[OddsMovementSignal, OddsMovementIntelligence]:
    """Build base movement signal plus extended intelligence metrics."""
    from worldcup_predictor.odds.odds_movement_agent import build_odds_movement

    supplemental = supplemental or {}
    base = build_odds_movement(
        fixture_id=fixture_id,
        supplemental=supplemental,
        stored_snapshots=stored_snapshots,
    )

    home_delta = _implied_delta(base.opening_home_odds, base.latest_home_odds)
    draw_delta = _implied_delta(base.opening_draw_odds, base.latest_draw_odds)
    away_delta = _implied_delta(base.opening_away_odds, base.latest_away_odds)

    deltas = {
        "home": home_delta,
        "draw": draw_delta,
        "away": away_delta,
    }
    valid = {k: abs(v) for k, v in deltas.items() if v is not None}
    strongest = max(valid, key=valid.get) if valid else None
    strongest_delta = deltas.get(strongest) if strongest else None

    movement_score = 0.0
    if valid:
        movement_score = round(min(100.0, max(valid.values()) * 500 + base.movement_confidence * 0.35), 2)

    direction = _direction_from_delta(strongest_delta, strongest) if strongest else None
    confidence_shift = 0.0
    if strongest_delta is not None:
        confidence_shift = round(abs(strongest_delta) * 100, 2)

    sharp = base.steam_move_detected or any(
        v is not None and abs(v) >= SHARP_MOVE_PCT
        for v in (
            base.home_movement,
            base.draw_movement,
            base.away_movement,
            base.over_movement,
            base.under_movement,
        )
    )

    consensus_drift = base.market_drift
    if not consensus_drift and strongest_delta is not None and abs(strongest_delta) >= 0.03:
        consensus_drift = f"Implied probability drift on {strongest}: {strongest_delta:+.1%}"

    intel = OddsMovementIntelligence(
        odds_movement_score=movement_score,
        odds_movement_direction=direction,
        market_confidence_shift=confidence_shift,
        opening_implied_home=_implied_from_decimal(base.opening_home_odds),
        current_implied_home=_implied_from_decimal(base.latest_home_odds),
        implied_probability_delta_home=home_delta,
        sharp_movement_detected=sharp,
        consensus_drift=consensus_drift,
        bookmaker_count=base.snapshot_count,
    )

    enriched = OddsMovementSignal(
        home_movement=base.home_movement,
        draw_movement=base.draw_movement,
        away_movement=base.away_movement,
        over_movement=base.over_movement,
        under_movement=base.under_movement,
        strongest_move=base.strongest_move or strongest,
        movement_confidence=base.movement_confidence,
        warning=base.warning,
        opening_home_odds=base.opening_home_odds,
        latest_home_odds=base.latest_home_odds,
        opening_draw_odds=base.opening_draw_odds,
        latest_draw_odds=base.latest_draw_odds,
        opening_away_odds=base.opening_away_odds,
        latest_away_odds=base.latest_away_odds,
        steam_move_detected=base.steam_move_detected,
        suspicious_volatility=base.suspicious_volatility,
        market_drift=consensus_drift or base.market_drift,
        snapshot_count=base.snapshot_count,
        notes=list(base.notes) + [f"46d_movement_score={movement_score}"],
    )
    return enriched, intel


def enrich_movement_signal_dict(signal_dict: dict[str, Any], intel: OddsMovementIntelligence) -> dict[str, Any]:
    """Attach intelligence fields for specialist/WDE input layer (read-only)."""
    out = dict(signal_dict)
    out.update(intel.to_dict())
    return out
