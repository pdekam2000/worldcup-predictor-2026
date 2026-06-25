"""Phase 42D — global public prediction archive (SQLite + merge with user history)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from worldcup_predictor.api.archive_evaluation_join import (
    enrich_row_with_evaluation,
    merge_history_row_pair,
)
from worldcup_predictor.api.prediction_history_evaluation import (
    FixtureOutcomeResolver,
    evaluate_history_record,
    filter_by_result_status,
)
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.postgres.schemas import PredictionHistoryRecord
from worldcup_predictor.database.repository import FootballIntelligenceRepository

HistoryScope = Literal["my", "global", "all"]
HistorySort = Literal["newest", "oldest", "match_date_desc", "match_date_asc"]
GLOBAL_ENTRY_PREFIX = "global-"
MAX_MERGED_HISTORY = 500


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
    if value in {"correct", "wrong", "partial", "pending"}:
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


def predicted_market_keys_from_payload(payload: dict[str, Any]) -> list[str]:
    """Read-only list of canonical market keys present in a stored prediction payload."""
    dm = payload.get("detailed_markets")
    keys: list[str] = []

    def _has_pick(block: Any) -> bool:
        if not isinstance(block, dict):
            return False
        return bool(
            block.get("selection")
            or block.get("team")
            or block.get("player")
            or block.get("minute_range")
            or block.get("expected_minute")
        )

    if not isinstance(dm, dict):
        return ["1x2"] if _main_prediction(payload) else []

    if _has_pick(dm.get("match_winner")) or _main_prediction(payload):
        keys.append("1x2")
    if _has_pick(dm.get("btts")):
        keys.append("btts")
    if _has_pick(dm.get("over_under_25")):
        keys.append("over_under_2_5")
    cs = dm.get("correct_scores")
    if isinstance(cs, dict) and (cs.get("selection") or cs.get("top_scores") or cs.get("primary")):
        keys.append("correct_score")
    fg = dm.get("first_goal")
    if isinstance(fg, dict) and fg.get("team"):
        keys.append("first_goal_team")
    if isinstance(fg, dict) and (fg.get("minute_range") or fg.get("expected_minute")):
        keys.append("goal_minute")
    if _has_pick(dm.get("goal_timing")) and "goal_minute" not in keys:
        keys.append("goal_minute")
    return keys or (["1x2"] if _main_prediction(payload) else [])


def _detect_source(payload: dict[str, Any], stored_row: dict[str, Any]) -> str:
    row_source = str(stored_row.get("source") or "").lower()
    if row_source == "legacy_import":
        return "legacy_import"
    gen_by = str(payload.get("generated_by") or payload.get("source") or row_source or "").lower()
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
    row_status, row_reason = ("pending", "no_valid_evaluation")
    market_counts: dict[str, int] = {}
    market_statuses: dict[str, str] = {}
    if evaluation and not int(evaluation.get("is_quarantined") or 0):
        from worldcup_predictor.api.archive_evaluation_join import compute_row_status_from_evaluation, count_market_statuses, market_statuses_from_evaluation_row

        row_status, row_reason = compute_row_status_from_evaluation(evaluation)
        market_counts = count_market_statuses(market_statuses_from_evaluation_row(evaluation))
        market_statuses = market_statuses_from_evaluation_row(evaluation)
    else:
        row_status = _normalize_status((evaluation or {}).get("market_1x2_status") or (evaluation or {}).get("overall_status"))
        if outcome.is_finished and row_status == "pending" and evaluation:
            row_status = _normalize_status(evaluation.get("overall_status"))

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
        "match_date": (
            fixture.get("kickoff_utc")
            if fixture
            else stored_row.get("kickoff_utc") or payload.get("kickoff_utc")
        ),
        "generated_at": stored_row.get("predicted_at") or payload.get("generated_at") or payload.get("predicted_at"),
        "prediction_date": stored_row.get("predicted_at") or payload.get("generated_at") or payload.get("predicted_at"),
        "viewed_at": stored_row.get("predicted_at") or payload.get("generated_at") or payload.get("predicted_at"),
        "main_prediction": main_pred,
        "predicted_1x2": main_pred,
        "prediction_1x2": main_pred,
        "confidence": _confidence_value(payload),
        "predicted_confidence": _confidence_value(payload),
        "result_status": row_status,
        "result": row_status,
        "evaluation_status": row_status,
        "row_status_reason": row_reason,
        "evaluated_markets_count": market_counts.get("evaluated_markets_count", 0),
        "correct_markets_count": market_counts.get("correct_markets_count", 0),
        "wrong_markets_count": market_counts.get("wrong_markets_count", 0),
        "pending_markets_count": market_counts.get("pending_markets_count", 0),
        "market_statuses": market_statuses,
        "actual_result": evaluation.get("actual_result") if evaluation else (outcome.actual_result if outcome.is_finished else None),
        "final_score": evaluation.get("final_score") if evaluation else (outcome.final_score if outcome.is_finished else None),
        "markets_count": _markets_count(payload),
        "predicted_market_keys": predicted_market_keys_from_payload(payload),
        "can_open_detail": True,
        "is_finished": row_status in {"correct", "wrong", "partial"} or outcome.is_finished,
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
        include_quarantined=False,
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
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    eval_rows = repo.list_worldcup_prediction_evaluations(competition_key="world_cup_2026")
    evaluations = {int(r["fixture_id"]): r for r in eval_rows}

    with saas_uow() as uow:
        rows = uow.prediction_history.list_for_user(user_id, limit=limit, offset=offset)

    items = [evaluate_history_record(row, resolver=resolver, settings=settings) for row in rows]
    enriched_items: list[dict[str, Any]] = []
    for item in items:
        item["entry_id"] = str(item.get("id"))
        item["source"] = "my"
        item["main_prediction"] = item.get("predicted_1x2") or item.get("prediction_1x2")
        item["generated_at"] = item.get("viewed_at")
        item["prediction_date"] = item.get("viewed_at")
        item["can_open_detail"] = True
        item["markets_count"] = item.get("markets_count") or 1
        fid = int(item.get("fixture_id") or 0)
        enriched_items.append(enrich_row_with_evaluation(item, evaluations.get(fid)))
    return filter_by_result_status(enriched_items, result_filter)


def sort_history_rows(items: list[dict[str, Any]], sort: str = "newest") -> list[dict[str, Any]]:
    sort_key = str(sort or "newest").lower()

    def _generated(row: dict[str, Any]) -> str:
        return str(row.get("generated_at") or row.get("viewed_at") or row.get("prediction_date") or "")

    def _match_date(row: dict[str, Any]) -> str:
        return str(row.get("match_date") or "")

    if sort_key == "oldest":
        return sorted(items, key=_generated)
    if sort_key == "match_date_asc":
        return sorted(items, key=_match_date)
    if sort_key == "match_date_desc":
        return sorted(items, key=_match_date, reverse=True)
    return sorted(items, key=_generated, reverse=True)


def count_global_archive_rows(
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
) -> int:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    return repo.count_worldcup_stored_predictions(
        competition_key=competition_key,
        include_quarantined=False,
    )


def merge_history_rows(
    my_rows: list[dict[str, Any]],
    global_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge by fixture_id — prefer user entry but keep production evaluation status."""
    merged: dict[int, dict[str, Any]] = {}
    for row in global_rows:
        fid = int(row.get("fixture_id") or 0)
        if fid:
            merged[fid] = row
    for row in my_rows:
        fid = int(row.get("fixture_id") or 0)
        if fid:
            existing = merged.get(fid)
            merged[fid] = merge_history_row_pair(existing, row) if existing else row
    out = list(merged.values())
    out.sort(key=lambda r: str(r.get("generated_at") or r.get("match_date") or r.get("viewed_at") or ""), reverse=True)
    return out


