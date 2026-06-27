"""Public trust statistics from real evaluations — Phase A20."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.social_trust.constants import DISCLAIMER


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def build_public_accuracy_trust(
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
    days: int = 30,
) -> dict[str, Any]:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    cutoff = (_utc_now() - timedelta(days=days)).isoformat()

    rows = repo.list_worldcup_prediction_evaluations(competition_key=competition_key)

    recent = [
        r for r in rows
        if not int(r.get("is_quarantined") or 0)
        and str(r.get("evaluated_at") or r.get("created_at") or "") >= cutoff
    ]

    market_stats: dict[str, dict[str, int]] = {}
    correct_1x2 = 0
    total_1x2 = 0

    for row in recent:
        status = str(row.get("market_1x2_status") or "pending").lower()
        if status in ("correct", "wrong"):
            total_1x2 += 1
            if status == "correct":
                correct_1x2 += 1

        for market, col in (
            ("1x2", "market_1x2_status"),
            ("over_under_2_5", "market_ou_status"),
            ("btts", "market_btts_status"),
            ("double_chance", "market_dc_status"),
        ):
            st = str(row.get(col) or "pending").lower()
            if st not in ("correct", "wrong"):
                continue
            market_stats.setdefault(market, {"correct": 0, "total": 0})
            market_stats[market]["total"] += 1
            if st == "correct":
                market_stats[market]["correct"] += 1

    best_market = None
    best_rate = -1.0
    for mk, rec in market_stats.items():
        if rec["total"] < 5:
            continue
        rate = rec["correct"] / rec["total"]
        if rate > best_rate:
            best_rate = rate
            best_market = mk

    accuracy_30d = round((correct_1x2 / total_1x2) * 100, 1) if total_1x2 >= 5 else None
    evaluated_count = len(recent)

    return {
        "period_days": days,
        "evaluated_predictions": evaluated_count,
        "accuracy_30d_pct": accuracy_30d,
        "accuracy_30d_sample": total_1x2,
        "best_market": best_market,
        "best_market_accuracy_pct": round(best_rate * 100, 1) if best_market and best_rate >= 0 else None,
        "markets": {
            mk: {
                "evaluated": rec["total"],
                "accuracy_pct": round((rec["correct"] / rec["total"]) * 100, 1) if rec["total"] else None,
            }
            for mk, rec in market_stats.items()
            if rec["total"] >= 3
        },
        "data_available": evaluated_count > 0 and total_1x2 >= 5,
        "disclaimer": DISCLAIMER,
    }
