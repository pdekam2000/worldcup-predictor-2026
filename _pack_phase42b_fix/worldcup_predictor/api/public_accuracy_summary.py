"""Public platform accuracy summary — Phase 42B (SaaS-safe, no admin internals)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.automation.worldcup_background.accuracy_summary import get_accuracy_summary
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository

_MARKET_SUMMARY_KEYS: tuple[tuple[str, str], ...] = (
    ("1X2", "market_1x2"),
    ("Over/Under 2.5", "market_over_under_2_5"),
    ("BTTS", "market_btts"),
    ("Double Chance", "market_double_chance"),
)

_EVAL_MARKET_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("1X2", "market_1x2_status", "prediction"),
    ("Over/Under 2.5", "market_ou_status", "over_under_2_5"),
    ("BTTS", "market_btts_status", "btts"),
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _parse_payload(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row or not row.get("payload_json"):
        return {}
    try:
        data = json.loads(row["payload_json"])
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _market_block(name: str, block: dict[str, Any] | None) -> dict[str, Any]:
    block = block or {}
    total = int(block.get("total") or 0)
    correct = int(block.get("correct") or 0)
    wrong = max(0, total - correct)
    winrate = block.get("winrate")
    accuracy = float(winrate) if winrate is not None else None
    return {
        "market": name,
        "total": total,
        "correct": correct,
        "wrong": wrong,
        "pending": 0,
        "accuracy": accuracy,
    }


def _normalize_status(raw: str | None) -> str:
    value = str(raw or "pending").lower()
    if value in {"correct", "wrong", "pending"}:
        return value
    if value in {"unknown", "void"}:
        return "pending"
    return "pending"


def _prediction_label(payload: dict[str, Any], field: str) -> str | None:
    if field == "prediction":
        return payload.get("prediction") or payload.get("one_x_two")
    if field == "over_under_2_5":
        ou = (payload.get("probabilities") or {}).get("over_under_2_5")
        if isinstance(ou, dict):
            return ou.get("selection") or ou.get("pick")
        return payload.get("over_under")
    if field == "btts":
        btts = (payload.get("probabilities") or {}).get("btts")
        if isinstance(btts, dict):
            return btts.get("selection") or btts.get("pick")
    return None


def _build_recent_results(
    repo: FootballIntelligenceRepository,
    *,
    competition_key: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    rows = repo.list_worldcup_prediction_evaluations(competition_key=competition_key)
    rows.sort(key=lambda r: str(r.get("evaluated_at") or ""), reverse=True)

    results: list[dict[str, Any]] = []
    for ev in rows:
        if len(results) >= limit:
            break
        fid = int(ev["fixture_id"])
        fixture = repo.get_fixture_row(fid) or {}
        stored = _parse_payload(repo.get_worldcup_stored_prediction(fid))
        home = fixture.get("home_team") or stored.get("home_team") or "Home"
        away = fixture.get("away_team") or stored.get("away_team") or "Away"
        match_name = f"{home} vs {away}"
        match_date = fixture.get("kickoff_utc") or stored.get("kickoff_utc")
        confidence = stored.get("confidence")

        for market_label, status_col, pred_field in _EVAL_MARKET_COLUMNS:
            status = _normalize_status(ev.get(status_col))
            if status == "pending" and ev.get("overall_status") not in {"pending", None}:
                continue
            prediction = _prediction_label(stored, pred_field)
            if prediction is None and status == "pending":
                continue
            results.append(
                {
                    "fixture_id": fid,
                    "match_name": match_name,
                    "market": market_label,
                    "prediction": prediction,
                    "actual_result": ev.get("actual_result"),
                    "final_score": ev.get("final_score"),
                    "status": status,
                    "confidence": float(confidence) if confidence is not None else None,
                    "match_date": match_date,
                }
            )
            if len(results) >= limit:
                break
    return results


def _summary_from_jsonl_tracker() -> dict[str, Any] | None:
    try:
        from worldcup_predictor.accuracy.service import AccuracyTrackerService

        snapshot = AccuracyTrackerService().load_summary_from_disk()
    except Exception:
        return None
    if snapshot is None or snapshot.metrics.total_evaluated <= 0:
        return None

    correct = sum(1 for item in snapshot.evaluated if item.one_x_two_correct)
    wrong = len(snapshot.evaluated) - correct
    ou_eval = [item for item in snapshot.evaluated if item.over_under_correct is not None]
    ou_correct = sum(1 for item in ou_eval if item.over_under_correct)
    fg_eval = [item for item in snapshot.evaluated if item.first_goal_evaluated]
    fg_correct = sum(1 for item in fg_eval if item.first_goal_correct)

    markets = [
        _market_block(
            "1X2",
            {"total": len(snapshot.evaluated), "correct": correct, "winrate": metrics.one_x_two_accuracy},
        ),
        _market_block(
            "Over/Under 2.5",
            {"total": len(ou_eval), "correct": ou_correct, "winrate": metrics.over_under_2_5_accuracy},
        ),
    ]
    if fg_eval:
        markets.append(
            _market_block(
                "First Goal Team",
                {"total": len(fg_eval), "correct": fg_correct, "winrate": metrics.first_goal_accuracy},
            )
        )
    recent: list[dict[str, Any]] = []
    for item in snapshot.evaluated[:20]:
        recent.append(
            {
                "fixture_id": item.fixture_id,
                "match_name": item.match_name,
                "market": "1X2",
                "prediction": item.predicted_1x2,
                "actual_result": item.actual_1x2,
                "final_score": item.final_score,
                "status": "correct" if item.one_x_two_correct else "wrong",
                "confidence": item.confidence_score,
                "match_date": item.date,
            }
        )

    return {
        "overall_accuracy": metrics.one_x_two_accuracy,
        "total_predictions": metrics.total_predictions,
        "correct_predictions": correct,
        "wrong_predictions": wrong,
        "pending_predictions": metrics.pending_predictions,
        "accuracy_by_market": markets,
        "recent_results": recent,
        "updated_at": _utc_now_iso(),
        "data_source": "jsonl_learning_memory",
        "competition_key": "world_cup_2026",
        "disclaimer": "Historical model evaluation does not guarantee future results.",
    }


def build_public_accuracy_summary(
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
    recent_limit: int = 20,
) -> dict[str, Any]:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)

    summary = get_accuracy_summary(settings=settings, competition_key=competition_key)
    evaluated = int((summary or {}).get("evaluated_predictions") or 0)
    correct = int((summary or {}).get("correct") or 0)
    wrong = int((summary or {}).get("wrong") or 0)
    pending = int((summary or {}).get("pending") or 0)
    total = int((summary or {}).get("total_evaluations") or 0)

    if summary and evaluated > 0:
        markets = [_market_block(label, summary.get(key)) for label, key in _MARKET_SUMMARY_KEYS]
        fg_block = summary.get("first_goal_team")
        if isinstance(fg_block, dict) and fg_block.get("total"):
            markets.append(_market_block("First Goal Team", fg_block))

        overall = summary.get("winrate")
        if overall is None and evaluated > 0:
            overall = round(correct / evaluated, 4)

        return {
            "status": "ok",
            "overall_accuracy": overall,
            "total_predictions": int(summary.get("total_stored_predictions") or total),
            "correct_predictions": correct,
            "wrong_predictions": wrong,
            "pending_predictions": pending,
            "accuracy_by_market": markets,
            "recent_results": _build_recent_results(repo, competition_key=competition_key, limit=recent_limit),
            "updated_at": summary.get("updated_at") or _utc_now_iso(),
            "data_source": "worldcup_sqlite_evaluations",
            "competition_key": competition_key,
            "disclaimer": "Accuracy is calculated from finished matches only.",
        }

    jsonl_payload = _summary_from_jsonl_tracker()
    if jsonl_payload is not None:
        return {"status": "ok", **jsonl_payload}

    return {
        "status": "ok",
        "overall_accuracy": None,
        "total_predictions": repo.count_worldcup_stored_predictions(competition_key=competition_key),
        "correct_predictions": 0,
        "wrong_predictions": 0,
        "pending_predictions": pending or total,
        "accuracy_by_market": [_market_block(label, None) for label, _ in _MARKET_SUMMARY_KEYS],
        "recent_results": [],
        "updated_at": _utc_now_iso(),
        "data_source": "empty",
        "competition_key": competition_key,
        "disclaimer": "Accuracy is calculated from finished matches only.",
    }
