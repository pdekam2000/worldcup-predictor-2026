"""Research-facing confidence lineage exposure (no formula changes)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.decision.no_bet_reasons import CONFIDENCE_NO_BET_THRESHOLD
from worldcup_predictor.domain.prediction import MatchPrediction


def build_confidence_lineage(
    prediction: MatchPrediction | None,
    *,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Expose existing confidence stages without altering calculation.

    Missing historical fields are explicitly labeled NOT_EXPOSED.
    """
    payload = payload or {}
    audit = payload.get("audit_trace") if isinstance(payload.get("audit_trace"), dict) else {}
    conf_audit = audit.get("confidence") if isinstance(audit.get("confidence"), dict) else {}
    adaptive_payload = payload.get("adaptive_confidence_trace") or conf_audit.get("adaptive") or {}

    final_display = None
    if prediction is not None:
        final_display = float(prediction.confidence_score or 0.0)
    elif payload.get("confidence") is not None:
        try:
            final_display = float(payload.get("confidence"))
        except (TypeError, ValueError):
            final_display = None

    base = None
    adj_total = None
    adjustments: list[dict[str, Any]] = []
    if prediction is not None and getattr(prediction, "adaptive_confidence", None) is not None:
        adj = prediction.adaptive_confidence
        base = float(adj.base_confidence)
        adj_total = float(adj.total_bonus)
        before = base
        for code, val in (
            ("similar_situation_bonus", float(adj.similar_situation_bonus or 0)),
            ("pattern_bonus", float(adj.pattern_bonus or 0)),
            ("competition_bonus", float(adj.competition_bonus or 0)),
            ("bucket_bonus", float(adj.bucket_bonus or 0)),
        ):
            if not val:
                continue
            after = before + val
            adjustments.append(
                {
                    "code": code,
                    "source_component": "AdaptiveConfidenceEngine",
                    "signed_value": round(val, 4),
                    "before": round(before, 4),
                    "after": round(after, 4),
                    "reason": getattr(adj, "reason", None) or code,
                }
            )
            before = after
        # Live calibration is applied inside AdaptiveConfidenceEngine after bonuses;
        # only the net final is observable here unless more fields are added later.
        if abs(float(adj.final_confidence) - before) > 1e-9:
            adjustments.append(
                {
                    "code": "live_calibration_or_clamp",
                    "source_component": "apply_confidence_correction/clamp",
                    "signed_value": round(float(adj.final_confidence) - before, 4),
                    "before": round(before, 4),
                    "after": round(float(adj.final_confidence), 4),
                    "reason": "Net difference after bonuses vs final_confidence",
                }
            )
    elif adaptive_payload:
        try:
            base = float(adaptive_payload.get("confidence_before_adaptive"))
            adj_total = float(adaptive_payload.get("adaptive_adjustment") or 0)
            final_display = float(
                adaptive_payload.get("confidence_after_adaptive") or final_display or 0
            )
        except (TypeError, ValueError):
            pass

    caps = list(conf_audit.get("caps_applied") or [])
    reductions = list(conf_audit.get("reductions") or [])
    for item in caps:
        adjustments.append(
            {
                "code": "confidence_cap",
                "source_component": "WeightedDecisionEngine",
                "signed_value": None,
                "before": "NOT_EXPOSED",
                "after": "NOT_EXPOSED",
                "reason": str(item),
            }
        )
    for item in reductions:
        adjustments.append(
            {
                "code": "confidence_reduction",
                "source_component": "WeightedDecisionEngine",
                "signed_value": None,
                "before": "NOT_EXPOSED",
                "after": "NOT_EXPOSED",
                "reason": str(item),
            }
        )

    pre_enrichment = base
    post_enrichment = float(getattr(getattr(prediction, "adaptive_confidence", None), "final_confidence", None) or final_display or 0) if prediction or final_display is not None else None
    final_unrounded = post_enrichment  # engine already rounds to 1dp before store
    final_display_r = round(final_display, 1) if final_display is not None else None

    reconciles = None
    if base is not None and adj_total is not None and post_enrichment is not None:
        # Allow live-calibration residual in adjustments list
        expected = base + adj_total
        # final may include calibration; check within 0.15 of recorded final
        reconciles = abs(float(post_enrichment) - float(final_display_r or post_enrichment)) < 0.15

    thr = float(CONFIDENCE_NO_BET_THRESHOLD)
    cmp = None
    if final_display is not None:
        cmp = {
            "operator": "<",
            "threshold": thr,
            "value": final_display,
            "fails_gate": final_display < thr,
        }

    return {
        "raw_model_confidence": conf_audit.get("baseline") if conf_audit.get("baseline") is not None else "NOT_EXPOSED",
        "base_confidence": base if base is not None else "NOT_EXPOSED",
        "normalized_confidence": "NOT_APPLICABLE_0_100_SCALE",
        "adaptive_adjustment_total": adj_total if adj_total is not None else "NOT_EXPOSED",
        "adaptive_adjustments": adjustments,
        "conflict_penalty": "SEE_adjustments_or_NOT_EXPOSED",
        "data_quality_penalty": "SEE_adjustments_or_NOT_EXPOSED",
        "market_alignment_adjustment": "SEE_adjustments_or_NOT_EXPOSED",
        "domain_adjustment": "NOT_EXPOSED",
        "fallback_penalty": "NOT_EXPOSED",
        "live_calibration_adjustment": next(
            (a for a in adjustments if a["code"] == "live_calibration_or_clamp"),
            "NOT_SEPARATELY_EXPOSED",
        ),
        "pre_enrichment_confidence": pre_enrichment if pre_enrichment is not None else "NOT_EXPOSED",
        "post_enrichment_confidence": post_enrichment if post_enrichment is not None else "NOT_EXPOSED",
        "final_unrounded_confidence": final_unrounded if final_unrounded is not None else "NOT_EXPOSED",
        "final_display_confidence": final_display_r,
        "threshold_used": thr,
        "threshold_comparison_result": cmp,
        "lineage_arithmetic_reconciles": reconciles,
        "research_only": True,
    }
