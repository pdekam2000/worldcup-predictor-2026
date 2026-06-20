"""Safe audit / promotion trace for prediction API responses — no secrets or raw provider data."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.quota.prediction_cache_policy import PREDICTION_CACHE_SCHEMA_VERSION


def _float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).lower() in ("true", "1", "yes")


def _agent_status(agents: dict[str, Any], name: str) -> dict[str, Any]:
    row = agents.get(name) if isinstance(agents, dict) else None
    if not isinstance(row, dict):
        return {"status": "missing", "impact_score": None, "domain": None}
    return {
        "status": row.get("status"),
        "impact_score": row.get("impact_score"),
        "domain": row.get("domain"),
        "status_reason": row.get("status_reason"),
    }


def build_audit_trace(
    prediction: MatchPrediction | None,
    specialist_summary: dict[str, Any] | None,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """
    Build a safe, JSON-serializable audit trace for API clients.

    Uses WDE metadata and audit_report when present; falls back to specialist
    statuses for cached payloads that predate audit_trace serialization.
    """
    settings = settings or get_settings()
    md = (prediction.metadata if prediction else None) or {}
    trace = prediction.audit_report.trace if prediction and prediction.audit_report else None
    agents = (specialist_summary or {}).get("agents") or {}

    promotion_modes = {
        "expected_lineup": settings.expected_lineup_promotion_mode,
        "tournament_context": settings.tournament_context_promotion_mode,
        "xg": settings.xg_promotion_mode,
        "sportmonks_prediction": settings.sportmonks_prediction_promotion_mode,
        "lambda_bridge": settings.lambda_bridge_mode,
        "rule_a_gate": settings.rule_a_gate_mode,
        "real_world_validation": settings.real_world_validation_mode,
    }

    def promo_block(
        *,
        mode: str,
        active_key: str,
        delta_key: str,
        reason_key: str,
        confidence_key: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        active = _bool(getattr(trace, active_key, None) if trace else md.get(active_key))
        block: dict[str, Any] = {
            "mode": mode,
            "shadow_active": mode == "shadow",
            "gated_active": mode == "gated" and active,
            "promotion_applied": active,
            "delta_score": _float(getattr(trace, delta_key, None) if trace else md.get(delta_key)),
            "reason": str(getattr(trace, reason_key, None) if trace else md.get(reason_key) or ""),
        }
        if confidence_key:
            block["confidence"] = _float(
                getattr(trace, confidence_key, None) if trace else md.get(confidence_key)
            )
        if extra:
            block.update(extra)
        return block

    out: dict[str, Any] = {
        "cache_schema_version": PREDICTION_CACHE_SCHEMA_VERSION,
        "decision_engine": md.get("decision_engine", "unknown"),
        "watch_only": _bool(getattr(trace, "watch_only", None) if trace else md.get("watch_only")),
        "promotion_modes": promotion_modes,
        "combined_promotion_confidence_delta": _float(
            getattr(trace, "combined_promotion_confidence_delta", None)
            if trace
            else md.get("combined_promotion_confidence_delta")
        ),
        "expected_lineup": {
            **_agent_status(agents, "expected_lineup_agent"),
            **promo_block(
                mode=settings.expected_lineup_promotion_mode,
                active_key="lineup_promotion_active",
                delta_key="lineup_delta_score",
                reason_key="lineup_promotion_reason",
                confidence_key="lineup_promotion_confidence",
            ),
        },
        "tournament_context": {
            **_agent_status(agents, "tournament_context_agent"),
            **promo_block(
                mode=settings.tournament_context_promotion_mode,
                active_key="context_promotion_active",
                delta_key="context_delta_score",
                reason_key="context_promotion_reason",
                confidence_key="context_promotion_confidence",
                extra={
                    "must_win_influence": _float(
                        getattr(trace, "must_win_influence", None) if trace else md.get("must_win_influence")
                    ),
                    "rotation_context_influence": _float(
                        getattr(trace, "rotation_context_influence", None)
                        if trace
                        else md.get("rotation_context_influence")
                    ),
                    "draw_acceptability_influence": _float(
                        getattr(trace, "draw_acceptability_influence", None)
                        if trace
                        else md.get("draw_acceptability_influence")
                    ),
                },
            ),
        },
        "xg_intelligence": {
            **_agent_status(agents, "xg_intelligence_agent"),
            **promo_block(
                mode=settings.xg_promotion_mode,
                active_key="xg_promotion_active",
                delta_key="xg_delta_score",
                reason_key="xg_promotion_reason",
                confidence_key="xg_promotion_confidence",
            ),
        },
        "sportmonks_prediction": {
            **_agent_status(agents, "sportmonks_prediction_agent"),
            **promo_block(
                mode=settings.sportmonks_prediction_promotion_mode,
                active_key="sportmonks_promotion_active",
                delta_key="sportmonks_confidence_delta",
                reason_key="sportmonks_promotion_reason",
                extra={
                    "disagreement_signal": str(
                        getattr(trace, "sportmonks_disagreement_signal", None)
                        if trace
                        else md.get("sportmonks_disagreement_signal")
                        or ""
                    ),
                    "no_bet_review_trace": _bool(
                        getattr(trace, "sportmonks_no_bet_review_trace", None)
                        if trace
                        else md.get("sportmonks_no_bet_review_trace")
                    ),
                },
            ),
        },
    }

    if trace:
        out["confidence"] = {
            "baseline": trace.baseline_confidence,
            "final": trace.final_confidence,
            "caps_applied": list(trace.confidence_caps_applied or []),
            "reductions": list(trace.confidence_reductions or []),
            "no_bet_reasons": list(trace.no_bet_reasons or []),
        }

    return out
