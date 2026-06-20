"""Tournament context promotion adapter — Phase 24B."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.domain.specialist import MatchSpecialistReport, SpecialistSignal
from worldcup_predictor.promotion.config import (
    CONFIG_VERSION_24B,
    CONTEXT_PROMOTION_AGENT_KEY,
    MAX_CONTEXT_CONFIDENCE_BOOST,
    MAX_CONTEXT_CONFIDENCE_REDUCE,
    MAX_MOTIVATION_EDGE_DELTA,
    MAX_MOTIVATION_SCORE_DELTA,
    MIN_GROUP_CONTEXT_STRENGTH,
    WEIGHTS_MOT_BLEND,
)
from worldcup_predictor.promotion.models import PromotionMode, TournamentContextPromotionResult
from worldcup_predictor.promotion.shadow_store import (
    TournamentContextPromotionShadowRecord,
    TournamentContextPromotionShadowStore,
)

logger = logging.getLogger(__name__)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _promotion_mode(settings: Settings | None = None) -> PromotionMode:
    settings = settings or get_settings()
    mode = str(getattr(settings, "tournament_context_promotion_mode", "shadow") or "shadow").lower()
    if mode in ("off", "shadow", "gated"):
        return mode  # type: ignore[return-value]
    return "shadow"


def _context_signal(specialist: MatchSpecialistReport | None) -> SpecialistSignal | None:
    if not specialist:
        return None
    return specialist.signal(CONTEXT_PROMOTION_AGENT_KEY)


def _mot_psych_avg(specialist: MatchSpecialistReport | None, fallback: float) -> float:
    if not specialist:
        return fallback
    sig = specialist.signal("motivation_psychology_agent")
    if not sig or not sig.signals:
        return fallback
    block = sig.signals
    mh = float(block.get("motivation_score_home") or fallback)
    ma = float(block.get("motivation_score_away") or fallback)
    return (mh + ma) / 2


def _tour_intel_pressure(specialist: MatchSpecialistReport | None, fallback: float) -> float:
    if not specialist:
        return fallback
    sig = specialist.signal("tournament_intelligence_agent")
    if not sig or not sig.signals:
        return fallback
    return float(sig.signals.get("pressure_score") or fallback)


def _tour_intel_must_win_flagged(specialist: MatchSpecialistReport | None) -> bool:
    if not specialist:
        return False
    sig = specialist.signal("tournament_intelligence_agent")
    if not sig or not sig.signals:
        return False
    flags = sig.signals.get("risk_flags") or []
    return "must_win_match" in flags


def _compute_tactics_trace(block: dict[str, Any], match_context: str) -> tuple[float, str]:
    """Trace-only O/U context notes — not applied to tactics_matchup in 24B."""
    delta = 0.0
    notes: list[str] = []
    aggression = str(block.get("expected_aggression") or "balanced").lower()
    conservatism = str(block.get("expected_conservatism") or "balanced").lower()
    rotation = str(block.get("rotation_risk") or "Medium")
    importance = str(block.get("tournament_importance") or "standard").lower()

    if aggression == "high":
        delta += 0.04
        notes.append("aggression_high_over_lean")
    if conservatism == "high":
        delta -= 0.04
        notes.append("conservatism_high_under_lean")
    if rotation == "High":
        delta += 0.03
        notes.append("rotation_high_volatility")
    if importance == "critical":
        delta += 0.02
        notes.append("importance_critical")

    is_knockout = "group stage" not in str(match_context).lower()
    if is_knockout and match_context not in {"Unknown", ""}:
        delta = _clamp(delta, -0.05, 0.05)
        notes.append("knockout_ou_cap")

    return round(delta, 4), ";".join(notes) if notes else "no_tactics_trace"


def _gate_passed(
    sig: SpecialistSignal | None,
    *,
    competition_key: str,
    is_placeholder: bool,
) -> tuple[bool, str]:
    if _promotion_mode() == "off":
        return False, "promotion_off"
    if competition_key != "world_cup_2026":
        return False, "competition_not_world_cup_2026"
    if is_placeholder:
        return False, "placeholder_data"
    if sig is None or not sig.is_usable:
        return False, "tournament_context_unavailable"
    if sig.status == "unavailable":
        return False, "tournament_context_status_unavailable"
    block = sig.signals or {}
    if not block.get("data_sources"):
        return False, "no_tournament_context_sources"
    strength = float(block.get("group_context_strength") or 0)
    if strength < MIN_GROUP_CONTEXT_STRENGTH:
        return False, "group_context_strength_below_gate"
    return True, "gates_passed"


def compute_tournament_context_promotion(
    *,
    specialist: MatchSpecialistReport | None,
    baseline_mot_score: float,
    baseline_mot_edge: float,
    competition_key: str = "world_cup_2026",
    is_placeholder: bool = False,
    fixture_id: int | None = None,
    settings: Settings | None = None,
) -> TournamentContextPromotionResult:
    """Compute bounded motivation_psychology promotion from TournamentContextAgent."""
    settings = settings or get_settings()
    mode = _promotion_mode(settings)
    empty = TournamentContextPromotionResult(
        baseline_motivation_score=baseline_mot_score,
        promoted_motivation_score=baseline_mot_score,
        mode=mode,
    )
    if mode == "off":
        return empty

    sig = _context_signal(specialist)
    passed, reason = _gate_passed(
        sig,
        competition_key=competition_key,
        is_placeholder=is_placeholder,
    )

    if not passed or sig is None:
        result = TournamentContextPromotionResult(
            context_promotion_reason=reason,
            baseline_motivation_score=baseline_mot_score,
            promoted_motivation_score=baseline_mot_score,
            mode=mode,
            gate_passed=False,
        )
        _maybe_log_shadow(result, fixture_id=fixture_id, settings=settings)
        return result

    block = sig.signals or {}
    context_conf = float(block.get("group_context_strength") or 0)
    context_home = float(block.get("motivation_score_home") or 50)
    context_away = float(block.get("motivation_score_away") or 50)
    context_avg = (context_home + context_away) / 2
    supports_internal = bool(block.get("context_supports_internal", True))
    disagreement = float(block.get("disagreement_score") or 0)

    w_psych, w_tour, w_ctx = WEIGHTS_MOT_BLEND
    mot_psych = _mot_psych_avg(specialist, baseline_mot_score)
    tour_pressure = _tour_intel_pressure(specialist, baseline_mot_score)
    target_score = w_psych * mot_psych + w_tour * tour_pressure + w_ctx * context_avg
    target_score = _clamp(target_score, 0.0, 100.0)

    raw_delta = target_score - baseline_mot_score
    if not supports_internal:
        raw_delta *= 0.5
        reason = "gates_passed_dampened_internal_divergence"
    else:
        reason = "tournament_context_motivation_blend"

    score_delta = _clamp(raw_delta, -MAX_MOTIVATION_SCORE_DELTA, MAX_MOTIVATION_SCORE_DELTA)

    must_win_influence = 0.0
    draw_influence = 0.0
    rotation_influence = 0.0
    edge_nudge = 0.0

    must_win = bool(block.get("must_win_flag"))
    home_must = str(block.get("qualification_status_home") or "") == "must_win"
    away_must = str(block.get("qualification_status_away") or "") == "must_win"
    draw_ok = bool(block.get("draw_acceptability"))
    rotation = str(block.get("rotation_risk") or "Medium")

    if must_win and home_must and not away_must:
        must_win_influence = 0.015
        if _tour_intel_must_win_flagged(specialist):
            must_win_influence *= 0.5
            reason += ";dedup_tour_intel_must_win"
        edge_nudge += must_win_influence
    elif must_win and away_must and not home_must:
        must_win_influence = -0.015
        if _tour_intel_must_win_flagged(specialist):
            must_win_influence *= 0.5
            reason += ";dedup_tour_intel_must_win"
        edge_nudge += must_win_influence

    if draw_ok:
        draw_influence = -0.01
        if baseline_mot_edge > 0:
            edge_nudge -= min(0.01, abs(baseline_mot_edge))
        elif baseline_mot_edge < 0:
            edge_nudge += min(0.01, abs(baseline_mot_edge))
        reason += ";draw_acceptability"

    elim_home = float(block.get("elimination_risk_home") or 50)
    elim_away = float(block.get("elimination_risk_away") or 50)
    elim_diff = elim_home - elim_away
    if abs(elim_diff) >= 20:
        elim_nudge = 0.01 if elim_diff < 0 else -0.01
        edge_nudge += elim_nudge
        reason += ";elimination_risk_edge"

    if rotation == "High":
        rotation_influence = 0.03
    elif rotation == "Low":
        rotation_influence = -0.01

    if not supports_internal:
        edge_nudge *= 0.5
        must_win_influence *= 0.5
        draw_influence *= 0.5

    edge_delta = _clamp(edge_nudge, -MAX_MOTIVATION_EDGE_DELTA, MAX_MOTIVATION_EDGE_DELTA)

    match_context = str(block.get("match_context") or "Unknown")
    tactics_over_trace, tactics_notes = _compute_tactics_trace(block, match_context)

    conf_delta = 0.0
    if context_conf >= 60 and supports_internal:
        conf_delta += min(1.0, MAX_CONTEXT_CONFIDENCE_BOOST)
        reason += ";strong_group_context"
    if disagreement >= 0.35:
        conf_delta -= min(1.5, MAX_CONTEXT_CONFIDENCE_REDUCE)
        reason += ";context_motivation_disagreement"
    conf_delta = _clamp(conf_delta, -MAX_CONTEXT_CONFIDENCE_REDUCE, MAX_CONTEXT_CONFIDENCE_BOOST)

    promoted_score = _clamp(baseline_mot_score + score_delta, 0.0, 100.0)
    applied = mode == "gated"
    promoted_if_applied = promoted_score if applied else baseline_mot_score

    result = TournamentContextPromotionResult(
        context_promotion_active=True,
        context_delta_score=round(score_delta, 2),
        context_delta_edge=round(edge_delta, 4),
        context_promotion_reason=reason,
        context_promotion_confidence=round(context_conf, 1),
        must_win_influence=round(must_win_influence, 4),
        rotation_context_influence=round(rotation_influence, 4),
        draw_acceptability_influence=round(draw_influence, 4),
        confidence_delta=round(conf_delta, 2),
        tactics_trace_notes=tactics_notes,
        tactics_over_trace_delta=tactics_over_trace,
        baseline_motivation_score=round(baseline_mot_score, 2),
        promoted_motivation_score=round(promoted_score if mode == "shadow" else promoted_if_applied, 2),
        mode=mode,
        gate_passed=True,
        applied=applied,
    )

    _maybe_log_shadow(result, fixture_id=fixture_id, settings=settings)
    return result


def apply_context_promotion_to_factor(
    baseline_score: float,
    baseline_edge: float,
    promotion: TournamentContextPromotionResult,
) -> tuple[float, float]:
    """Apply promotion deltas when mode=gated and active (motivation only — tactics trace-only)."""
    if not promotion.context_promotion_active or promotion.mode != "gated" or not promotion.applied:
        return baseline_score, baseline_edge
    score = _clamp(baseline_score + promotion.context_delta_score, 0.0, 100.0)
    edge = baseline_edge + promotion.context_delta_edge
    return score, edge


def _maybe_log_shadow(
    result: TournamentContextPromotionResult,
    *,
    fixture_id: int | None,
    settings: Settings | None,
) -> None:
    if result.mode not in ("shadow", "gated") or fixture_id is None:
        return
    settings = settings or get_settings()
    path = getattr(
        settings,
        "tournament_context_promotion_shadow_path",
        "data/shadow/tournament_context_promotion_shadow.jsonl",
    )
    store = TournamentContextPromotionShadowStore(path)
    try:
        store.append(
            TournamentContextPromotionShadowRecord(
                fixture_id=int(fixture_id),
                timestamp=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                mode=result.mode,
                config_version=CONFIG_VERSION_24B,
                baseline_motivation_score=result.baseline_motivation_score,
                promoted_motivation_score=result.promoted_motivation_score,
                context_delta_score=result.context_delta_score,
                context_delta_edge=result.context_delta_edge,
                confidence_delta=result.confidence_delta,
                context_promotion_active=result.context_promotion_active,
                context_promotion_reason=result.context_promotion_reason,
                must_win_influence=result.must_win_influence,
                rotation_context_influence=result.rotation_context_influence,
                draw_acceptability_influence=result.draw_acceptability_influence,
                tactics_over_trace_delta=result.tactics_over_trace_delta,
                tactics_trace_notes=result.tactics_trace_notes,
                applied=result.applied,
                gate_passed=result.gate_passed,
            )
        )
    except OSError:
        logger.debug("tournament context promotion shadow log skipped fixture=%s", fixture_id)
