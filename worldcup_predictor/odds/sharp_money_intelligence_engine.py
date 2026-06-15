"""Sharp Money & Odds Movement Intelligence V2 — API-Football odds only."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.agents.specialists.odds_control_agent import (
    extract_api_sports_1x2_meta,
    extract_api_sports_ou25_meta,
)
from worldcup_predictor.odds.models import (
    OddsSnapshotTrack,
    SharpMoneyIntelligenceResult,
    SharpMoneyPredictionImpact,
)
from worldcup_predictor.odds.odds_snapshot_engine import build_odds_snapshot_track

_STEAM_THRESHOLD = 8.0
_EXTREME_THRESHOLD = 15.0
_ADJUSTMENT_CAP = 10.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _sharp_band(score: float) -> str:
    if score < 20:
        return "Very Weak"
    if score < 40:
        return "Weak"
    if score < 60:
        return "Moderate"
    if score < 80:
        return "Strong"
    return "Very Strong"


def _disagreement_to_level(std_dev: float, level_str: str) -> str:
    if std_dev >= 0.05:
        return "Extreme"
    if level_str == "High":
        return "High"
    if level_str == "Medium":
        return "Medium"
    if level_str == "Low":
        return "Low"
    return "Low" if std_dev < 0.015 else "Medium"


def _implied_from_track(track: Any) -> tuple[float | None, float | None]:
    opening = getattr(track, "opening_odds", None)
    latest = getattr(track, "latest_odds", None)
    open_imp = 1.0 / opening if opening and opening > 1.0 else None
    latest_imp = 1.0 / latest if latest and latest > 1.0 else None
    return open_imp, latest_imp


def _detect_reverse_line(track: Any) -> tuple[bool, float]:
    """RLM when implied probability and decimal odds move in opposite directions."""
    open_imp, latest_imp = _implied_from_track(track)
    pct = getattr(track, "movement_pct", None)
    if open_imp is None or latest_imp is None or pct is None:
        return False, 0.0
    prob_delta = latest_imp - open_imp
    if abs(prob_delta) < 0.02 or abs(pct) < 2.0:
        return False, 0.0
    odds_shortening = pct < 0
    prob_increasing = prob_delta > 0
    if prob_increasing != odds_shortening:
        confidence = _clamp(abs(prob_delta) * 400 + abs(pct) * 2, 15, 90)
        return True, round(confidence, 1)
    return False, 0.0


def _goals_market_bias(track: Any) -> float:
    pct = getattr(track, "movement_pct", None)
    if pct is None:
        return 50.0
    if pct < -5:
        return _clamp(50 + abs(pct) * 2.5, 50, 85)
    if pct > 5:
        return _clamp(50 - abs(pct) * 2.5, 15, 50)
    return 50.0


def _compute_sharp_score(
    track: OddsSnapshotTrack,
    *,
    steam: bool,
    rlm: bool,
    rlm_confidence: float,
    disagreement_level: str,
) -> float:
    moves = [
        track.home.movement_pct,
        track.draw.movement_pct,
        track.away.movement_pct,
        track.over_2_5.movement_pct,
        track.under_2_5.movement_pct,
    ]
    valid = [abs(m) for m in moves if m is not None]
    base = 15.0
    if valid:
        base += min(35.0, max(valid) * 1.8)
        base += min(15.0, len(valid) * 3.0)
    if steam:
        base += 20.0
    if rlm:
        base += rlm_confidence * 0.25
    if disagreement_level in {"High", "Extreme"}:
        base += 8.0
    if track.snapshot_count >= 2:
        base += 10.0
    elif not track.history_available:
        base = min(base, 25.0)
    return round(_clamp(base, 0, 100), 1)


def _movement_summary(track: OddsSnapshotTrack) -> str:
    parts: list[str] = []
    for label, side in (
        ("Home", track.home),
        ("Draw", track.draw),
        ("Away", track.away),
        ("Over 2.5", track.over_2_5),
        ("Under 2.5", track.under_2_5),
    ):
        if side.movement_pct is not None:
            parts.append(f"{label} {side.movement_class} ({side.movement_pct:+.1f}%)")
    return "; ".join(parts) if parts else "No significant odds movement detected."


def _build_prediction_impact(
    track: OddsSnapshotTrack,
    *,
    sharp_score: float,
    rlm: bool,
    rlm_confidence: float,
    meta_1x2: dict[str, Any],
    steam: bool,
) -> SharpMoneyPredictionImpact:
    impact = SharpMoneyPredictionImpact()
    if not track.history_available:
        return impact

    weight = min(sharp_score / 100.0, 0.6)

    for side_key, adj_attr in (("home", "home_adjustment"), ("away", "away_adjustment"), ("draw", "draw_adjustment")):
        side_track = getattr(track, side_key if side_key != "draw" else "draw")
        pct = side_track.movement_pct
        if pct is None:
            continue
        delta = -pct * 0.15 * weight
        if side_track.movement_direction == "shortening":
            delta = abs(delta)
        elif side_track.movement_direction == "drifting":
            delta = -abs(delta)
        setattr(impact, adj_attr, round(_clamp(getattr(impact, adj_attr) + delta, -_ADJUSTMENT_CAP, _ADJUSTMENT_CAP), 2))

    if track.over_2_5.movement_pct is not None and track.over_2_5.movement_pct < -3:
        impact.over25_adjustment = round(_clamp(-track.over_2_5.movement_pct * 0.12 * weight, 0, _ADJUSTMENT_CAP), 2)
    if track.under_2_5.movement_pct is not None and track.under_2_5.movement_pct < -3:
        impact.under25_adjustment = round(_clamp(-track.under_2_5.movement_pct * 0.12 * weight, 0, _ADJUSTMENT_CAP), 2)

    if steam:
        strongest = max(
            [
                ("home", track.home.movement_pct),
                ("away", track.away.movement_pct),
                ("over_2_5", track.over_2_5.movement_pct),
            ],
            key=lambda x: abs(x[1] or 0),
        )
        if strongest[0] == "home" and (strongest[1] or 0) < 0:
            impact.home_adjustment = round(_clamp(impact.home_adjustment + 2.0 * weight, -_ADJUSTMENT_CAP, _ADJUSTMENT_CAP), 2)
        elif strongest[0] == "away" and (strongest[1] or 0) < 0:
            impact.away_adjustment = round(_clamp(impact.away_adjustment + 2.0 * weight, -_ADJUSTMENT_CAP, _ADJUSTMENT_CAP), 2)
        elif strongest[0] == "over_2_5" and (strongest[1] or 0) < 0:
            impact.over25_adjustment = round(_clamp(impact.over25_adjustment + 2.5 * weight, -_ADJUSTMENT_CAP, _ADJUSTMENT_CAP), 2)

    if rlm and rlm_confidence >= 40:
        probs = meta_1x2.get("probs") or {}
        favorite = max(probs, key=probs.get) if probs else None
        if favorite == "home":
            impact.away_adjustment = round(_clamp(impact.away_adjustment + 1.5, -_ADJUSTMENT_CAP, _ADJUSTMENT_CAP), 2)
        elif favorite == "away":
            impact.home_adjustment = round(_clamp(impact.home_adjustment + 1.5, -_ADJUSTMENT_CAP, _ADJUSTMENT_CAP), 2)

    return impact


def _build_risk_flags(
    track: OddsSnapshotTrack,
    *,
    steam: bool,
    rlm: bool,
    disagreement_level: str,
    sharp_score: float,
    bookmaker_count: int,
    suspicious: bool,
    late_move: bool,
) -> list[str]:
    flags: list[str] = []
    if steam:
        flags.append("steam_move_detected")
    if rlm:
        flags.append("reverse_line_movement")
    if disagreement_level in {"High", "Extreme"}:
        flags.append("high_market_disagreement")
    extreme = any(
        abs(getattr(track, k).movement_pct or 0) >= _EXTREME_THRESHOLD
        for k in ("home", "draw", "away", "over_2_5", "under_2_5")
    )
    if extreme:
        flags.append("extreme_odds_shift")
    if suspicious:
        flags.append("suspicious_market_activity")
    if not track.history_available or bookmaker_count < 2:
        flags.append("low_market_confidence")
    if disagreement_level == "Extreme" or (disagreement_level == "High" and bookmaker_count >= 3):
        flags.append("bookmaker_split")
    if late_move:
        flags.append("late_market_move")
    if sharp_score >= 60 and steam:
        flags.append("suspicious_market_activity")
    return sorted(set(flags))


def _safe_fallback() -> SharpMoneyIntelligenceResult:
    from worldcup_predictor.odds.models import OutcomeOddsTrack

    empty = OutcomeOddsTrack(None, None, None, None, "Stable")
    track = OddsSnapshotTrack(
        home=empty,
        draw=empty,
        away=empty,
        over_2_5=empty,
        under_2_5=empty,
        snapshot_count=0,
        history_available=False,
    )
    return SharpMoneyIntelligenceResult(
        odds_tracking=track,
        sharp_money_score=0.0,
        sharp_money_band="Very Weak",
        reverse_line_movement=False,
        reverse_line_confidence=0.0,
        consensus_strength=0.0,
        disagreement_level="Low",
        probability_dispersion=0.0,
        over_market_bias=50.0,
        under_market_bias=50.0,
        goals_market_confidence=25.0,
        market_confidence=25.0,
        steam_move_detected=False,
        movement_summary="No API-Football odds data available.",
        risk_flags=["low_market_confidence"],
        prediction_impact=SharpMoneyPredictionImpact(),
        summary="Market intelligence unavailable — safe fallback applied. Analysis only — not betting advice.",
    )


def build_sharp_money_intelligence(
    report: Any,
    *,
    stored_snapshots: list[dict[str, Any]] | None = None,
) -> SharpMoneyIntelligenceResult:
    """Build Sharp Money & Market Intelligence V2 from API-Football odds only."""
    try:
        meta_1x2 = extract_api_sports_1x2_meta(report)
        meta_ou = extract_api_sports_ou25_meta(report)
        track = build_odds_snapshot_track(report, stored_snapshots=stored_snapshots)

        bookmaker_count = int(meta_1x2.get("bookmaker_count") or 0)
        ou_count = int(meta_ou.get("bookmaker_count") or 0)
        if bookmaker_count == 0 and not track.history_available:
            return _safe_fallback()
        std_dev = float(meta_1x2.get("std_dev") or 0.0)
        disagreement_level = _disagreement_to_level(std_dev, str(meta_1x2.get("disagreement_level") or "unknown"))

        consensus_strength = 0.0
        if bookmaker_count >= 2:
            consensus_strength = round(_clamp(40 + bookmaker_count * 4 - std_dev * 400, 20, 95), 1)
        elif bookmaker_count == 1:
            consensus_strength = 35.0

        moves = [
            track.home.movement_pct,
            track.draw.movement_pct,
            track.away.movement_pct,
            track.over_2_5.movement_pct,
            track.under_2_5.movement_pct,
        ]
        steam = any(abs(m or 0) >= _STEAM_THRESHOLD for m in moves)
        suspicious = any(abs(m or 0) >= _EXTREME_THRESHOLD for m in moves)

        rlm_flags = [_detect_reverse_line(getattr(track, k)) for k in ("home", "draw", "away")]
        rlm = any(r[0] for r in rlm_flags)
        rlm_confidence = max((r[1] for r in rlm_flags), default=0.0)

        late_move = track.snapshot_count >= 2 and any(
            getattr(track, k).movement_class in {"Large Move", "Extreme Move"}
            for k in ("home", "draw", "away", "over_2_5", "under_2_5")
        )

        sharp_score = _compute_sharp_score(
            track,
            steam=steam,
            rlm=rlm,
            rlm_confidence=rlm_confidence,
            disagreement_level=disagreement_level,
        )

        over_bias = _goals_market_bias(track.over_2_5)
        under_bias = _goals_market_bias(track.under_2_5)
        goals_conf = 25.0
        if track.over_2_5.movement_pct is not None or track.under_2_5.movement_pct is not None:
            goals_conf = round(_clamp(35 + ou_count * 5, 25, 85), 1)

        market_confidence = round(
            _clamp((consensus_strength + goals_conf) / 2 - (10 if disagreement_level in {"High", "Extreme"} else 0), 15, 95),
            1,
        )

        risk_flags = _build_risk_flags(
            track,
            steam=steam,
            rlm=rlm,
            disagreement_level=disagreement_level,
            sharp_score=sharp_score,
            bookmaker_count=bookmaker_count,
            suspicious=suspicious,
            late_move=late_move,
        )

        prediction_impact = _build_prediction_impact(
            track,
            sharp_score=sharp_score,
            rlm=rlm,
            rlm_confidence=rlm_confidence,
            meta_1x2=meta_1x2,
            steam=steam,
        )

        summary_parts = [_movement_summary(track)]
        if steam:
            summary_parts.append("Steam move detected (analysis only).")
        if rlm:
            summary_parts.append(f"Reverse line movement signal (confidence {rlm_confidence:.0f}%).")
        if not track.history_available and bookmaker_count == 0:
            summary = "No API-Football odds data available — safe fallback applied."
        else:
            summary = " ".join(summary_parts) + " Analysis only — not betting advice."

        return SharpMoneyIntelligenceResult(
            odds_tracking=track,
            sharp_money_score=sharp_score,
            sharp_money_band=_sharp_band(sharp_score),
            reverse_line_movement=rlm,
            reverse_line_confidence=rlm_confidence,
            consensus_strength=consensus_strength,
            disagreement_level=disagreement_level,
            probability_dispersion=round(std_dev, 4),
            over_market_bias=round(over_bias, 1),
            under_market_bias=round(under_bias, 1),
            goals_market_confidence=goals_conf,
            market_confidence=market_confidence,
            steam_move_detected=steam,
            movement_summary=_movement_summary(track),
            risk_flags=risk_flags,
            prediction_impact=prediction_impact,
            summary=summary,
            bookmaker_count_1x2=bookmaker_count,
            bookmaker_count_ou25=ou_count,
        )
    except Exception:
        return _safe_fallback()
