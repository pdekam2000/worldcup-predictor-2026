"""Expected lineup promotion adapter — Phase 24A."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.domain.specialist import MatchSpecialistReport, SpecialistSignal
from worldcup_predictor.promotion.config import (
    CONFIG_VERSION,
    MAX_CONFIDENCE_BOOST,
    MAX_CONFIDENCE_REDUCE,
    MAX_LINEUP_EDGE_DELTA,
    MAX_LINEUP_SCORE_DELTA,
    PROMOTION_AGENT_KEY,
    WEIGHTS_EXPECTED,
    WEIGHTS_OFFICIAL,
)
from worldcup_predictor.promotion.models import ExpectedLineupPromotionResult, PromotionMode
from worldcup_predictor.promotion.shadow_store import (
    ExpectedLineupPromotionShadowRecord,
    ExpectedLineupPromotionShadowStore,
)

logger = logging.getLogger(__name__)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _promotion_mode(settings: Settings | None = None) -> PromotionMode:
    settings = settings or get_settings()
    mode = str(getattr(settings, "expected_lineup_promotion_mode", "shadow") or "shadow").lower()
    if mode in ("off", "shadow", "gated"):
        return mode  # type: ignore[return-value]
    return "shadow"


def _official_lineups(specialist: MatchSpecialistReport | None) -> bool:
    if not specialist:
        return False
    lv2 = specialist.signal("lineup_intelligence_agent")
    if not lv2 or not lv2.signals:
        return False
    home = lv2.signals.get("home") or {}
    away = lv2.signals.get("away") or {}
    return bool(home.get("official_lineup") or away.get("official_lineup"))


def _baseline_v2_strength(specialist: MatchSpecialistReport | None) -> float:
    if not specialist:
        return 35.0
    lv2 = specialist.signal("lineup_intelligence_agent")
    if lv2 and lv2.signals:
        home = lv2.signals.get("home") or {}
        away = lv2.signals.get("away") or {}
        return (
            float(home.get("lineup_strength", 35)) + float(away.get("lineup_strength", 35))
        ) / 2
    la = specialist.signal("lineup_agent")
    if la and la.signals:
        return float(la.signals.get("lineup_confidence_score", 35))
    return 35.0


def _expected_signal(specialist: MatchSpecialistReport | None) -> SpecialistSignal | None:
    if not specialist:
        return None
    return specialist.signal(PROMOTION_AGENT_KEY)


def _history_from_signal(sig: SpecialistSignal) -> dict[str, Any]:
    block = sig.signals or {}
    return {
        "comparison_available": bool(block.get("comparison_available")),
        "confirmed_available": bool(block.get("confirmed_available")),
        "player_overlap_pct": block.get("player_overlap_pct"),
        "surprise_starters": block.get("surprise_starters") or [],
        "missed_expected": block.get("missed_expected") or [],
        "from_cache": bool(block.get("from_cache")),
    }


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
        return False, "expected_lineup_unavailable"
    if sig.status == "unavailable":
        return False, "expected_lineup_status_unavailable"
    block = sig.signals or {}
    if not block.get("data_sources"):
        return False, "no_expected_lineup_sources"
    return True, "gates_passed"


def compute_expected_lineup_promotion(
    *,
    specialist: MatchSpecialistReport | None,
    baseline_lineup_score: float,
    baseline_lineup_edge: float,
    competition_key: str = "world_cup_2026",
    is_placeholder: bool = False,
    fixture_id: int | None = None,
    settings: Settings | None = None,
) -> ExpectedLineupPromotionResult:
    """Compute bounded lineup_strength promotion from ExpectedLineupAgent signal."""
    settings = settings or get_settings()
    mode = _promotion_mode(settings)
    empty = ExpectedLineupPromotionResult(
        baseline_lineup_score=baseline_lineup_score,
        promoted_lineup_score=baseline_lineup_score,
        mode=mode,
    )
    if mode == "off":
        return empty

    sig = _expected_signal(specialist)
    passed, reason = _gate_passed(
        sig,
        competition_key=competition_key,
        is_placeholder=is_placeholder,
    )
    history = _history_from_signal(sig) if sig else {}

    if not passed or sig is None:
        result = ExpectedLineupPromotionResult(
            lineup_promotion_reason=reason,
            expected_vs_confirmed_history=history,
            baseline_lineup_score=baseline_lineup_score,
            promoted_lineup_score=baseline_lineup_score,
            mode=mode,
            gate_passed=False,
        )
        _maybe_log_shadow(result, fixture_id=fixture_id, settings=settings)
        return result

    block = sig.signals or {}
    expected_xi = float(block.get("expected_xi_quality") or baseline_lineup_score)
    lineup_conf = float(block.get("lineup_confidence") or 35.0)
    v2_strength = _baseline_v2_strength(specialist)
    official = _official_lineups(specialist)

    w_v2, w_exp, w_conf = WEIGHTS_OFFICIAL if official else WEIGHTS_EXPECTED
    composite = w_v2 * v2_strength + w_exp * expected_xi + w_conf * lineup_conf
    composite = _clamp(composite, 25.0, 95.0)

    raw_delta = composite - baseline_lineup_score
    if not block.get("lineup_supports_internal", True):
        raw_delta *= 0.5
        reason = "gates_passed_dampened_internal_divergence"
    else:
        reason = "expected_lineup_composite_blend"

    score_delta = _clamp(raw_delta, -MAX_LINEUP_SCORE_DELTA, MAX_LINEUP_SCORE_DELTA)
    edge_delta = 0.0
    if official and block.get("comparison_available") and block.get("player_overlap_pct") is not None:
        try:
            overlap = float(block["player_overlap_pct"])
            if overlap >= 85:
                edge_delta = _clamp(0.015, 0, MAX_LINEUP_EDGE_DELTA)
        except (TypeError, ValueError):
            pass

    conf_delta = 0.0
    late_news = str(block.get("late_news_risk") or "low")
    if late_news == "high":
        conf_delta -= min(4.0, MAX_CONFIDENCE_REDUCE)
        reason += ";late_news_risk"
    elif lineup_conf < 45 and not official:
        conf_delta -= min(2.0, MAX_CONFIDENCE_REDUCE)
        reason += ";low_lineup_confidence"
    elif official and block.get("confirmed_available"):
        conf_delta += min(2.0, MAX_CONFIDENCE_BOOST)
        reason += ";confirmed_overlap_window"

    conf_delta = _clamp(conf_delta, -MAX_CONFIDENCE_REDUCE, MAX_CONFIDENCE_BOOST)
    promoted_score = _clamp(baseline_lineup_score + score_delta, 0.0, 100.0)
    applied = mode == "gated"
    promoted_score_if_applied = promoted_score if applied else baseline_lineup_score

    result = ExpectedLineupPromotionResult(
        lineup_promotion_active=True,
        lineup_delta_score=round(score_delta, 2),
        lineup_delta_edge=round(edge_delta, 4),
        lineup_promotion_reason=reason,
        lineup_promotion_confidence=round(lineup_conf, 1),
        confidence_delta=round(conf_delta, 2),
        expected_vs_confirmed_history=history,
        baseline_lineup_score=round(baseline_lineup_score, 2),
        promoted_lineup_score=round(promoted_score if mode == "shadow" else promoted_score_if_applied, 2),
        mode=mode,
        gate_passed=True,
        applied=applied,
    )

    _maybe_log_shadow(result, fixture_id=fixture_id, settings=settings)
    return result


def apply_lineup_promotion_to_factor(
    baseline_score: float,
    baseline_edge: float,
    promotion: ExpectedLineupPromotionResult,
) -> tuple[float, float]:
    """Apply promotion deltas when mode=gated and active."""
    if not promotion.lineup_promotion_active or promotion.mode != "gated" or not promotion.applied:
        return baseline_score, baseline_edge
    score = _clamp(baseline_score + promotion.lineup_delta_score, 0.0, 100.0)
    edge = baseline_edge + promotion.lineup_delta_edge
    return score, edge


def _maybe_log_shadow(
    result: ExpectedLineupPromotionResult,
    *,
    fixture_id: int | None,
    settings: Settings | None,
) -> None:
    if result.mode not in ("shadow", "gated") or fixture_id is None:
        return
    settings = settings or get_settings()
    path = getattr(
        settings,
        "expected_lineup_promotion_shadow_path",
        "data/shadow/expected_lineup_promotion_shadow.jsonl",
    )
    store = ExpectedLineupPromotionShadowStore(path)
    try:
        store.append(
            ExpectedLineupPromotionShadowRecord(
                fixture_id=int(fixture_id),
                timestamp=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                mode=result.mode,
                config_version=CONFIG_VERSION,
                baseline_lineup_score=result.baseline_lineup_score,
                promoted_lineup_score=result.promoted_lineup_score,
                lineup_delta_score=result.lineup_delta_score,
                confidence_delta=result.confidence_delta,
                lineup_promotion_active=result.lineup_promotion_active,
                lineup_promotion_reason=result.lineup_promotion_reason,
                applied=result.applied,
                gate_passed=result.gate_passed,
                expected_vs_confirmed_history=result.expected_vs_confirmed_history,
            )
        )
    except OSError:
        logger.debug("expected lineup promotion shadow log skipped fixture=%s", fixture_id)