def compute_history_stats(items: list[dict[str, Any]]) -> dict[str, Any]:
    settled = [item for item in items if item.get("result_status") in ("correct", "wrong")]
    partial = sum(1 for item in items if item.get("result_status") == "partial")
    correct = sum(1 for item in settled if item.get("result_status") == "correct")
    wrong = sum(1 for item in settled if item.get("result_status") == "wrong")
    pending = sum(1 for item in items if item.get("result_status") == "pending")
    unknown = sum(1 for item in items if item.get("result_status") == "unknown")
    accuracy = round((correct / len(settled)) * 100, 1) if settled else 0.0
    return {
        "total": len(items),
        "correct": correct,
        "wrong": wrong,
        "partial": partial,
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
    sort: str = "newest",
) -> dict[str, Any]:
    settings = settings or get_settings()
    scope_norm = str(scope or "all").lower()
    if scope_norm not in {"my", "global", "all"}:
        scope_norm = "all"

    fetch_limit = min(max(limit + offset, limit), MAX_MERGED_HISTORY)
    my_rows: list[dict[str, Any]] = []
    global_rows: list[dict[str, Any]] = []

    if scope_norm in {"my", "all"}:
        my_rows = list_my_history_rows(
            user_id,
            settings=settings,
            limit=fetch_limit if scope_norm == "all" else limit,
            offset=offset if scope_norm == "my" else 0,
            result_filter="all" if scope_norm == "all" else result_filter,
        )
    if scope_norm in {"global", "all"}:
        global_rows = list_global_archive_rows(
            settings=settings,
            competition_key=competition_key,
            limit=MAX_MERGED_HISTORY if scope_norm in {"global", "all"} else limit,
            offset=0,
            result_filter="all",
        )

    stats_source: list[dict[str, Any]]

    if scope_norm == "my":
        full_history = sort_history_rows(my_rows, sort)
        if result_filter != "all":
            full_history = filter_by_result_status(full_history, result_filter)
        total_count = len(full_history)
        stats_source = full_history
        history = full_history[offset : offset + limit]
    elif scope_norm == "global":
        total_count = count_global_archive_rows(settings=settings, competition_key=competition_key)
        full_history = sort_history_rows(global_rows, sort)
        if result_filter != "all":
            full_history = filter_by_result_status(full_history, result_filter)
            total_count = len(full_history)
        stats_source = full_history
        history = full_history[offset : offset + limit]
    else:
        full_history = sort_history_rows(merge_history_rows(my_rows, global_rows), sort)
        if result_filter != "all":
            full_history = filter_by_result_status(full_history, result_filter)
        total_count = len(full_history)
        stats_source = full_history
        history = full_history[offset : offset + limit]

    return {
        "status": "ok",
        "scope": scope_norm,
        "sort": sort,
        "history": history,
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
        "stats": compute_history_stats(stats_source),
        "sources_included": {
            "my": len(my_rows),
            "global": len(global_rows),
            "merged_total": total_count if scope_norm == "all" else len(history),
            "global_archive_total": count_global_archive_rows(settings=settings, competition_key=competition_key),
        },
        "updated_at": _utc_now_iso(),
    }
