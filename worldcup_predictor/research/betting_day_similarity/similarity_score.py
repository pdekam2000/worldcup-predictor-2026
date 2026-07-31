"""Day similarity quality score 0–100 — research-only, not a profit probability."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.betting_day_similarity.constants import GRADE_THRESHOLDS


def day_similarity_quality_score(
    *,
    nn_similarity_strength: float,
    analog_sample_size: int,
    analog_roi_mean: float | None,
    analog_roi_std: float | None,
    analog_drawdown_mean: float | None,
    analog_coupon_survival: float | None,
    analog_failure_rate: float | None,
    regime_confidence: float,
    feature_completeness: float,
    ood_level: str,
    min_analog_count: int = 5,
) -> dict[str, Any]:
    score = 50.0
    evidence = []
    # NN strength (0..1-ish)
    score += 20.0 * max(0.0, min(1.0, nn_similarity_strength))
    evidence.append(f"nn_strength={nn_similarity_strength:.3f}")

    # sample size
    if analog_sample_size >= min_analog_count:
        score += 10.0
        evidence.append(f"adequate_sample={analog_sample_size}")
    else:
        score -= 15.0
        evidence.append(f"low_sample={analog_sample_size}")

    # consistency (low std better)
    if analog_roi_std is not None:
        score += max(-10.0, 8.0 - 20.0 * float(analog_roi_std))
        evidence.append(f"roi_std={analog_roi_std:.3f}")

    # historical analog ROI (evaluation display contribution — not live decision input at build time;
    # used only when analogs come from training library)
    if analog_roi_mean is not None:
        score += max(-15.0, min(15.0, 25.0 * float(analog_roi_mean)))
        evidence.append(f"analog_roi={analog_roi_mean:.3f}")

    if analog_drawdown_mean is not None:
        score -= min(10.0, float(analog_drawdown_mean) * 2.0)
        evidence.append(f"analog_dd={analog_drawdown_mean:.3f}")

    if analog_coupon_survival is not None:
        score += 10.0 * float(analog_coupon_survival)
        evidence.append(f"survival={analog_coupon_survival:.3f}")

    if analog_failure_rate is not None:
        score -= 12.0 * float(analog_failure_rate)
        evidence.append(f"fail_rate={analog_failure_rate:.3f}")

    score += 8.0 * float(regime_confidence)
    score += 8.0 * float(feature_completeness)

    if ood_level == "mildly_out_of_distribution":
        score -= 12.0
        evidence.append("ood_mild_penalty")
    elif ood_level == "strongly_out_of_distribution":
        score -= 30.0
        evidence.append("ood_strong_penalty")

    score = float(max(0.0, min(100.0, score)))
    grade = "F"
    for g in ("S", "A", "B", "C", "D", "F"):
        if score >= GRADE_THRESHOLDS[g]:
            grade = g
            break

    recommendation = _recommendation(
        score=score,
        analog_sample_size=analog_sample_size,
        min_analog_count=min_analog_count,
        analog_roi_mean=analog_roi_mean,
        ood_level=ood_level,
    )
    uncertainty = "high" if analog_sample_size < min_analog_count or ood_level != "in_distribution" else "medium"
    if analog_sample_size >= min_analog_count * 2 and ood_level == "in_distribution":
        uncertainty = "low"

    return {
        "day_similarity_quality_score": round(score, 4),
        "grade": grade,
        "recommendation": recommendation,
        "evidence": evidence,
        "uncertainty": uncertainty,
        "sample_size": analog_sample_size,
        "ood_status": ood_level,
        "not_a_profit_probability": True,
    }


def _recommendation(
    *,
    score: float,
    analog_sample_size: int,
    min_analog_count: int,
    analog_roi_mean: float | None,
    ood_level: str,
) -> str:
    if ood_level == "strongly_out_of_distribution":
        return "OUT_OF_DISTRIBUTION"
    if analog_sample_size < min_analog_count:
        return "UNCERTAIN_LOW_SAMPLE"
    if analog_roi_mean is not None and analog_roi_mean <= -0.05:
        return "HOSTILE_SIMILARITY"
    if analog_roi_mean is not None and analog_roi_mean >= 0.15 and score >= 70 and ood_level == "in_distribution":
        return "FAVORABLE_SIMILARITY"
    if analog_roi_mean is not None and analog_roi_mean >= 0.05 and score >= 60:
        return "MODERATELY_FAVORABLE"
    return "NEUTRAL"
