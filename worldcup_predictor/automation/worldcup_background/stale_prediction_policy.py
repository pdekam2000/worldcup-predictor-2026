"""Phase 36C/36B — invalidate stale/placeholder stored predictions safely."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.automation.worldcup_background.prediction_store_guard import (
    is_provider_env_placeholder_payload,
    payload_has_placeholder_data_reason,
)
from worldcup_predictor.prediction.engine_versions import (
    ADAPTIVE_CONFIDENCE_VERSION,
    NATIONAL_TEAM_INTELLIGENCE_VERSION,
    PREDICTION_ENGINE_VERSION,
)

# Confidence below this with strong market lean suggests corrupt/stale cache.
_LOW_CONFIDENCE_THRESHOLD = 15.0
_STRONG_MARKET_LEAN_THRESHOLD = 40.0
_UNEXPLAINED_DROP_GAP = 5.0

INVALIDATED_REASON_PROVIDER_ENV = "provider_env_missing_placeholder"


def _float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _max_ft_probability(payload: dict[str, Any]) -> float:
    probs = payload.get("probabilities") or {}
    values = [
        _float(probs.get("home_win")),
        _float(probs.get("draw")),
        _float(probs.get("away_win")),
    ]
    dm = (payload.get("detailed_markets") or {}).get("match_winner") or {}
    ft = dm.get("probabilities") or {}
    if ft:
        values.extend([_float(ft.get("home_win")), _float(ft.get("draw")), _float(ft.get("away_win"))])
    return max(values) if values else 0.0


def _adaptive_trace(payload: dict[str, Any]) -> dict[str, Any] | None:
    trace = payload.get("adaptive_confidence_trace")
    if isinstance(trace, dict) and trace:
        return trace
    audit = payload.get("audit_trace") or {}
    conf = audit.get("confidence") or {}
    adaptive = conf.get("adaptive")
    return adaptive if isinstance(adaptive, dict) and adaptive else None


def _has_placeholder_flag(payload: dict[str, Any]) -> bool:
    if is_provider_env_placeholder_payload(payload):
        return True

    if payload.get("is_placeholder") is True and payload_has_placeholder_data_reason(payload):
        return True

    audit = payload.get("audit_trace") or {}
    conf = audit.get("confidence") or {}
    reasons = conf.get("no_bet_reasons") or []
    if any("placeholder" in str(r).lower() for r in reasons):
        if payload.get("prediction_engine_version") == PREDICTION_ENGINE_VERSION:
            return True

    generated_by = str(payload.get("generated_by") or payload.get("cache_source") or "")
    if generated_by == "background_daily" and payload_has_placeholder_data_reason(payload):
        return True
    return False


def is_stored_prediction_quality_valid(payload: dict[str, Any]) -> tuple[bool, str]:
    """
    Return (valid, reason). Invalid entries should be refreshed on next request/cycle.
    """
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        return False, "invalid_payload"

    if payload.get("invalidated_reason") == INVALIDATED_REASON_PROVIDER_ENV:
        return False, INVALIDATED_REASON_PROVIDER_ENV

    engine_ver = payload.get("prediction_engine_version")
    if engine_ver != PREDICTION_ENGINE_VERSION:
        return False, f"engine_version_stale:{engine_ver or 'missing'}"

    nat = payload.get("national_team_intelligence") or {}
    nat_ver = nat.get("version")
    if nat_ver != NATIONAL_TEAM_INTELLIGENCE_VERSION:
        return False, f"national_intel_not_{NATIONAL_TEAM_INTELLIGENCE_VERSION}:{nat_ver or 'missing'}"

    if _has_placeholder_flag(payload):
        return False, "placeholder_or_legacy_background"

    adaptive = _adaptive_trace(payload)
    stored_conf = _float(payload.get("confidence"))
    audit = payload.get("audit_trace") or {}
    wde_final = _float((audit.get("confidence") or {}).get("final"))

    if adaptive is None and wde_final > 0 and abs(stored_conf - wde_final) > _UNEXPLAINED_DROP_GAP:
        return False, "missing_adaptive_trace_unexplained_drop"

    if stored_conf < _LOW_CONFIDENCE_THRESHOLD and _max_ft_probability(payload) >= _STRONG_MARKET_LEAN_THRESHOLD:
        return False, "low_confidence_high_probability_mismatch"

    if payload.get("adaptive_confidence_version") != ADAPTIVE_CONFIDENCE_VERSION:
        return False, f"adaptive_version_stale:{payload.get('adaptive_confidence_version') or 'missing'}"

    return True, "ok"


def should_invalidate_stored_row(payload: dict[str, Any], *, source: str = "") -> tuple[bool, str]:
    """Phase 36B — detect rows to invalidate before repair refresh."""
    if not isinstance(payload, dict):
        return False, ""
    if is_provider_env_placeholder_payload(payload):
        return True, INVALIDATED_REASON_PROVIDER_ENV
    if _has_placeholder_flag(payload):
        return True, "placeholder_or_legacy_background"
    gen = str(payload.get("generated_by") or source or "")
    if gen.startswith("phase34b_test") and _float(payload.get("confidence")) <= 15.0:
        if payload_has_placeholder_data_reason(payload):
            return True, INVALIDATED_REASON_PROVIDER_ENV
    return False, ""
