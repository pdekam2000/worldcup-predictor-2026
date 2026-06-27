"""Phase 42D — global public prediction archive (SQLite + merge with user history)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from worldcup_predictor.api.prediction_history_evaluation import (
    FixtureOutcomeResolver,
    evaluate_history_record,
    filter_by_result_status,
)
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.postgres.schemas import PredictionHistoryRecord
from worldcup_predictor.database.repository import FootballIntelligenceRepository

HistoryScope = Literal["my", "global", "all"]
GLOBAL_ENTRY_PREFIX = "global-"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def global_entry_id(fixture_id: int) -> str:
    return f"{GLOBAL_ENTRY_PREFIX}{int(fixture_id)}"


def is_global_entry_id(entry_id: str) -> bool:
    return str(entry_id or "").startswith(GLOBAL_ENTRY_PREFIX)


def parse_global_fixture_id(entry_id: str) -> int | None:
    if not is_global_entry_id(entry_id):
        return None
    try:
        return int(str(entry_id)[len(GLOBAL_ENTRY_PREFIX) :])
    except ValueError:
        return None


def _parse_payload(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    raw = row.get("payload_json")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _normalize_status(raw: str | None) -> str:
    value = str(raw or "pending").lower()
    if value in {"correct", "wrong", "pending"}:
        return value
    if value in {"unknown", "void"}:
        return "pending"
    return "pending"


def _main_prediction(payload: dict[str, Any]) -> str | None:
    pred = payload.get("prediction") or payload.get("one_x_two")
    if pred:
        return str(pred)
    mw = (payload.get("detailed_markets") or {}).get("match_winner") or {}
    if isinstance(mw, dict) and mw.get("selection"):
        return str(mw["selection"])
    return None


def _confidence_value(payload: dict[str, Any]) -> float | None:
    raw = payload.get("confidence")
    if raw is None:
        mw = (payload.get("detailed_markets") or {}).get("match_winner") or {}
        if isinstance(mw, dict):
            raw = mw.get("probability")
    if raw is None:
        return None
    try:
        num = float(raw)
    except (TypeError, ValueError):
        return None
    if 0 <= num <= 1:
        return round(num * 100, 1)
    return round(num, 1)


def _markets_count(payload: dict[str, Any]) -> int:
    dm = payload.get("detailed_markets")
    if isinstance(dm, dict) and dm:
        return len([k for k, v in dm.items() if isinstance(v, dict) and v.get("selection")])
    probs = payload.get("probabilities")
    if isinstance(probs, dict):
        return len(probs)
    return 1 if _main_prediction(payload) else 0


def _detect_source(payload: dict[str, Any], stored_row: dict[str, Any]) -> str:
    gen_by = str(payload.get("generated_by") or payload.get("source") or stored_row.get("source") or "").lower()
    if gen_by == "background_daily" or "background" in gen_by:
        return "background_daily"
    if gen_by in {"system", "admin", "worldcup_background"}:
        return "system"
    return "global_archive"


def _evaluation_for_fixture(evaluations: dict[int, dict[str, Any]], fixture_id: int) -> dict[str, Any] | None:
    return evaluations.get(int(fixture_id))


def build_global_archive_row(
    stored_row: dict[str, Any],
    *,
    evaluation: dict[str, Any] | None,
    fixture: dict[str, Any] | None,
    resolver: FixtureOutcomeResolver,
) -> dict[str, Any]:
    fixture_id = int(stored_row["fixture_id"])
    payload = _parse_payload(stored_row)
    home = (
        fixture.get("home_team")
        if fixture
        else payload.get("home_team") or stored_row.get("home_team") or "Home"
    )
    away = (
        fixture.get("away_team")
        if fixture
        else payload.get("away_team") or stored_row.get("away_team") or "Away"
    )
    outcome = resolver.resolve(fixture_id)
    status = _normalize_status((evaluation or {}).get("market_1x2_status") or (evaluation or {}).get("overall_status"))
    if outcome.is_finished and status == "pending" and evaluation:
        status = _normalize_status(evaluation.get("overall_status"))

    match_date = (
        fixture.get("kickoff_utc")
        if fixture
        else stored_row.get("kickoff_utc") or payload.get("kickoff_utc")
    )
    generated_at = stored_row.get("predicted_at") or payload.get("generated_at") or payload.get("predicted_at")

    main_pred = _main_prediction(payload)
    return {
        "entry_id": global_entry_id(fixture_id),
        "id": global_entry_id(fixture_id),
        "source": _detect_source(payload, stored_row),
        "fixture_id": fixture_id,
        "match_name": f"{home} vs {away}",
        "home_team": home,
        "away_team": away,
        "league": payload.get("competition") or payload.get("league") or "World Cup 2026",
        "match_date": match_date,
        "generated_at": generated_at,
        "prediction_date": generated_at,
        "viewed_at": generated_at,
        "main_prediction": main_pred,
        "predicted_1x2": main_pred,
        "prediction_1x2": main_pred,
        "confidence": _confidence_value(payload),
        "predicted_confidence": _confidence_value(payload),
        "result_status": status,
        "result": status,
        "actual_result": outcome.actual_result if outcome.is_finished else (evaluation or {}).get("actual_result"),
        "final_score": outcome.final_score if outcome.is_finished else (evaluation or {}).get("final_score"),
        "markets_count": _markets_count(payload),
        "can_open_detail": True,
        "is_finished": outcome.is_finished,
        "evaluated_at": (evaluation or {}).get("evaluated_at"),
    }


def list_global_archive_rows(
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
    limit: int = 200,
    offset: int = 0,
    result_filter: str = "all",
) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    resolver = FixtureOutcomeResolver(settings=settings)

    stored_rows = repo.list_worldcup_stored_predictions(
        competition_key=competition_key,
        limit=max(limit + offset, limit),
        offset=0,
    )
    eval_rows = repo.list_worldcup_prediction_evaluations(competition_key=competition_key)
    evaluations = {int(r["fixture_id"]): r for r in eval_rows}

    items: list[dict[str, Any]] = []
    for row in stored_rows:
        fid = int(row["fixture_id"])
        fixture = repo.get_fixture_row(fid) or {}
        items.append(
            build_global_archive_row(
                row,
                evaluation=_evaluation_for_fixture(evaluations, fid),
                fixture=fixture,
                resolver=resolver,
            )
        )

    items.sort(key=lambda r: str(r.get("generated_at") or r.get("match_date") or ""), reverse=True)
    sliced = items[offset : offset + limit]
    return filter_by_result_status(sliced, result_filter)


def list_my_history_rows(
    user_id: uuid.UUID,
    *,
    settings: Settings | None = None,
    limit: int = 100,
    offset: int = 0,
    result_filter: str = "all",
) -> list[dict[str, Any]]:
    from worldcup_predictor.database.saas_factory import saas_uow

    settings = settings or get_settings()
    resolver = FixtureOutcomeResolver(settings=settings)
    with saas_uow() as uow:
        rows = uow.prediction_history.list_for_user(user_id, limit=limit, offset=offset)

    items = [evaluate_history_record(row, resolver=resolver, settings=settings) for row in rows]
    for item in items:
        item["entry_id"] = str(item.get("id"))
        item["source"] = "my"
        item["main_prediction"] = item.get("predicted_1x2") or item.get("prediction_1x2")
        item["generated_at"] = item.get("viewed_at")
        item["prediction_date"] = item.get("viewed_at")
        item["can_open_detail"] = True
        item["markets_count"] = item.get("markets_count") or 1
    return filter_by_result_status(items, result_filter)


def merge_history_rows(
    my_rows: list[dict[str, Any]],
    global_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge by fixture_id — prefer user-specific entry."""
    merged: dict[int, dict[str, Any]] = {}
    for row in global_rows:
        fid = int(row.get("fixture_id") or 0)
        if fid:
            merged[fid] = row
    for row in my_rows:
        fid = int(row.get("fixture_id") or 0)
        if fid:
            merged[fid] = row
    out = list(merged.values())
    out.sort(key=lambda r: str(r.get("generated_at") or r.get("match_date") or r.get("viewed_at") or ""), reverse=True)
    return out


