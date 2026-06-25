"""Update research highlights from autonomous performance stats — Phase 61."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.autonomous.store import AutonomousStore
from worldcup_predictor.config.settings import Settings, get_settings


def build_autonomous_research_block(*, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    store = AutonomousStore(settings)
    cert = store.latest_certification_report()
    prod = store.aggregate_performance(engine="production", rolling_days=30)
    elite = store.aggregate_performance(engine="elite_shadow", rolling_days=30)

    return {
        "autonomous_platform": {
            "rolling_30d_production_winrate": prod.get("winrate"),
            "rolling_30d_production_evaluated": prod.get("evaluated", 0),
            "rolling_30d_elite_winrate": elite.get("winrate"),
            "rolling_30d_elite_evaluated": elite.get("evaluated", 0),
            "latest_certification": (cert or {}).get("report", {}).get("overall", {}),
            "disclaimer": "Research statistics from autonomous shadow tracking. Not betting advice.",
        }
    }


def merge_into_highlights_payload(payload: dict[str, Any], *, settings: Settings | None = None) -> dict[str, Any]:
    block = build_autonomous_research_block(settings=settings)
    merged = dict(payload)
    merged["autonomous_stats"] = block["autonomous_platform"]
    return merged
