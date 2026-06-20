"""Phase 26 — capture validation records from live predictions (shadow-only)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.validation.models import (
    IntelligenceSnapshots,
    PromotionTrackSnapshot,
    RealWorldValidationRecord,
)
from worldcup_predictor.validation.store import RealWorldValidationStore

logger = logging.getLogger(__name__)

PROMOTION_KEYS = ("24a_lineup", "24b_context", "24c_xg", "24c_sportmonks")


def _signal_block(specialist: Any, name: str) -> dict[str, Any]:
    if not specialist:
        return {}
    sig = specialist.signal(name) if hasattr(specialist, "signal") else None
    if not sig:
        return {}
    block = getattr(sig, "signals", None) or {}
    return dict(block) if isinstance(block, dict) else {}


def _confidence_bucket(score: float) -> str:
    if score >= 70:
        return "high_70+"
    if score >= 55:
        return "medium_55_69"
    if score >= 40:
        return "low_40_54"
    return "very_low_below_40"


def build_snapshots(report: Any, specialist: Any) -> IntelligenceSnapshots:
    lineup = _signal_block(specialist, "lineup_intelligence_agent")
    if not lineup and report and getattr(report, "lineups", None):
        lineup = {"available": bool(report.lineups.get("available")), "source": "report_lineups"}

    return IntelligenceSnapshots(
        lineup_snapshot=lineup,
        expected_lineup_snapshot=_signal_block(specialist, "expected_lineup_agent"),
        tournament_context_snapshot=_signal_block(specialist, "tournament_context_agent"),
        xg_snapshot=_signal_block(specialist, "xg_intelligence_agent"),
        sportmonks_prediction_snapshot=_signal_block(specialist, "sportmonks_prediction_agent"),
    )


def build_promotion_tracks(
    *,
    trace: Any,
    metadata: dict[str, Any],
    settings: Settings,
) -> tuple[list[PromotionTrackSnapshot], dict[str, float]]:
    tr = trace
    md = metadata or {}
    tracks: list[PromotionTrackSnapshot] = []
    deltas: dict[str, float] = {
        "lineup_delta_score": float(getattr(tr, "lineup_delta_score", 0) if tr else md.get("lineup_delta_score", 0) or 0),
        "context_delta_score": float(getattr(tr, "context_delta_score", 0) if tr else md.get("context_delta_score", 0) or 0),
        "xg_delta_score": float(getattr(tr, "xg_delta_score", 0) if tr else md.get("xg_delta_score", 0) or 0),
        "sportmonks_confidence_delta": float(
            getattr(tr, "sportmonks_confidence_delta", 0) if tr else md.get("sportmonks_confidence_delta", 0) or 0
        ),
        "combined_promotion_confidence_delta": float(
            getattr(tr, "combined_promotion_confidence_delta", 0) if tr else md.get("combined_promotion_confidence_delta", 0) or 0
        ),
    }

    tracks.append(
        PromotionTrackSnapshot(
            promotion_key="24a_lineup",
            signal_available=bool(getattr(tr, "lineup_promotion_active", False) if tr else md.get("lineup_promotion_active") == "True"),
            confidence=float(getattr(tr, "lineup_promotion_confidence", 0) if tr else float(md.get("lineup_promotion_confidence") or 0)),
            delta=deltas["lineup_delta_score"],
            active=bool(getattr(tr, "lineup_promotion_active", False) if tr else md.get("lineup_promotion_active") == "True"),
            reason=str(getattr(tr, "lineup_promotion_reason", "") if tr else md.get("lineup_promotion_reason") or ""),
            mode=settings.expected_lineup_promotion_mode,
        )
    )
    tracks.append(
        PromotionTrackSnapshot(
            promotion_key="24b_context",
            signal_available=bool(getattr(tr, "context_promotion_active", False) if tr else md.get("context_promotion_active") == "True"),
            confidence=float(getattr(tr, "context_promotion_confidence", 0) if tr else float(md.get("context_promotion_confidence") or 0)),
            delta=deltas["context_delta_score"],
            disagreement=float(getattr(tr, "draw_acceptability_influence", 0) or 0) if tr else None,
            active=bool(getattr(tr, "context_promotion_active", False) if tr else md.get("context_promotion_active") == "True"),
            reason=str(getattr(tr, "context_promotion_reason", "") if tr else md.get("context_promotion_reason") or ""),
            mode=settings.tournament_context_promotion_mode,
        )
    )
    tracks.append(
        PromotionTrackSnapshot(
            promotion_key="24c_xg",
            signal_available=bool(getattr(tr, "xg_promotion_active", False) if tr else md.get("xg_promotion_active") == "True"),
            confidence=float(getattr(tr, "xg_promotion_confidence", 0) if tr else float(md.get("xg_promotion_confidence") or 0)),
            delta=deltas["xg_delta_score"],
            active=bool(getattr(tr, "xg_promotion_active", False) if tr else md.get("xg_promotion_active") == "True"),
            reason=str(getattr(tr, "xg_promotion_reason", "") if tr else md.get("xg_promotion_reason") or ""),
            mode=settings.xg_promotion_mode,
        )
    )
    sm_signal = str(getattr(tr, "sportmonks_disagreement_signal", "") if tr else md.get("sportmonks_disagreement_signal") or "")
    sm_parts = sm_signal.split(":") if sm_signal else []
    sm_disagreement = float(sm_parts[1]) if len(sm_parts) == 2 else None
    tracks.append(
        PromotionTrackSnapshot(
            promotion_key="24c_sportmonks",
            signal_available=bool(getattr(tr, "sportmonks_promotion_active", False) if tr else md.get("sportmonks_promotion_active") == "True"),
            confidence=0.0,
            delta=deltas["sportmonks_confidence_delta"],
            disagreement=sm_disagreement,
            active=bool(getattr(tr, "sportmonks_promotion_active", False) if tr else md.get("sportmonks_promotion_active") == "True"),
            reason=str(getattr(tr, "sportmonks_promotion_reason", "") if tr else md.get("sportmonks_promotion_reason") or ""),
            mode=settings.sportmonks_prediction_promotion_mode,
        )
    )
    return tracks, deltas


def build_validation_record(
    *,
    prediction: Any,
    report: Any,
    specialist: Any | None = None,
    settings: Settings | None = None,
) -> RealWorldValidationRecord:
    settings = settings or get_settings()
    trace = None
    if getattr(prediction, "audit_report", None) and prediction.audit_report.trace:
        trace = prediction.audit_report.trace

    md = dict(getattr(prediction, "metadata", None) or {})
    snapshots = build_snapshots(report, specialist)
    promotions, deltas = build_promotion_tracks(trace=trace, metadata=md, settings=settings)

    kickoff = getattr(prediction, "kickoff_utc", None)
    match_date = kickoff.strftime("%Y-%m-%d") if kickoff else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dq = 0.0
    if report and report.data_quality:
        dq = float(report.data_quality.score) * 100

    shadow_signals = {
        "promotion_modes": {
            "24a": settings.expected_lineup_promotion_mode,
            "24b": settings.tournament_context_promotion_mode,
            "24c_xg": settings.xg_promotion_mode,
            "24c_sm": settings.sportmonks_prediction_promotion_mode,
        },
        "watch_only": md.get("watch_only"),
        "sportmonks_no_bet_review": bool(getattr(trace, "sportmonks_no_bet_review_trace", False) if trace else False),
        "tactics_trace_notes": str(getattr(trace, "tactics_trace_notes", "") if trace else ""),
    }

    return RealWorldValidationRecord(
        fixture_id=int(prediction.fixture_id),
        match_date=match_date,
        prediction_timestamp=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        match_name=str(prediction.match_name),
        competition_key=str(getattr(prediction, "competition_key", None) or "world_cup_2026"),
        predicted_1x2=str(prediction.one_x_two.selection),
        predicted_over_under=str(prediction.over_under.selection),
        confidence=float(prediction.confidence_score),
        baseline_confidence=float(getattr(trace, "baseline_confidence", prediction.confidence_score) if trace else prediction.confidence_score),
        no_bet_flag=bool(prediction.no_bet_flag),
        data_quality_score=dq,
        confidence_bucket=_confidence_bucket(float(prediction.confidence_score)),
        snapshots=snapshots,
        promotions=promotions,
        promotion_deltas=deltas,
        shadow_signals=shadow_signals,
    )


def maybe_record_real_world_validation(
    *,
    prediction: Any,
    report: Any,
    specialist: Any | None = None,
    enabled: bool | None = None,
    store_path: str | None = None,
) -> None:
    """Forward-only capture — does not alter predictions or promotion modes."""
    settings = get_settings()
    if enabled is None:
        enabled = settings.real_world_validation_mode == "shadow"
    if not enabled:
        return
    try:
        record = build_validation_record(prediction=prediction, report=report, specialist=specialist, settings=settings)
        store = RealWorldValidationStore(store_path or settings.real_world_validation_path)
        store.append(record)
    except Exception:
        logger.exception("real-world validation capture failed fixture=%s", getattr(prediction, "fixture_id", "?"))
