"""Phase A23 blueprint — Goal Timing Quality Gate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from worldcup_predictor.goal_timing.wc_reliability.range_probabilities import normalize_range_probabilities
from worldcup_predictor.goal_timing.wc_reliability.timing_consistency import validate_timing_consistency

DataQualityLevel = Literal["HIGH", "MEDIUM", "LOW"]
PredictionAction = Literal["BET", "LEAN", "PASS"]


@dataclass(frozen=True)
class QualityGateResult:
    data_quality: DataQualityLevel
    no_clear_edge: bool
    prediction_action: PredictionAction
    checks: dict[str, Any]
    reasons: list[str]


class GoalTimingQualityGate:
    """Cross-signal gate for FIFA / national-team goal timing (blueprint)."""

    HIGH_DQ = 0.75
    MEDIUM_DQ = 0.50

    def evaluate(self, payload: dict[str, Any]) -> QualityGateResult:
        dm = payload.get("detailed_markets") or {}
        fg = dm.get("first_goal") or {}
        gt = payload.get("goal_timing") or dm.get("goal_timing") or {}

        minute_range = fg.get("minute_range") or gt.get("first_goal_time_range")
        expected_minute = fg.get("expected_minute") or gt.get("estimated_first_goal_minute")
        range_probs = normalize_range_probabilities(
            gt.get("range_probabilities") or fg.get("range_probabilities")
        )

        timing = validate_timing_consistency(minute_range=minute_range, expected_minute=expected_minute)

        probs = payload.get("probabilities") or {}
        ou = probs.get("over_under_2_5") or dm.get("over_under_25") or {}
        btts = probs.get("btts") or dm.get("btts") or {}
        lambda_home = payload.get("lambda_home") or payload.get("shadow_lambda_home")
        lambda_away = payload.get("lambda_away") or payload.get("shadow_lambda_away")
        xg_block = payload.get("xg") or payload.get("xg_intelligence") or {}
        egie_status = (payload.get("egie") or {}).get("status") or gt.get("status")

        checks: dict[str, Any] = {
            "minute_range_consistency": timing.prediction_status == "VALID",
            "expected_minute_consistency": timing.prediction_status == "VALID",
            "range_probabilities_present": bool(range_probs),
            "range_probabilities_sum": round(sum(range_probs.values()), 3) if range_probs else 0.0,
            "xg_present": bool(xg_block),
            "lambda_present": lambda_home is not None and lambda_away is not None,
            "over_under_present": bool(ou),
            "first_goal_team_present": bool(fg.get("team") or gt.get("first_goal_team")),
            "egie_available": egie_status in (None, "available", "ok"),
            "timing_deviation_minutes": timing.deviation_minutes,
            "confidence_penalty": timing.confidence_penalty,
        }

        dq_score = float(payload.get("data_quality_score") or gt.get("data_quality_score") or 0.0)
        signal_count = sum(
            1
            for k in (
                "range_probabilities_present",
                "lambda_present",
                "over_under_present",
                "first_goal_team_present",
            )
            if checks[k]
        )

        if timing.prediction_status == "INVALID" or dq_score < self.MEDIUM_DQ:
            data_quality: DataQualityLevel = "LOW"
        elif dq_score >= self.HIGH_DQ and signal_count >= 3 and checks["range_probabilities_present"]:
            data_quality = "HIGH"
        else:
            data_quality = "MEDIUM"

        reasons: list[str] = []
        if timing.prediction_status == "INVALID":
            reasons.append("timing_conflict")
        if not range_probs:
            reasons.append("missing_range_probabilities")
        if egie_status in ("missing", "unavailable", "no_pick"):
            reasons.append("missing_egie")
        if not checks["lambda_present"]:
            reasons.append("missing_lambda")
        if timing.confidence_penalty >= 0.30:
            reasons.append("high_timing_deviation")

        # NO_CLEAR_EDGE: close bucket race or invalid timing
        if range_probs:
            vals = sorted(range_probs.values(), reverse=True)
            gap = (vals[0] - vals[1]) if len(vals) > 1 else vals[0]
            no_clear_edge = gap < 0.08 or timing.prediction_status == "INVALID"
            if gap < 0.08:
                reasons.append("bucket_probabilities_too_close")
        else:
            no_clear_edge = True

        from worldcup_predictor.goal_timing.wc_reliability.abstention import decide_prediction_action

        action = decide_prediction_action(
            data_quality=data_quality,
            no_clear_edge=no_clear_edge,
            timing_invalid=timing.prediction_status == "INVALID",
            reasons=reasons,
        )

        return QualityGateResult(
            data_quality=data_quality,
            no_clear_edge=no_clear_edge,
            prediction_action=action,
            checks=checks,
            reasons=reasons,
        )
