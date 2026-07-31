"""Daily portfolio quality score (research-only)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.bet_portfolio_manager.constants import (
    ACTION_THRESHOLDS,
    GRADE_THRESHOLDS,
    SCORE_WEIGHTS,
)
from worldcup_predictor.research.bet_portfolio_manager.correlation import analyze_diversification


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _grade(score: float) -> str:
    for thr, g in GRADE_THRESHOLDS:
        if score >= thr:
            return g
    return "F"


def _action(score: float) -> str:
    for thr, a in ACTION_THRESHOLDS:
        if score >= thr:
            return a
    return "SKIP"


def compute_daily_portfolio_score(
    fixtures: list[dict[str, Any]],
    *,
    league_reliability: dict[str, float] | None = None,
    historical_forward_performance: float | None = None,
    calibration_quality: float | None = None,
) -> dict[str, Any]:
    """
    Single day quality score in [0, 100].
    Never changes football predictions — evaluates investability only.
    """
    n = len(fixtures)
    reasoning: list[str] = []
    if n == 0:
        return {
            "research_only": True,
            "daily_portfolio_score": 0.0,
            "grade": "F",
            "recommendation": "SKIP",
            "reasoning": ["No fixtures available."],
            "components": {},
            "n_fixtures": 0,
        }

    conf = sum(float(f.get("confidence") or 0) for f in fixtures) / n
    ent = sum(float(f.get("entropy") or 0) for f in fixtures) / n
    low_ent = _clamp01(1.0 - (ent - 1.5) / 2.5)
    cov = sum(float(f.get("coverage_mass") or 0) for f in fixtures) / n
    res = sum(float(f.get("residual_risk") or 0) for f in fixtures) / n
    low_res = _clamp01(1.0 - res)
    ins = sum(float(f.get("insurance_contribution") or 0) for f in fixtures) / n
    ins_n = _clamp01(ins / 0.12)
    bal = sum(float(f.get("odds_balance") or 0) for f in fixtures) / n
    tags = {t for f in fixtures for t in (f.get("market_tags") or [])}
    mdiv = _clamp01(len(tags) / max(3.0, float(n)))
    # Prefer 2–4 fixtures for coupon quality
    if n == 0:
        fcount_q = 0.0
    elif 2 <= n <= 4:
        fcount_q = 1.0
    elif n == 1 or n == 5:
        fcount_q = 0.7
    else:
        fcount_q = 0.45

    lr_map = league_reliability or {}
    league_rel = sum(float(lr_map.get(str(f.get("league") or ""), 0.55)) for f in fixtures) / n

    div = analyze_diversification(fixtures)
    low_corr = _clamp01(div["diversification_score"] / 100.0)

    components = {
        "mean_confidence": round(100 * _clamp01(conf), 4),
        "low_entropy": round(100 * low_ent, 4),
        "coverage_mass": round(100 * _clamp01(cov), 4),
        "low_residual_risk": round(100 * low_res, 4),
        "insurance_contribution": round(100 * ins_n, 4),
        "odds_balance": round(100 * _clamp01(bal), 4),
        "market_diversity": round(100 * mdiv, 4),
        "fixture_count_quality": round(100 * fcount_q, 4),
        "league_reliability": round(100 * _clamp01(league_rel), 4),
        "low_correlation": round(100 * low_corr, 4),
    }
    if historical_forward_performance is not None:
        components["historical_forward_performance"] = round(100 * _clamp01(historical_forward_performance), 4)
    if calibration_quality is not None:
        components["calibration_quality"] = round(100 * _clamp01(calibration_quality), 4)

    score = 0.0
    wsum = 0.0
    for k, w in SCORE_WEIGHTS.items():
        score += w * (components.get(k, 50.0) / 100.0)
        wsum += w
    # Optional extras
    for k, w in (("historical_forward_performance", 0.04), ("calibration_quality", 0.04)):
        if k in components:
            score += w * (components[k] / 100.0)
            wsum += w
    daily = round(100.0 * (score / wsum if wsum else 0.0), 4)

    # Penalties
    if div.get("over_concentrated"):
        daily = round(max(0.0, daily - 8.0), 4)
        reasoning.append("Penalty: high fixture correlation / league concentration.")
    if n >= 6:
        daily = round(max(0.0, daily - 5.0), 4)
        reasoning.append("Penalty: large slate increases capital concentration risk.")
    if conf >= 0.55:
        reasoning.append("High average prediction confidence.")
    if low_ent >= 0.55:
        reasoning.append("Entropy is controlled (lower uncertainty).")
    if ins_n >= 0.4:
        reasoning.append("Insurance layer contributes meaningful uncovered mass.")
    if league_rel >= 0.6:
        reasoning.append("League historical reliability is supportive.")
    if low_corr >= 0.5:
        reasoning.append("Pairwise correlation / diversification acceptable.")
    if cov >= 0.7:
        reasoning.append("Coverage mass after Main(+Insurance) is strong.")

    grade = _grade(daily)
    rec = _action(daily)
    return {
        "research_only": True,
        "owner_only": True,
        "daily_portfolio_score": daily,
        "grade": grade,
        "recommendation": rec,
        "reasoning": reasoning or ["Neutral day quality."],
        "components": components,
        "n_fixtures": n,
        "diversification": {
            "diversification_score": div["diversification_score"],
            "mean_pairwise_correlation": div["mean_pairwise_correlation"],
            "over_concentrated": div["over_concentrated"],
        },
        "predictions_unchanged": True,
    }
