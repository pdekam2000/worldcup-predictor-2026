"""Aggregate historical backtest metrics (Phase 51H)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.goal_timing.learning_stats import (
    _aggregate_statuses,
    _bucket_winrates,
    _confidence_bucket,
    _dq_bucket,
)


def aggregate_backtest_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Build accuracy, bucket winrates, and league breakdown from backtest rows."""
    clean = [r for r in rows if "error" not in r]
    published = [r for r in clean if not r.get("no_prediction_flag")]
    evaluable = [r for r in published if r.get("evaluable")]

    team_statuses = [str(r.get("first_goal_team_status") or "pending") for r in evaluable]
    range_statuses = [str(r.get("time_range_status") or "pending") for r in evaluable]
    minute_statuses = [str(r.get("minute_tolerance_status") or "pending") for r in evaluable]

    by_market = {
        "first_goal_team": _aggregate_statuses(team_statuses),
        "goal_range": _aggregate_statuses(range_statuses),
        "goal_minute": _aggregate_statuses(minute_statuses),
    }

    dq_rows = [
        {
            **r,
            "_dq_bucket": _dq_bucket(float(r["data_quality_score"]) if r.get("data_quality_score") is not None else None),
        }
        for r in evaluable
    ]
    conf_rows = [
        {
            **r,
            "_conf_bucket": _confidence_bucket(
                float(r["confidence_score"]) if r.get("confidence_score") is not None else None
            ),
        }
        for r in evaluable
    ]

    league_groups: dict[str, list[dict[str, Any]]] = {}
    for row in evaluable:
        key = str(row.get("competition_key") or "unknown")
        league_groups.setdefault(key, []).append(row)

    by_league: dict[str, Any] = {}
    for league, items in sorted(league_groups.items()):
        by_league[league] = {
            "sample_size": len(items),
            "first_goal_team": _aggregate_statuses(
                [str(i.get("first_goal_team_status") or "pending") for i in items]
            ),
            "goal_range": _aggregate_statuses(
                [str(i.get("time_range_status") or "pending") for i in items]
            ),
            "goal_minute": _aggregate_statuses(
                [str(i.get("minute_tolerance_status") or "pending") for i in items]
            ),
        }

    no_pick = [r for r in clean if r.get("no_prediction_flag")]

    return {
        "fixtures_scanned": len(clean),
        "published_predictions": len(published),
        "no_pick_count": len(no_pick),
        "evaluable_published": len(evaluable),
        "skipped_not_evaluable": len(published) - len(evaluable),
        "by_market": by_market,
        "by_league": by_league,
        "by_dq_bucket": {
            "first_goal_team": _bucket_winrates(dq_rows, bucket_field="_dq_bucket", status_field="first_goal_team_status"),
            "goal_range": _bucket_winrates(dq_rows, bucket_field="_dq_bucket", status_field="time_range_status"),
            "goal_minute": _bucket_winrates(dq_rows, bucket_field="_dq_bucket", status_field="minute_tolerance_status"),
        },
        "by_confidence_bucket": {
            "first_goal_team": _bucket_winrates(
                conf_rows, bucket_field="_conf_bucket", status_field="first_goal_team_status"
            ),
            "goal_range": _bucket_winrates(conf_rows, bucket_field="_conf_bucket", status_field="time_range_status"),
            "goal_minute": _bucket_winrates(
                conf_rows, bucket_field="_conf_bucket", status_field="minute_tolerance_status"
            ),
        },
    }


def build_calibration_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Confidence vs hit-rate calibration for each market (published + evaluable only)."""
    evaluable = [r for r in rows if not r.get("no_prediction_flag") and r.get("evaluable")]

    def _cal_for_field(status_field: str) -> dict[str, Any]:
        buckets: dict[str, dict[str, Any]] = {}
        for row in evaluable:
            bucket = _confidence_bucket(
                float(row["confidence_score"]) if row.get("confidence_score") is not None else None
            )
            status = str(row.get(status_field) or "pending")
            if status == "pending":
                continue
            entry = buckets.setdefault(
                bucket,
                {"bucket": bucket, "total": 0, "correct": 0, "partial": 0, "wrong": 0, "hit_rate": None},
            )
            entry["total"] += 1
            if status == "correct":
                entry["correct"] += 1
            elif status == "partial":
                entry["partial"] += 1
            elif status == "wrong":
                entry["wrong"] += 1
        for entry in buckets.values():
            decided = entry["correct"] + entry["wrong"]
            soft = entry["correct"] + entry["partial"] + entry["wrong"]
            entry["hit_rate"] = round(entry["correct"] / decided, 4) if decided else None
            entry["soft_hit_rate"] = round((entry["correct"] + entry["partial"]) / soft, 4) if soft else None
            entry["mean_confidence"] = None
        conf_sums: dict[str, list[float]] = {}
        for row in evaluable:
            bucket = _confidence_bucket(
                float(row["confidence_score"]) if row.get("confidence_score") is not None else None
            )
            status = str(row.get(status_field) or "pending")
            if status == "pending":
                continue
            conf_sums.setdefault(bucket, []).append(float(row.get("confidence_score") or 0))
        for bucket, vals in conf_sums.items():
            if bucket in buckets and vals:
                buckets[bucket]["mean_confidence"] = round(sum(vals) / len(vals), 4)
        return {k: buckets[k] for k in sorted(buckets)}

    return {
        "first_goal_team": _cal_for_field("first_goal_team_status"),
        "goal_range": _cal_for_field("time_range_status"),
        "goal_minute": _cal_for_field("minute_tolerance_status"),
    }
