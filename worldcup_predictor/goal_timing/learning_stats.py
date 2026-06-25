"""Learning statistics from goal-timing evaluations (Phase 51E)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.goal_timing.storage.repository import GoalTimingRepository


def _dq_bucket(score: float | None) -> str:
    if score is None:
        return "unknown"
    s = float(score)
    if s < 0.45:
        return "dq_lt_0_45"
    if s < 0.55:
        return "dq_0_45_0_55"
    if s < 0.65:
        return "dq_0_55_0_65"
    return "dq_gte_0_65"


def _confidence_bucket(score: float | None) -> str:
    if score is None:
        return "unknown"
    s = float(score)
    if s < 0.5:
        return "conf_lt_0_50"
    if s < 0.65:
        return "conf_0_50_0_65"
    return "conf_gte_0_65"


def _aggregate_statuses(statuses: list[str]) -> dict[str, Any]:
    correct = sum(1 for s in statuses if s == "correct")
    wrong = sum(1 for s in statuses if s == "wrong")
    partial = sum(1 for s in statuses if s == "partial")
    pending = sum(1 for s in statuses if s == "pending")
    decided = correct + wrong
    soft_decided = correct + partial + wrong
    return {
        "correct": correct,
        "wrong": wrong,
        "partial": partial,
        "pending": pending,
        "total": len(statuses),
        "winrate": round(correct / decided, 4) if decided else None,
        "soft_winrate": round((correct + partial) / soft_decided, 4) if soft_decided else None,
    }


def _bucket_winrates(
    rows: list[dict[str, Any]],
    *,
    bucket_field: str,
    status_field: str,
) -> dict[str, Any]:
    buckets: dict[str, list[str]] = {}
    for row in rows:
        key = str(row.get(bucket_field) or "unknown")
        buckets.setdefault(key, []).append(str(row.get(status_field) or "pending"))
    return {k: _aggregate_statuses(v) for k, v in sorted(buckets.items())}


def build_goal_timing_learning_stats(
    *,
    settings: Settings | None = None,
    competition_key: str | None = None,
    limit: int = 2000,
) -> dict[str, Any]:
    settings = settings or get_settings()
    repo = GoalTimingRepository(settings)
    rows = repo.list_evaluations_joined(
        competition_key=competition_key,
        limit=limit,
        offset=0,
        evaluated_only=False,
    )

    team_statuses = [str(r.get("first_goal_team_status") or "pending") for r in rows]
    range_statuses = [str(r.get("time_range_status") or "pending") for r in rows]
    minute_statuses = [str(r.get("minute_tolerance_status") or "pending") for r in rows]

    by_market = {
        "first_goal_team": _aggregate_statuses(team_statuses),
        "goal_range": _aggregate_statuses(range_statuses),
        "goal_minute": _aggregate_statuses(minute_statuses),
    }

    league_rows: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        league = str(row.get("competition_key") or "unknown")
        league_rows.setdefault(league, []).append(row)

    by_league: dict[str, Any] = {}
    for league, league_items in sorted(league_rows.items()):
        by_league[league] = {
            "first_goal_team": _aggregate_statuses(
                [str(r.get("first_goal_team_status") or "pending") for r in league_items]
            ),
            "goal_range": _aggregate_statuses(
                [str(r.get("time_range_status") or "pending") for r in league_items]
            ),
            "goal_minute": _aggregate_statuses(
                [str(r.get("minute_tolerance_status") or "pending") for r in league_items]
            ),
        }

    dq_rows = [{**r, "_dq_bucket": _dq_bucket(
        float(r["data_quality_score"]) if r.get("data_quality_score") is not None else None
    )} for r in rows]
    conf_rows = [{**r, "_conf_bucket": _confidence_bucket(
        float(r["confidence_score"]) if r.get("confidence_score") is not None else None
    )} for r in rows]

    fg_rows = [{**r, "_fg_team": str(r.get("first_goal_team") or "none")} for r in rows]

    return {
        "sample_size": len(rows),
        "by_market": by_market,
        "by_league": by_league,
        "by_dq_bucket": {
            "first_goal_team": _bucket_winrates(dq_rows, bucket_field="_dq_bucket", status_field="first_goal_team_status"),
            "goal_range": _bucket_winrates(dq_rows, bucket_field="_dq_bucket", status_field="time_range_status"),
            "goal_minute": _bucket_winrates(dq_rows, bucket_field="_dq_bucket", status_field="minute_tolerance_status"),
        },
        "by_confidence_bucket": {
            "first_goal_team": _bucket_winrates(conf_rows, bucket_field="_conf_bucket", status_field="first_goal_team_status"),
            "goal_range": _bucket_winrates(conf_rows, bucket_field="_conf_bucket", status_field="time_range_status"),
            "goal_minute": _bucket_winrates(conf_rows, bucket_field="_conf_bucket", status_field="minute_tolerance_status"),
        },
        "by_predicted_first_goal_team": {
            "first_goal_team": _bucket_winrates(fg_rows, bucket_field="_fg_team", status_field="first_goal_team_status"),
            "goal_range": _bucket_winrates(fg_rows, bucket_field="_fg_team", status_field="time_range_status"),
            "goal_minute": _bucket_winrates(fg_rows, bucket_field="_fg_team", status_field="minute_tolerance_status"),
        },
    }
