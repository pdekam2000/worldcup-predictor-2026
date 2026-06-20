"""xG intelligence promotion adapter — Phase 24C (tactics_matchup only)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.domain.specialist import MatchSpecialistReport, SpecialistSignal
from worldcup_predictor.promotion.config import (
    CONFIG_VERSION_24C,
    MAX_XG_DISAGREEMENT,
    MAX_XG_TACTICS_OVER_DELTA,
    MAX_XG_TACTICS_SCORE_DELTA,
    MIN_XG_CONFIDENCE_GATE,
    XG_PROMOTION_AGENT_KEY,
)
from worldcup_predictor.promotion.models import PromotionMode, XGPromotionResult
from worldcup_predictor.promotion.shadow_store import XGPromotionShadowRecord, XGPromotionShadowStore

logger = logging.getLogger(__name__)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _promotion_mode(settings: Settings | None = None) -> PromotionMode:
    settings = settings or get_settings()
    mode = str(getattr(settings, "xg_promotion_mode", "shadow") or "shadow").lower()
    if mode in ("off", "shadow", "gated"):
        return mode  # type: ignore[return-value]
    return "shadow"


def _xg_signal(specialist: MatchSpecialistReport | None) -> SpecialistSignal | None:
    if not specialist:
        return None
    return specialist.signal(XG_PROMOTION_AGENT_KEY)


def _internal_goals_pressure(specialist: MatchSpecialistReport | None) -> float:
    if not specialist:
        return 50.0
    sig = specialist.signal("xg_chance_quality_intelligence_agent")
    if not sig or not sig.signals:
        return 50.0
    return float(sig.signals.get("goals_pressure_score") or 50.0)


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
        return False, "xg_intelligence_unavailable"
    if sig.status == "unavailable":
        return False, "xg_status_unavailable"
    block = sig.signals or {}
    plan = str(block.get("plan_support") or "none")
    xg_conf = float(block.get("xg_confidence") or 0)
    if plan != "full" and xg_conf < MIN_XG_CONFIDENCE_GATE:
        return False, "xg_plan_or_confidence_insufficient"
    if not block.get("comparison_available"):
        return False, "xg_comparison_unavailable"
    disagreement = float(block.get("disagreement_score") or 1.0)
    if disagreement > MAX_XG_DISAGREEMENT:
        return False, "xg_disagreement_above_gate"
    if block.get("xg_total") is None:
        return False, "xg_total_missing"
    return True, "gates_passed"


def compute_xg_promotion(
    *,
    specialist: MatchSpecialistReport | None,
    baseline_tactics_score: float,
    baseline_tactics_over: float,
    competition_key: str = "world_cup_2026",
    is_placeholder: bool = False,
    fixture_id: int | None = None,
    settings: Settings | None = None,
) -> XGPromotionResult:
    """Compute bounded tactics_matchup promotion from XGIntelligenceAgent."""
    settings = settings or get_settings()
    mode = _promotion_mode(settings)
    empty = XGPromotionResult(
        baseline_tactics_score=baseline_tactics_score,
        promoted_tactics_score=baseline_tactics_score,
        mode=mode,
    )
    if mode == "off":
        return empty

    sig = _xg_signal(specialist)
    passed, reason = _gate_passed(
        sig,
        competition_key=competition_key,
        is_placeholder=is_placeholder,
    )

    if not passed or sig is None:
        result = XGPromotionResult(
            xg_promotion_reason=reason,
            baseline_tactics_score=baseline_tactics_score,
            promoted_tactics_score=baseline_tactics_score,
            mode=mode,
            gate_passed=False,
        )
        _maybe_log_shadow(result, fixture_id=fixture_id, settings=settings)
        return result

    block = sig.signals or {}
    xg_conf = float(block.get("xg_confidence") or 0)
    xg_total = float(block.get("xg_total") or 2.5)
    supports = bool(block.get("xg_supports_internal", True))

    internal_pressure = _internal_goals_pressure(specialist)
    raw_adjust = 0.6 * (xg_total - 2.5) * 10 + 0.4 * (internal_pressure - 50) * 0.1
    raw_adjust = _clamp(raw_adjust, -MAX_XG_TACTICS_SCORE_DELTA, MAX_XG_TACTICS_SCORE_DELTA)

    if not supports:
        reason = "gates_passed_trace_only_internal_divergence"
        score_delta = 0.0
        over_delta = 0.0
    else:
        reason = "sportmonks_xg_tactics_blend"
        promoted_target = (baseline_tactics_score + baseline_tactics_score + raw_adjust) / 2
        score_delta = _clamp(
            promoted_target - baseline_tactics_score,
            -MAX_XG_TACTICS_SCORE_DELTA,
            MAX_XG_TACTICS_SCORE_DELTA,
        )
        over_delta = _clamp((xg_total - 2.5) * 0.25, -MAX_XG_TACTICS_OVER_DELTA, MAX_XG_TACTICS_OVER_DELTA)

    promoted_score = _clamp(baseline_tactics_score + score_delta, 0.0, 100.0)
    applied = mode == "gated" and supports
    promoted_if_applied = promoted_score if applied else baseline_tactics_score

    result = XGPromotionResult(
        xg_promotion_active=True,
        xg_delta_score=round(score_delta, 2),
        xg_delta_over=round(over_delta, 4),
        xg_promotion_reason=reason,
        xg_promotion_confidence=round(xg_conf, 1),
        baseline_tactics_score=round(baseline_tactics_score, 2),
        promoted_tactics_score=round(promoted_score if mode == "shadow" else promoted_if_applied, 1),
        mode=mode,
        gate_passed=True,
        applied=applied,
    )

    _maybe_log_shadow(result, fixture_id=fixture_id, settings=settings)
    return result


def apply_xg_promotion_to_factor(
    baseline_score: float,
    baseline_over: float,
    promotion: XGPromotionResult,
) -> tuple[float, float]:
    """Apply xG promotion when mode=gated, active, and internal agreement."""
    if not promotion.xg_promotion_active or promotion.mode != "gated" or not promotion.applied:
        return baseline_score, baseline_over
    score = _clamp(baseline_score + promotion.xg_delta_score, 0.0, 100.0)
    over = baseline_over + promotion.xg_delta_over
    return score, over


def _maybe_log_shadow(
    result: XGPromotionResult,
    *,
    fixture_id: int | None,
    settings: Settings | None,
) -> None:
    if result.mode not in ("shadow", "gated") or fixture_id is None:
        return
    settings = settings or get_settings()
    path = getattr(settings, "xg_promotion_shadow_path", "data/shadow/xg_promotion_shadow.jsonl")
    store = XGPromotionShadowStore(path)
    try:
        store.append(
            XGPromotionShadowRecord(
                fixture_id=int(fixture_id),
                timestamp=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                mode=result.mode,
                config_version=CONFIG_VERSION_24C,
                baseline_tactics_score=result.baseline_tactics_score,
                promoted_tactics_score=result.promoted_tactics_score,
                xg_delta_score=result.xg_delta_score,
                xg_delta_over=result.xg_delta_over,
                xg_promotion_active=result.xg_promotion_active,
                xg_promotion_reason=result.xg_promotion_reason,
                applied=result.applied,
                gate_passed=result.gate_passed,
            )
        )
    except OSError:
        logger.debug("xg promotion shadow log skipped fixture=%s", fixture_id)
