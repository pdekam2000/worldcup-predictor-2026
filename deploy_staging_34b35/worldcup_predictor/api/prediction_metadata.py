"""Phase 34B — engine version stamps and adaptive confidence trace for API payloads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.prediction.engine_versions import (
    ADAPTIVE_CONFIDENCE_VERSION,
    NATIONAL_TEAM_INTELLIGENCE_VERSION,
    PREDICTION_ENGINE_VERSION,
)


def build_adaptive_confidence_trace(prediction: MatchPrediction) -> dict[str, Any] | None:
    adj = getattr(prediction, "adaptive_confidence", None)
    if adj is None:
        md = prediction.metadata or {}
        base = md.get("base_confidence")
        bonus = md.get("learning_confidence_bonus")
        if base is None:
            return None
        try:
            before = float(base)
            bonus_f = float(str(bonus).replace("+", "")) if bonus else 0.0
            after = float(prediction.confidence_score or 0)
        except (TypeError, ValueError):
            return None
        return {
            "confidence_before_adaptive": round(before, 1),
            "adaptive_adjustment": round(bonus_f, 1),
            "confidence_after_adaptive": round(after, 1),
            "adaptive_reasons": "Recovered from metadata",
        }

    reasons: list[str] = []
    if adj.reason:
        reasons.append(adj.reason)
    if adj.pattern_bonus:
        reasons.append(f"pattern {adj.pattern_bonus:+.1f}")
    if adj.competition_bonus:
        reasons.append(f"competition {adj.competition_bonus:+.1f}")
    if adj.similar_situation_bonus:
        reasons.append(f"similar matches {adj.similar_situation_bonus:+.1f}")
    if adj.bucket_bonus:
        reasons.append(f"calibration bucket {adj.bucket_bonus:+.1f}")

    return {
        "confidence_before_adaptive": round(float(adj.base_confidence), 1),
        "adaptive_adjustment": round(float(adj.total_bonus), 1),
        "confidence_after_adaptive": round(float(adj.final_confidence), 1),
        "adaptive_reasons": "; ".join(reasons) if reasons else "No learning adjustment",
        "pattern_bonus": round(float(adj.pattern_bonus), 1),
        "competition_bonus": round(float(adj.competition_bonus), 1),
        "similar_situation_bonus": round(float(adj.similar_situation_bonus), 1),
        "bucket_bonus": round(float(adj.bucket_bonus), 1),
        "similar_sample_size": int(adj.similar_sample_size or 0),
    }


def stamp_prediction_engine_metadata(
    payload: dict[str, Any],
    *,
    prediction: MatchPrediction | None = None,
    generated_by: str = "live",
) -> dict[str, Any]:
    """Attach Phase 34B version stamps and adaptive trace."""
    out = dict(payload)
    out["prediction_engine_version"] = PREDICTION_ENGINE_VERSION
    out["adaptive_confidence_version"] = ADAPTIVE_CONFIDENCE_VERSION
    out["generated_by"] = generated_by
    out["generated_at"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"

    nat = out.get("national_team_intelligence") or {}
    if isinstance(nat, dict) and not nat.get("version"):
        nat = dict(nat)
        nat["version"] = NATIONAL_TEAM_INTELLIGENCE_VERSION
        out["national_team_intelligence"] = nat

    if prediction is not None:
        adaptive = build_adaptive_confidence_trace(prediction)
        if adaptive:
            out["adaptive_confidence_trace"] = adaptive
            audit = dict(out.get("audit_trace") or {})
            conf = dict(audit.get("confidence") or {})
            conf["adaptive"] = adaptive
            if conf.get("final") is None and prediction.audit_report and prediction.audit_report.trace:
                conf["baseline"] = prediction.audit_report.trace.baseline_confidence
                conf["final"] = prediction.audit_report.trace.final_confidence
            audit["confidence"] = conf
            out["audit_trace"] = audit

    return out


def stamp_minimal_quality_metadata(
    payload: dict[str, Any],
    *,
    generated_by: str = "test",
) -> dict[str, Any]:
    """Stamp test/cache payloads without a full MatchPrediction (validation scripts)."""
    out = dict(payload)
    out["prediction_engine_version"] = PREDICTION_ENGINE_VERSION
    out["adaptive_confidence_version"] = ADAPTIVE_CONFIDENCE_VERSION
    out["generated_by"] = generated_by
    out["generated_at"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"

    nat = out.get("national_team_intelligence") or {}
    if isinstance(nat, dict):
        nat = dict(nat)
        nat.setdefault("version", NATIONAL_TEAM_INTELLIGENCE_VERSION)
        out["national_team_intelligence"] = nat

    conf = float(out.get("confidence") or 60.0)
    adaptive = {
        "confidence_before_adaptive": round(conf, 1),
        "adaptive_adjustment": 0.0,
        "confidence_after_adaptive": round(conf, 1),
        "adaptive_reasons": "validation fixture stamp",
    }
    out["adaptive_confidence_trace"] = adaptive
    audit = dict(out.get("audit_trace") or {})
    conf_audit = dict(audit.get("confidence") or {})
    conf_audit.setdefault("baseline", conf)
    conf_audit.setdefault("final", conf)
    conf_audit["adaptive"] = adaptive
    conf_audit["no_bet_reasons"] = [r for r in conf_audit.get("no_bet_reasons") or [] if "placeholder" not in str(r)]
    audit["confidence"] = conf_audit
    out["audit_trace"] = audit
    if "cached_at" not in out:
        import time

        out["cached_at"] = time.time()
    return out
