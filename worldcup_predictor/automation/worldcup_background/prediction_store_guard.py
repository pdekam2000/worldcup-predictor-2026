"""Phase 36C — guard against storing provider-missing placeholder predictions."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.config.provider_readiness import assert_production_api_football


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def payload_has_placeholder_data_reason(payload: dict[str, Any]) -> bool:
    audit = payload.get("audit_trace") or {}
    reasons = (audit.get("confidence") or {}).get("no_bet_reasons") or []
    if any("placeholder" in str(r).lower() for r in reasons):
        return True
    if payload.get("is_placeholder") is True:
        return True
    if payload.get("provider_env_missing"):
        return True
    readiness = payload.get("provider_readiness") or {}
    if readiness.get("api_football_configured") is False:
        return True
    return False


def is_provider_env_placeholder_payload(payload: dict[str, Any]) -> bool:
    """True when payload was (or would be) generated without API-Football key."""
    readiness = payload.get("provider_readiness") or {}
    if readiness.get("api_football_configured") is False:
        return True
    if payload.get("provider_env_missing"):
        return True
    audit = payload.get("audit_trace") or {}
    reasons = (audit.get("confidence") or {}).get("no_bet_reasons") or []
    if "placeholder_data" in reasons and _float(payload.get("confidence")) <= 15.0:
        gen = str(payload.get("generated_by") or payload.get("cache_source") or "")
        if gen.startswith("phase34b") or "test" in gen or not readiness:
            return True
    return False


def existing_is_better(existing: dict[str, Any] | None, candidate: dict[str, Any]) -> bool:
    if not existing:
        return False
    if is_provider_env_placeholder_payload(candidate) and not is_provider_env_placeholder_payload(existing):
        return True
    if payload_has_placeholder_data_reason(candidate) and not payload_has_placeholder_data_reason(existing):
        return True
    return _float(existing.get("confidence")) > _float(candidate.get("confidence")) + 5.0


def evaluate_prediction_storage(
    payload: dict[str, Any],
    *,
    settings: Settings | None = None,
    prediction_is_placeholder: bool | None = None,
    existing_payload: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """
    Return (allow_store, reason).
    Blocks storing fresh production predictions when provider keys were missing.
    """
    settings = settings or get_settings()
    if not settings.api_football_configured:
        _write_diagnostic_shadow(payload, reason="provider_env_missing")
        return False, "provider_env_missing"

    placeholder = prediction_is_placeholder
    if placeholder is None:
        placeholder = payload.get("is_placeholder") is True or payload_has_placeholder_data_reason(payload)

    if placeholder and not settings.api_football_configured:
        return False, "provider_env_missing_placeholder"

    if is_provider_env_placeholder_payload(payload):
        if existing_is_better(existing_payload, payload):
            return False, "provider_env_missing_would_downgrade"
        return False, "provider_env_missing_placeholder"

    if existing_is_better(existing_payload, payload):
        return False, "would_downgrade_existing_non_placeholder"

    return True, "ok"


def _write_diagnostic_shadow(payload: dict[str, Any], *, reason: str) -> None:
    try:
        path = Path("data/shadow/provider_env_missing_predictions.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": time.time(),
            "reason": reason,
            "fixture_id": payload.get("fixture_id"),
            "confidence": payload.get("confidence"),
            "generated_by": payload.get("generated_by"),
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def assert_can_run_production_prediction(settings: Settings | None = None) -> None:
    assert_production_api_football(settings)