def compute_history_stats(items: list[dict[str, Any]]) -> dict[str, Any]:
    settled = [item for item in items if item.get("result_status") in ("correct", "wrong")]
    correct = sum(1 for item in settled if item.get("result_status") == "correct")
    wrong = sum(1 for item in settled if item.get("result_status") == "wrong")
    pending = sum(1 for item in items if item.get("result_status") == "pending")
    unknown = sum(1 for item in items if item.get("result_status") == "unknown")
    accuracy = round((correct / len(settled)) * 100, 1) if settled else 0.0
    return {
        "total": len(items),
        "correct": correct,
        "wrong": wrong,
        "pending": pending,
        "unknown": unknown,
        "accuracy": accuracy,
    }


def fetch_merged_history(
    user_id: uuid.UUID,
    *,
    scope: HistoryScope = "all",
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
    limit: int = 100,
    offset: int = 0,
    result_filter: str = "all",
) -> dict[str, Any]:
    settings = settings or get_settings()
    scope_norm = str(scope or "all").lower()
    if scope_norm not in {"my", "global", "all"}:
        scope_norm = "all"

    my_rows: list[dict[str, Any]] = []
    global_rows: list[dict[str, Any]] = []

    if scope_norm in {"my", "all"}:
        my_rows = list_my_history_rows(
            user_id,
            settings=settings,
            limit=limit,
            offset=offset if scope_norm == "my" else 0,
            result_filter=result_filter,
        )
    if scope_norm in {"global", "all"}:
        global_rows = list_global_archive_rows(
            settings=settings,
            competition_key=competition_key,
            limit=limit,
            offset=offset if scope_norm == "global" else 0,
            result_filter=result_filter,
        )

    if scope_norm == "my":
        history = my_rows
    elif scope_norm == "global":
        history = global_rows
    else:
        history = merge_history_rows(my_rows, global_rows)
        history = history[offset : offset + limit]

    return {
        "status": "ok",
        "scope": scope_norm,
        "history": history,
        "stats": compute_history_stats(history),
        "sources_included": {
            "my": len(my_rows),
            "global": len(global_rows),
            "merged_total": len(history),
        },
        "updated_at": _utc_now_iso(),
    }
