"""Part D — persistent bias and edge detection."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.mbi.models import MIN_SAMPLE_BIAS, MIN_SAMPLE_STRONG, MIN_SAMPLE_WEAK


def detect_edges(bucket_table: list[dict[str, Any]]) -> dict[str, Any]:
    """Identify persistent over/underpricing by bucket."""
    weak: list[dict[str, Any]] = []
    bias: list[dict[str, Any]] = []
    strong: list[dict[str, Any]] = []

    for row in bucket_table:
        n = int(row["count"])
        gap = float(row["calibration_gap"])
        abs_gap = abs(gap)
        enriched = dict(row)
        if gap > 0:
            enriched["bias_type"] = "underpriced_by_book"
            enriched["interpretation"] = "Actual hit rate exceeds implied probability"
        elif gap < 0:
            enriched["bias_type"] = "overpriced_by_book"
            enriched["interpretation"] = "Implied probability exceeds actual hit rate"
        else:
            enriched["bias_type"] = "calibrated"
            enriched["interpretation"] = "Hit rate matches implied probability"

        if n >= MIN_SAMPLE_WEAK and abs_gap >= 0.03:
            weak.append(enriched)
        if n >= MIN_SAMPLE_BIAS and abs_gap >= 0.05:
            bias.append(enriched)
        if n >= MIN_SAMPLE_STRONG and abs_gap >= 0.07:
            strong.append(enriched)

    weak.sort(key=lambda r: abs(float(r["calibration_gap"])), reverse=True)
    bias.sort(key=lambda r: abs(float(r["calibration_gap"])), reverse=True)
    strong.sort(key=lambda r: abs(float(r["calibration_gap"])), reverse=True)

    persistent_over = [r for r in bias if r["bias_type"] == "overpriced_by_book"]
    persistent_under = [r for r in bias if r["bias_type"] == "underpriced_by_book"]

    return {
        "min_sample_thresholds": {
            "weak_signal": MIN_SAMPLE_WEAK,
            "persistent_bias": MIN_SAMPLE_BIAS,
            "strong_bias": MIN_SAMPLE_STRONG,
        },
        "weak_edges": weak[:20],
        "persistent_biases": bias[:20],
        "strong_biases": strong[:15],
        "persistent_overpricing": persistent_over[:10],
        "persistent_underpricing": persistent_under[:10],
        "bias_count": len(bias),
        "strong_bias_count": len(strong),
    }


def market_edge_ranking(bucket_table: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank markets by exploitable calibration signal."""
    by_market: dict[str, dict[str, Any]] = {}
    for row in bucket_table:
        mk = row["market_key"]
        entry = by_market.setdefault(mk, {"market_key": mk, "signal_score": 0.0, "biased_buckets": 0, "n": 0})
        n = int(row["count"])
        gap = abs(float(row["calibration_gap"]))
        entry["n"] += n
        if n >= MIN_SAMPLE_BIAS and gap >= 0.05:
            entry["biased_buckets"] += 1
            entry["signal_score"] += gap * n

    ranked = sorted(by_market.values(), key=lambda r: r["signal_score"], reverse=True)
    for r in ranked:
        r["signal_score"] = round(r["signal_score"], 2)
    return ranked
