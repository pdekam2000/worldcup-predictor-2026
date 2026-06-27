"""Daily betting day quality assessment — Phase A17."""

from __future__ import annotations

from typing import Any


def assess_day_quality(
    legs: list[dict[str, Any]],
    combos: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    scores = [float(l.get("bet_quality_score") or 0) for l in legs]
    elite = sum(1 for s in scores if s >= 90)
    strong = sum(1 for s in scores if s >= 75)
    avoid = sum(1 for s in scores if s < 45)
    unavailable = sum(1 for l in legs if l.get("internal_status") == "unavailable")
    avg = round(sum(scores) / len(scores), 1) if scores else 0.0

    combo_ready = sum(
        1 for c in combos.values() if int(c.get("leg_count") or 0) >= int((c.get("min_legs") or 2))
    )
    # infer min legs from empty check
    safe_ok = (combos.get("safe") or {}).get("leg_count", 0) >= 2
    balanced_ok = (combos.get("balanced") or {}).get("leg_count", 0) >= 3

    label = "Poor"
    recommendation = "No betting recommended today except very small test stakes."
    if elite >= 3 and avg >= 72 and safe_ok:
        label = "Excellent"
        recommendation = "Strong day — elite singles and safe combos available."
    elif strong >= 5 and avg >= 62 and (safe_ok or balanced_ok):
        label = "Good"
        recommendation = "Solid opportunities — favor quality singles and balanced combos."
    elif avg >= 48 and strong >= 2:
        label = "Risky"
        recommendation = "Proceed with caution — reduce stakes and avoid high-odds accumulators."
    elif avoid > len(legs) * 0.6 or avg < 40:
        label = "Poor"
        recommendation = "No betting recommended today except very small test stakes."

    if unavailable > len(legs) * 0.5 and len(legs) > 0:
        label = "Poor" if label != "Excellent" else label
        recommendation += " Data completeness is limited."

    return {
        "label": label,
        "overall_day_quality": label,
        "average_quality": avg,
        "elite_count": elite,
        "strong_count": strong,
        "avoid_count": avoid,
        "total_legs": len(legs),
        "combo_readiness": {
            "safe": safe_ok,
            "balanced": balanced_ok,
            "value": (combos.get("value") or {}).get("leg_count", 0) >= 3,
            "high_odds": (combos.get("high_odds") or {}).get("leg_count", 0) >= 4,
        },
        "recommendation": recommendation,
    }
