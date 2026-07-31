"""Explainability helpers for portfolio decisions (research-only)."""

from __future__ import annotations

from typing import Any


def build_explanation(
    *,
    daily: dict[str, Any],
    decision: dict[str, Any],
    allocation: dict[str, Any],
    risk: dict[str, Any],
) -> dict[str, Any]:
    bullets = []
    bullets.append(f"Today's score: {daily.get('daily_portfolio_score')}")
    bullets.append(f"Grade: {daily.get('grade')}")
    bullets.append(f"Recommendation: {decision.get('action')}")
    for r in (decision.get("reasoning") or [])[:8]:
        bullets.append(str(r))
    bullets.append(
        f"Recommended fixture count: {decision.get('recommended_fixture_count')}"
    )
    bullets.append(f"Allocated capital: €{allocation.get('allocated_eur')}")
    bullets.append(f"Max loss: €{risk.get('maximum_loss_eur')}")
    return {
        "research_only": True,
        "summary_lines": bullets,
        "components": daily.get("components"),
        "selected_fixture_ids": decision.get("selected_fixture_ids"),
        "predictions_not_modified": True,
    }
