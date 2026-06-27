"""Read-only performance insights for betting plan — Phase A17."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.api.performance_center import build_performance_summary
from worldcup_predictor.config.settings import Settings, get_settings


def build_performance_insights(
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
) -> dict[str, Any]:
    settings = settings or get_settings()
    summary = build_performance_summary(settings=settings, competition_key=competition_key)
    evaluated = int(summary.get("total_evaluated") or 0)
    if evaluated <= 0:
        return {
            "available": False,
            "message": "Performance history will appear after evaluated bets.",
            "by_market": [],
            "by_quality_tier": [],
            "combo_performance": [],
        }

    markets = []
    for m in summary.get("markets") or []:
        if int(m.get("sample_size") or 0) <= 0:
            continue
        markets.append(
            {
                "market": m.get("market_name"),
                "winrate": m.get("winrate") or m.get("accuracy"),
                "sample_size": m.get("sample_size"),
                "reliability": m.get("reliability_level"),
            }
        )

    tier_notes = []
    overall = summary.get("overall_accuracy")
    if overall is not None:
        tier_notes.append(
            {
                "tier": "overall",
                "winrate": overall,
                "sample_size": evaluated,
                "note": "All evaluated predictions",
            }
        )

    return {
        "available": True,
        "message": None,
        "overall_accuracy": overall,
        "total_evaluated": evaluated,
        "by_market": markets,
        "by_quality_tier": tier_notes,
        "combo_performance": [],
        "note": "Combo historical performance requires evaluated combo tracking — not yet available.",
    }
