"""Prematch-only regime selector — does not rewrite canonical probabilities."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.high_score_tail_shadow.constants import (
    REGIME_HIGH,
    REGIME_LOW,
    REGIME_UNCLEAR,
)


def _frac(x: Any) -> float | None:
    try:
        if x is None or x == "":
            return None
        v = float(x)
        return v / 100.0 if v > 1.5 else v
    except (TypeError, ValueError):
        return None


def select_regime(
    *,
    lambda_home: float | None,
    lambda_away: float | None,
    ou_prediction: str | None = None,
    btts_prediction: str | None = None,
    wde_home: float | None = None,
    wde_away: float | None = None,
    wde_confidence: float | None = None,
    top5_mass: float | None = None,
) -> dict[str, Any]:
    """Return regime recommendation with reasons (shadow-only)."""
    reasons: list[str] = []
    score = 0.0  # positive → high, negative → low

    if lambda_home is not None and lambda_away is not None:
        total = float(lambda_home) + float(lambda_away)
        if total >= 3.0:
            score += 2.0
            reasons.append(f"high_expected_total={total:.2f}")
        elif total <= 2.2:
            score -= 2.0
            reasons.append(f"low_expected_total={total:.2f}")
        else:
            reasons.append(f"mid_expected_total={total:.2f}")

    ou = str(ou_prediction or "").lower()
    if "over" in ou:
        score += 1.5
        reasons.append("ou_over")
    elif "under" in ou:
        score -= 1.5
        reasons.append("ou_under")

    btts = str(btts_prediction or "").lower()
    if btts in {"yes", "btts_yes"}:
        score += 0.5
        reasons.append("btts_yes")
    elif btts in {"no", "btts_no"}:
        score -= 0.5
        reasons.append("btts_no")

    hp, ap = _frac(wde_home), _frac(wde_away)
    if hp is not None and ap is not None:
        gap = abs(hp - ap)
        if gap >= 0.55:
            score += 0.75
            reasons.append(f"strong_wde_gap={gap:.2f}")

    mass = _frac(top5_mass)
    if mass is not None and mass >= 0.60:
        score -= 0.5
        reasons.append("concentrated_top5_mass")
    elif mass is not None and mass <= 0.45:
        score += 0.5
        reasons.append("diffuse_top5_mass")

    if score >= 1.5:
        regime = REGIME_HIGH
    elif score <= -1.5:
        regime = REGIME_LOW
    else:
        regime = REGIME_UNCLEAR

    confidence = min(0.95, 0.45 + abs(score) * 0.12)
    return {
        "regime": regime,
        "selector_score": round(score, 3),
        "selector_confidence": round(confidence, 3),
        "reasons": reasons,
        "shadow_only": True,
        "rewrites_canonical": False,
    }
