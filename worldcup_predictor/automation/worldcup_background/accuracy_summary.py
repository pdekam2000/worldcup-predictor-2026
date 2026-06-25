"""Aggregate World Cup prediction accuracy stats — Phase 33 / 33B."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository


def _rate(correct: int, total: int) -> float | None:
    if total <= 0:
        return None
    return round(correct / total, 4)


def rebuild_accuracy_summary(
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
) -> dict[str, Any]:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    rows = repo.list_worldcup_prediction_evaluations(competition_key=competition_key)

    total = len(rows)
    pending = sum(1 for r in rows if r.get("overall_status") == "pending")
    correct = sum(1 for r in rows if r.get("overall_status") == "correct")
    wrong = sum(1 for r in rows if r.get("overall_status") == "wrong")
    unknown = sum(1 for r in rows if r.get("overall_status") in {"unknown", "void"})
    evaluated = correct + wrong

    def _pick_stats(key: str) -> dict[str, Any]:
        sub = [r for r in rows if r.get(f"{key}_status") in {"correct", "wrong"}]
        c = sum(1 for r in sub if r.get(f"{key}_status") == "correct")
        return {"total": len(sub), "correct": c, "winrate": _rate(c, len(sub))}

    def _tier_winrate(*, official: bool) -> dict[str, Any]:
        sub: list[dict[str, Any]] = []
        for row in rows:
            detail_raw = row.get("detail_json")
            detail: dict[str, Any] = {}
            if detail_raw:
                try:
                    detail = json.loads(detail_raw) if isinstance(detail_raw, str) else detail_raw
                except (json.JSONDecodeError, TypeError):
                    detail = {}
            is_official = bool(detail.get("official_recommended")) and not bool(row.get("no_bet"))
            if official and not is_official:
                continue
            if not official and not (bool(row.get("no_bet")) or detail.get("pick_tier") == "caution"):
                continue
            status = detail.get("status")
            if status in {"correct", "wrong"}:
                sub.append(detail)
        correct = sum(1 for d in sub if d.get("status") == "correct")
        return {"total": len(sub), "correct": correct, "winrate": _rate(correct, len(sub))}

    def _caution_pick_stats() -> dict[str, Any]:
        sub: list[str] = []
        for row in rows:
            detail_raw = row.get("detail_json")
            if not detail_raw:
                continue
            try:
                detail = json.loads(detail_raw) if isinstance(detail_raw, str) else detail_raw
            except (json.JSONDecodeError, TypeError):
                continue
            markets = detail.get("markets") or {}
            status = markets.get("caution_pick") or markets.get("best_available_pick")
            if status in {"correct", "wrong"}:
                sub.append(status)
        correct = sum(1 for s in sub if s == "correct")
        return {"total": len(sub), "correct": correct, "winrate": _rate(correct, len(sub))}

    stored_preds = repo.count_worldcup_stored_predictions(competition_key=competition_key)
    no_bet = sum(1 for r in rows if r.get("no_bet"))

    summary = {
        "competition_key": competition_key,
        "updated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "total_stored_predictions": stored_preds,
        "total_evaluations": total,
        "evaluated_predictions": evaluated,
        "pending": pending,
        "correct": correct,
        "wrong": wrong,
        "unknown_or_void": unknown,
        "winrate": _rate(correct, evaluated),
        "no_bet_count": no_bet,
        "no_bet_rate": _rate(no_bet, total) if total else None,
        "official_picks": _tier_winrate(official=True),
        "caution_picks": _tier_winrate(official=False),
        "caution_pick_market": _caution_pick_stats(),
        "safe_pick": _pick_stats("safe_pick"),
        "value_pick": _pick_stats("value_pick"),
        "aggressive_pick": _pick_stats("aggressive_pick"),
        "market_1x2": _pick_stats("market_1x2"),
        "market_over_under_2_5": _pick_stats("market_ou"),
        "market_btts": _pick_stats("market_btts"),
        "market_double_chance": _pick_stats("market_dc"),
        "market_ht_result": _pick_stats("market_ht"),
        "market_correct_score": _pick_stats("market_cs"),
        "market_first_goal_team": _pick_stats("market_fg_team"),
        "market_goalscorer": _pick_stats("market_goalscorer"),
        "market_goal_minute": _pick_stats("market_goal_minute"),
    }
    repo.upsert_worldcup_accuracy_summary(competition_key=competition_key, summary=summary)

    try:
        from worldcup_predictor.monitoring.production_accuracy_monitor import capture_performance_snapshot

        capture_performance_snapshot(
            settings=settings,
            competition_key=competition_key,
            summary=summary,
        )
    except Exception:
        pass

    return summary


def get_accuracy_summary(
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    return repo.get_worldcup_accuracy_summary(competition_key=competition_key)
