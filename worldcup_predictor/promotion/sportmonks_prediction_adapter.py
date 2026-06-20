"""Sportmonks prediction promotion adapter — Phase 24C (confidence/audit only)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.domain.specialist import MatchSpecialistReport, SpecialistSignal
from worldcup_predictor.promotion.config import (
    CONFIG_VERSION_24C,
    MAX_SPORTMONKS_CONFIDENCE_BOOST,
    MAX_SPORTMONKS_CONFIDENCE_REDUCE,
    MIN_SPORTMONKS_CONFIDENCE_GATE,
    SPORTMONKS_PROMOTION_AGENT_KEY,
)
from worldcup_predictor.promotion.models import PromotionMode, SportmonksPredictionPromotionResult
from worldcup_predictor.promotion.shadow_store import (
    SportmonksPredictionPromotionShadowRecord,
    SportmonksPredictionPromotionShadowStore,
)

logger = logging.getLogger(__name__)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _promotion_mode(settings: Settings | None = None) -> PromotionMode:
    settings = settings or get_settings()
    mode = str(getattr(settings, "sportmonks_prediction_promotion_mode", "shadow") or "shadow").lower()
    if mode in ("off", "shadow", "gated"):
        return mode  # type: ignore[return-value]
    return "shadow"


def _sm_signal(specialist: MatchSpecialistReport | None) -> SpecialistSignal | None:
    if not specialist:
        return None
    return specialist.signal(SPORTMONKS_PROMOTION_AGENT_KEY)


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
        return False, "sportmonks_prediction_unavailable"
    if sig.status == "unavailable":
        return False, "sportmonks_status_unavailable"
    block = sig.signals or {}
    has_data = bool(block.get("sportmonks_odds_available") or block.get("sportmonks_prediction_available"))
    if not has_data:
        return False, "no_sportmonks_data"
    sm_conf = float(block.get("sportmonks_confidence") or 0)
    if sm_conf < MIN_SPORTMONKS_CONFIDENCE_GATE:
        return False, "sportmonks_confidence_below_gate"
    return True, "gates_passed"


def _confidence_delta_from_conflict(
    conflict_level: str,
    recommendation: str,
    *,
    disagreement: float,
    consensus: float,
) -> float:
    delta = 0.0
    if conflict_level == "medium" or recommendation == "caution":
        delta -= 3.0
    if conflict_level == "high" or recommendation == "no_bet_review":
        delta -= 6.0
    if conflict_level == "high" and consensus < 50.0:
        delta -= 2.0
    if disagreement >= 0.40 and conflict_level == "high":
        delta = min(delta, -6.0)
    return _clamp(delta, -MAX_SPORTMONKS_CONFIDENCE_REDUCE, MAX_SPORTMONKS_CONFIDENCE_BOOST)


def compute_sportmonks_prediction_promotion(
    *,
    specialist: MatchSpecialistReport | None,
    internal_selection: str,
    competition_key: str = "world_cup_2026",
    is_placeholder: bool = False,
    fixture_id: int | None = None,
    settings: Settings | None = None,
) -> SportmonksPredictionPromotionResult:
    """Compute Sportmonks confidence/disagreement promotion — never changes 1X2."""
    settings = settings or get_settings()
    mode = _promotion_mode(settings)
    empty = SportmonksPredictionPromotionResult(mode=mode)
    if mode == "off":
        return empty

    sig = _sm_signal(specialist)
    passed, reason = _gate_passed(
        sig,
        competition_key=competition_key,
        is_placeholder=is_placeholder,
    )

    if not passed or sig is None:
        result = SportmonksPredictionPromotionResult(
            sportmonks_promotion_reason=reason,
            mode=mode,
            gate_passed=False,
        )
        _maybe_log_shadow(result, fixture_id=fixture_id, settings=settings)
        return result

    block = sig.signals or {}
    conflict = str(block.get("conflict_level") or "low")
    recommendation = str(block.get("recommendation") or "support_internal")
    disagreement = float(block.get("disagreement_vs_internal") or 0)
    consensus = float(block.get("consensus_with_internal") or 50)
    internal_lean = str(block.get("internal_lean") or internal_selection)
    sm_lean = str(block.get("sportmonks_lean") or "draw")

    conf_delta = _confidence_delta_from_conflict(
        conflict,
        recommendation,
        disagreement=disagreement,
        consensus=consensus,
    )
    if disagreement >= 0.25:
        reason = f"{reason};disagreement_{disagreement:.2f}"
    if sm_lean != internal_lean:
        reason += ";external_model_divergence_trace"
    if recommendation == "no_bet_review":
        reason += ";no_bet_review_trace"

    disagreement_signal = f"{conflict}:{disagreement:.3f}"
    applied = mode == "gated"
    effective_delta = conf_delta if applied else 0.0

    result = SportmonksPredictionPromotionResult(
        sportmonks_promotion_active=True,
        sportmonks_confidence_delta=round(effective_delta if applied else conf_delta, 2),
        sportmonks_disagreement_signal=disagreement_signal,
        sportmonks_promotion_reason=reason,
        no_bet_review_trace=recommendation == "no_bet_review",
        internal_lean=internal_lean,
        sportmonks_lean=sm_lean,
        conflict_level=conflict,
        mode=mode,
        gate_passed=True,
        applied=applied,
    )

    _maybe_log_shadow(result, fixture_id=fixture_id, settings=settings)
    return result


def _maybe_log_shadow(
    result: SportmonksPredictionPromotionResult,
    *,
    fixture_id: int | None,
    settings: Settings | None,
) -> None:
    if result.mode not in ("shadow", "gated") or fixture_id is None:
        return
    settings = settings or get_settings()
    path = getattr(
        settings,
        "sportmonks_prediction_promotion_shadow_path",
        "data/shadow/sportmonks_prediction_promotion_shadow.jsonl",
    )
    store = SportmonksPredictionPromotionShadowStore(path)
    try:
        store.append(
            SportmonksPredictionPromotionShadowRecord(
                fixture_id=int(fixture_id),
                timestamp=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                mode=result.mode,
                config_version=CONFIG_VERSION_24C,
                sportmonks_confidence_delta=result.sportmonks_confidence_delta,
                sportmonks_disagreement_signal=result.sportmonks_disagreement_signal,
                sportmonks_promotion_active=result.sportmonks_promotion_active,
                sportmonks_promotion_reason=result.sportmonks_promotion_reason,
                no_bet_review_trace=result.no_bet_review_trace,
                internal_lean=result.internal_lean,
                sportmonks_lean=result.sportmonks_lean,
                conflict_level=result.conflict_level,
                applied=result.applied,
                gate_passed=result.gate_passed,
            )
        )
    except OSError:
        logger.debug("sportmonks promotion shadow log skipped fixture=%s", fixture_id)
