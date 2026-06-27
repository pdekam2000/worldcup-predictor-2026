"""Read-only evaluated prediction results for Results page and APIs (Hotfix Pack 3)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from worldcup_predictor.api.global_prediction_archive import (
    _main_prediction,
    _parse_payload,
    build_global_archive_row,
    predicted_market_keys_from_payload,
)
from worldcup_predictor.api.market_level_evaluation import (
    compute_archive_winrate_stats,
    limited_historical_payload,
    market_rows_from_evaluation,
    market_view_for_row,
    resolve_best_bet_market_keys,
    row_matches_market_filter,
)
from worldcup_predictor.api.match_evaluation import RESULT_COLORS, evaluation_summary_from_row
from worldcup_predictor.api.prediction_history_evaluation import (
    FixtureOutcomeResolver,
    filter_by_result_status,
)
from worldcup_predictor.config.competitions import get_competition
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository

ResultsRange = Literal["yesterday", "7d", "30d", "all"]
ResultsStatus = Literal["correct", "wrong", "partial", "pending", "all"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_dt(raw: Any) -> datetime | None:
    if not raw:
        return None
    text = str(raw).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except ValueError:
        return None


def _kickoff_date(row: dict[str, Any]) -> date | None:
    for key in ("kickoff", "match_date", "kickoff_utc"):
        dt = _parse_dt(row.get(key))
        if dt:
            return dt.date()
    return None


def _evaluated_date(row: dict[str, Any]) -> date | None:
    dt = _parse_dt(row.get("evaluated_at"))
    return dt.date() if dt else None


def _client_local_today(*, utc_offset_minutes: int | None = None) -> date:
    """Map UTC now to client-local calendar date (offset = -Date.getTimezoneOffset())."""
    now = datetime.now(timezone.utc)
    if utc_offset_minutes is None:
        return now.date()
    return (now + timedelta(minutes=int(utc_offset_minutes))).date()


def _date_in_range(
    anchor: date,
    range_key: str,
    *,
    today: date | None = None,
) -> bool:
    normalized = str(range_key or "all").lower()
    if normalized in {"all", "*"}:
        return True
    today = today or _utc_now().date()
    if normalized == "yesterday":
        return anchor == today - timedelta(days=1)
    if normalized == "7d":
        return anchor >= today - timedelta(days=7)
    if normalized == "30d":
        return anchor >= today - timedelta(days=30)
    return True


def _row_in_range(
    row: dict[str, Any],
    range_key: str,
    *,
    today: date | None = None,
) -> bool:
    """Match if kickoff OR evaluated_at falls in range (fixes empty yesterday/7d tabs)."""
    normalized = str(range_key or "all").lower()
    if normalized in {"all", "*"}:
        return True
    anchors = [d for d in (_kickoff_date(row), _evaluated_date(row)) if d is not None]
    if not anchors:
        return False
    return any(_date_in_range(d, normalized, today=today) for d in anchors)


def _in_range(kickoff: date | None, range_key: str, *, today: date | None = None) -> bool:
    """Legacy single-date helper — prefer _row_in_range."""
    normalized = str(range_key or "all").lower()
    if normalized in {"all", "*"}:
        return True
    if kickoff is None:
        return False
    return _date_in_range(kickoff, normalized, today=today)


def _competition_label(competition_key: str, payload: dict[str, Any]) -> str:
    try:
        return get_competition(competition_key).display_name
    except KeyError:
        return str(payload.get("competition") or payload.get("league") or competition_key or "Competition")


def _prediction_summary_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    main = _main_prediction(payload)
    dm = payload.get("detailed_markets") if isinstance(payload.get("detailed_markets"), dict) else {}
    mw = dm.get("match_winner") if isinstance(dm.get("match_winner"), dict) else {}
    return {
        "best_pick": main,
        "prediction_1x2": main,
        "confidence": payload.get("confidence") or mw.get("probability"),
        "markets_predicted": predicted_market_keys_from_payload(payload),
        "engine_version": payload.get("engine_version") or payload.get("pipeline_version"),
    }


def _detail_url(fixture_id: int, competition_key: str | None) -> str:
    base = f"/matches/{int(fixture_id)}"
    if competition_key:
        return f"{base}?competition={competition_key}"
    return base


def build_evaluated_result_row(
    eval_row: dict[str, Any],
    *,
    stored_row: dict[str, Any] | None,
    fixture: dict[str, Any] | None,
    resolver: FixtureOutcomeResolver,
    include_quarantined: bool = True,
) -> dict[str, Any] | None:
    fixture_id = int(eval_row.get("fixture_id") or 0)
    if fixture_id <= 0:
        return None

    payload = _parse_payload(stored_row)
    competition_key = str(
        eval_row.get("competition_key")
        or (stored_row or {}).get("competition_key")
        or payload.get("competition_key")
        or "world_cup_2026"
    )

    archive_row = None
    if stored_row:
        archive_row = build_global_archive_row(
            stored_row,
            evaluation=eval_row,
            fixture=fixture,
            resolver=resolver,
        )

    home = (
        (fixture or {}).get("home_team")
        or payload.get("home_team")
        or (archive_row or {}).get("home_team")
        or "Home"
    )
    away = (
        (fixture or {}).get("away_team")
        or payload.get("away_team")
        or (archive_row or {}).get("away_team")
        or "Away"
    )
    kickoff = (
        (fixture or {}).get("kickoff_utc")
        or (stored_row or {}).get("kickoff_utc")
        or payload.get("kickoff_utc")
        or (archive_row or {}).get("match_date")
    )

    eval_summary = evaluation_summary_from_row(
        eval_row,
        include_quarantined=include_quarantined,
    )
    if not eval_summary:
        return None

    overall_status = eval_summary.get("result_status") or "pending"
    pred_summary = _prediction_summary_from_payload(payload) if payload else {
        "best_pick": (archive_row or {}).get("main_prediction"),
        "prediction_1x2": (archive_row or {}).get("predicted_1x2"),
        "confidence": (archive_row or {}).get("confidence"),
        "markets_predicted": (archive_row or {}).get("predicted_market_keys") or ["1x2"],
        "engine_version": None,
    }

    outcome = resolver.resolve(fixture_id)
    market_breakdown = market_rows_from_evaluation(eval_row, payload, outcome)
    market_counts = {
        "correct_markets_count": sum(1 for r in market_breakdown if r.get("status") == "correct"),
        "wrong_markets_count": sum(1 for r in market_breakdown if r.get("status") == "wrong"),
        "pending_markets_count": sum(1 for r in market_breakdown if r.get("status") == "pending"),
        "unavailable_markets_count": sum(1 for r in market_breakdown if r.get("status") == "unavailable"),
        "evaluated_markets_count": sum(
            1 for r in market_breakdown if r.get("status") in {"correct", "wrong"}
        ),
    }
    has_best_bet = bool(resolve_best_bet_market_keys(payload)) if payload else False

    return {
        "fixture_id": fixture_id,
        "home_team": home,
        "away_team": away,
        "teams": f"{home} vs {away}",
        "competition": _competition_label(competition_key, payload),
        "competition_key": competition_key,
        "kickoff": kickoff,
        "match_date": kickoff,
        "final_score": eval_summary.get("final_score") or (archive_row or {}).get("final_score"),
        "actual_result": eval_summary.get("actual_result") or (archive_row or {}).get("actual_result"),
        "prediction_summary": pred_summary,
        "predicted_pick": pred_summary.get("best_pick"),
        "market_statuses": eval_summary.get("market_statuses") or {},
        "market_colors": eval_summary.get("market_colors") or {},
        "market_breakdown": market_breakdown,
        "has_best_bet": has_best_bet,
        "limited_historical_payload": limited_historical_payload(payload) if payload else False,
        "overall_status": overall_status,
        "result_status": overall_status,
        "evaluation_status": overall_status,
        "evaluation_reason": eval_summary.get("row_status_reason"),
        "colors": {
            "overall": RESULT_COLORS.get(overall_status, "gray"),
            **(eval_summary.get("market_colors") or {}),
        },
        "evaluated_at": eval_summary.get("evaluated_at") or eval_row.get("evaluated_at"),
        "detail_url": _detail_url(fixture_id, competition_key),
        "archive_entry_id": f"global-{fixture_id}",
        "has_stored_prediction": stored_row is not None,
        "is_quarantined": bool(eval_summary.get("is_quarantined")),
        "quarantine_reason": eval_row.get("quarantine_reason"),
        **market_counts,
    }


def list_evaluated_results(
    *,
    settings: Settings | None = None,
    range_key: str = "all",
    status_filter: str = "all",
    market_filter: str = "all",
    limit: int = 100,
    offset: int = 0,
    competition_key: str | None = None,
    utc_offset_minutes: int | None = None,
) -> dict[str, Any]:
    """List production evaluation rows joined with stored predictions (no fake data)."""
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    resolver = FixtureOutcomeResolver(settings=settings)

    try:
        eval_rows = repo.list_all_worldcup_prediction_evaluations(include_quarantined=True)
        if competition_key and competition_key not in {"all", "*"}:
            eval_rows = [r for r in eval_rows if str(r.get("competition_key") or "") == competition_key]

        built: list[dict[str, Any]] = []
        today = _client_local_today(utc_offset_minutes=utc_offset_minutes)
        for eval_row in eval_rows:
            fixture_id = int(eval_row["fixture_id"])
            stored = repo.get_worldcup_stored_prediction(fixture_id)
            fixture = repo.get_fixture_row(fixture_id)
            row = build_evaluated_result_row(
                eval_row,
                stored_row=stored,
                fixture=fixture,
                resolver=resolver,
                include_quarantined=True,
            )
            if not row:
                continue
            if not _row_in_range(row, range_key, today=today):
                continue
            built.append(row)

        built.sort(key=lambda r: str(r.get("kickoff") or r.get("evaluated_at") or ""), reverse=True)

        if market_filter and market_filter not in {"all", "*"}:
            built = [r for r in built if row_matches_market_filter(r, market_filter)]
            for row in built:
                view = market_view_for_row(row, market_filter)
                if view:
                    row["filtered_market_view"] = view
                    row["predicted_pick"] = view.get("display_pick") or view.get("predicted_pick")
                    row["filtered_market_status"] = view.get("status")

        if status_filter and status_filter not in {"all", "*"}:
            built = filter_by_result_status(built, status_filter)

        total = len(built)
        page = built[offset : offset + limit]

        counts = {
            "correct": sum(1 for r in built if r.get("overall_status") == "correct"),
            "wrong": sum(1 for r in built if r.get("overall_status") == "wrong"),
            "partial": sum(1 for r in built if r.get("overall_status") == "partial"),
            "pending": sum(1 for r in built if r.get("overall_status") == "pending"),
            "unavailable": sum(1 for r in built if r.get("overall_status") == "unavailable"),
        }
        winrate = compute_archive_winrate_stats(built)

        return {
            "status": "ok",
            "range": range_key,
            "status_filter": status_filter,
            "market_filter": market_filter,
            "utc_offset_minutes": utc_offset_minutes,
            "range_anchor_date": today.isoformat(),
            "total_count": total,
            "limit": limit,
            "offset": offset,
            "counts": counts,
            "winrate": winrate,
            "results": page,
        }
    finally:
        repo.close()


def build_finished_match_row_from_evaluation(
    eval_row: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Synthetic Match Center row for evaluated fixtures missing from live schedule."""
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    resolver = FixtureOutcomeResolver(settings=settings)
    try:
        fixture_id = int(eval_row.get("fixture_id") or 0)
        stored = repo.get_worldcup_stored_prediction(fixture_id)
        if not stored:
            return None
        fixture = repo.get_fixture_row(fixture_id)
        result = build_evaluated_result_row(
            eval_row,
            stored_row=stored,
            fixture=fixture,
            resolver=resolver,
        )
        if not result:
            return None

        competition_key = str(result.get("competition_key") or "world_cup_2026")
        try:
            comp = get_competition(competition_key)
            league = comp.display_name
            comp_name = comp.name
        except KeyError:
            league = result.get("competition") or "Competition"
            comp_name = league

        from worldcup_predictor.api.match_center_helpers import competition_emoji as _emoji

        comp_emoji = _emoji(competition_key) if competition_key else "⚽"

        eval_summary = evaluation_summary_from_row(eval_row) or {}
        pred_pick = result.get("predicted_pick")
        return {
            "id": fixture_id,
            "fixture_id": fixture_id,
            "home_team": result["home_team"],
            "away_team": result["away_team"],
            "match_date": result.get("kickoff"),
            "league": league,
            "competition_key": competition_key,
            "competition_name": comp_name,
            "competition_emoji": comp_emoji,
            "status": "FT",
            "bucket": "finished",
            "has_prediction": True,
            "final_score": result.get("final_score"),
            "home_goals": None,
            "away_goals": None,
            "result_status": result.get("overall_status"),
            "match_evaluation": eval_summary,
            "prediction_summary": {
                "best_pick": pred_pick,
                "selection": pred_pick,
                "confidence": (result.get("prediction_summary") or {}).get("confidence"),
            },
            "fixture_status_label": "Finished",
            "from_evaluated_supplement": True,
        }
    finally:
        repo.close()
