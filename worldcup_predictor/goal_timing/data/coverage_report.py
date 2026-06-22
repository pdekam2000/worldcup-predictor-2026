"""Coverage report for goal timing data wiring."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.goal_timing.data.sportmonks_coverage import probe_sportmonks_goal_timing_coverage
from worldcup_predictor.goal_timing.data.stored_adapter import StoredGoalTimingAdapter
from worldcup_predictor.goal_timing.leagues import GOAL_TIMING_ALLOWED_LEAGUE_KEYS, resolve_goal_timing_league


def build_goal_timing_coverage_report(
    *,
    stored: StoredGoalTimingAdapter | None = None,
    sample_fixture_ids: list[int] | None = None,
) -> dict[str, Any]:
    stored = stored or StoredGoalTimingAdapter()
    rows = stored.league_coverage_rows()
    by_key = {r["competition_key"]: r for r in rows}

    leagues: list[dict[str, Any]] = []
    total_finished = 0
    total_with_events = 0
    total_with_fg_minute = 0
    gaps: list[str] = []

    for key in GOAL_TIMING_ALLOWED_LEAGUE_KEYS:
        spec = resolve_goal_timing_league(key)
        row = by_key.get(key) or {}
        finished = int(row.get("finished_matches") or 0)
        with_events = int(row.get("with_goal_events") or 0)
        with_fg = int(row.get("with_first_goal_minute") or 0)
        total_finished += finished
        total_with_events += with_events
        total_with_fg_minute += with_fg
        coverage_pct = round((with_events / finished) * 100, 1) if finished else 0.0
        leagues.append(
            {
                "competition_key": key,
                "name": getattr(spec, "name", key) if spec else key,
                "finished_matches": finished,
                "with_goal_events": with_events,
                "with_first_goal_minute": with_fg,
                "goal_event_coverage_pct": coverage_pct,
            }
        )
        if finished == 0:
            gaps.append(f"No finished matches stored for {key}")
        elif with_events < finished * 0.5:
            gaps.append(f"Low goal-event coverage for {key} ({coverage_pct}%)")

    sportmonks = probe_sportmonks_goal_timing_coverage(sample_fixture_ids=sample_fixture_ids or [])

    return {
        "phase": "51C",
        "allowed_leagues": list(GOAL_TIMING_ALLOWED_LEAGUE_KEYS),
        "totals": {
            "finished_matches": total_finished,
            "with_goal_events": total_with_events,
            "with_first_goal_minute": total_with_fg_minute,
            "goal_event_coverage_pct": round((total_with_events / total_finished) * 100, 1)
            if total_finished
            else 0.0,
        },
        "leagues": leagues,
        "missing_data_gaps": gaps,
        "sportmonks": sportmonks,
    }
