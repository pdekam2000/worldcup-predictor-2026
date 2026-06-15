"""Model evaluation grades — accuracy only, not profit."""

from __future__ import annotations

from typing import Any


def compute_model_grade(primary_accuracy: float | None) -> str:
    """Letter grade from overall 1X2 accuracy (model evaluation only)."""
    if primary_accuracy is None:
        return "—"
    pct = primary_accuracy * 100
    if pct >= 70:
        return "A"
    if pct >= 60:
        return "B"
    if pct >= 50:
        return "C"
    return "D"


def market_league_table(metrics: Any) -> list[dict[str, Any]]:
    """Rank markets by accuracy for Performance Center league table."""
    rows: list[dict[str, Any]] = []
    if metrics.total_evaluated:
        if metrics.one_x_two_accuracy is not None:
            rows.append(
                {
                    "market": "1X2",
                    "accuracy": metrics.one_x_two_accuracy,
                    "evaluated": metrics.total_evaluated,
                }
            )
        if metrics.over_under_2_5_accuracy is not None:
            rows.append(
                {
                    "market": "Over/Under 2.5",
                    "accuracy": metrics.over_under_2_5_accuracy,
                    "evaluated": metrics.total_evaluated,
                }
            )
        if metrics.halftime_bucket_accuracy is not None:
            rows.append(
                {
                    "market": "Halftime bucket",
                    "accuracy": metrics.halftime_bucket_accuracy,
                    "evaluated": metrics.halftime_evaluated_count,
                }
            )
        if getattr(metrics, "scoreline_exact_accuracy", None) is not None:
            rows.append(
                {
                    "market": "Exact scoreline",
                    "accuracy": metrics.scoreline_exact_accuracy,
                    "evaluated": getattr(metrics, "scoreline_evaluated_count", 0),
                }
            )
        if getattr(metrics, "first_goal_accuracy", None) is not None:
            rows.append(
                {
                    "market": "First goal team",
                    "accuracy": metrics.first_goal_accuracy,
                    "evaluated": getattr(metrics, "first_goal_evaluated_count", 0),
                }
            )
    rows.sort(key=lambda row: row.get("accuracy") or 0, reverse=True)
    return rows


def best_and_worst_market(rows: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    eligible = [row for row in rows if row.get("evaluated", 0) >= 1 and row.get("accuracy") is not None]
    if not eligible:
        return None, None
    best = max(eligible, key=lambda row: row["accuracy"])
    worst = min(eligible, key=lambda row: row["accuracy"])
    return str(best["market"]), str(worst["market"])
