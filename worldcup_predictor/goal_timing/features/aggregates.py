"""Aggregate timing statistics from historical matches."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.goal_timing.config import GOAL_TIMING_MINUTE_RANGES
from worldcup_predictor.goal_timing.data.stored_adapter import HistoricalMatchContext
from worldcup_predictor.goal_timing.minute_ranges import (
    CUMULATIVE_MINUTE_THRESHOLDS,
    counts_to_probabilities,
    effective_minute,
    empty_range_counts,
    minute_to_range_key,
    no_goal_before_minute_probs,
)
from worldcup_predictor.outcomes.models import GoalEvent


def _team_side_in_match(ctx: HistoricalMatchContext, team_name: str) -> str | None:
    if ctx.home_team == team_name:
        return "home"
    if ctx.away_team == team_name:
        return "away"
    return None


def _first_goal_side(ctx: HistoricalMatchContext, team_name: str) -> str | None:
    if ctx.goal_events:
        first = ctx.goal_events[0]
        if first.team == ctx.home_team:
            return "home" if team_name == ctx.home_team else "away" if team_name == ctx.away_team else None
        if first.team == ctx.away_team:
            return "away" if team_name == ctx.away_team else "home" if team_name == ctx.home_team else None
    fg = (ctx.first_goal_team or "").lower()
    side = _team_side_in_match(ctx, team_name)
    if not side or not fg:
        return None
    if fg in {"home", "home_win"} and side == "home":
        return "scored"
    if fg in {"away", "away_win"} and side == "away":
        return "scored"
    if fg in {"home", "home_win"} and side == "away":
        return "conceded"
    if fg in {"away", "away_win"} and side == "home":
        return "conceded"
    return None


def accumulate_team_timing(matches: list[HistoricalMatchContext], team_name: str) -> dict[str, Any]:
    scored = empty_range_counts()
    conceded = empty_range_counts()
    first_goal_scored = 0
    first_goal_conceded = 0
    first_goal_none = 0
    first_goal_minutes: list[int] = []
    goals_before: dict[int, int] = {t: 0 for t in CUMULATIVE_MINUTE_THRESHOLDS}
    home_scored = empty_range_counts()
    away_scored = empty_range_counts()
    samples = 0
    with_event_data = 0

    for ctx in matches:
        side = _team_side_in_match(ctx, team_name)
        if not side:
            continue
        samples += 1
        if ctx.has_goal_minute_data:
            with_event_data += 1

        fg_side = _first_goal_side(ctx, team_name)
        if fg_side == "scored":
            first_goal_scored += 1
        elif fg_side == "conceded":
            first_goal_conceded += 1
        else:
            first_goal_none += 1

        if ctx.goal_events:
            match_first_minute: int | None = None
            for ev in ctx.goal_events:
                minute = effective_minute(ev.minute, ev.extra_minute)
                if minute is None:
                    continue
                if match_first_minute is None:
                    match_first_minute = minute
                rng = minute_to_range_key(minute)
                if not rng:
                    continue
                scorer_is_home = ev.team == ctx.home_team or (
                    ev.team is None and side == "home"
                )
                scorer_is_away = ev.team == ctx.away_team or (
                    ev.team is None and side == "away"
                )
                if side == "home":
                    if scorer_is_home:
                        scored[rng] += 1
                        home_scored[rng] += 1
                    elif scorer_is_away:
                        conceded[rng] += 1
                else:
                    if scorer_is_away:
                        scored[rng] += 1
                        away_scored[rng] += 1
                    elif scorer_is_home:
                        conceded[rng] += 1
                for threshold in CUMULATIVE_MINUTE_THRESHOLDS:
                    if minute <= threshold:
                        goals_before[threshold] += 1
            if match_first_minute is not None:
                first_goal_minutes.append(match_first_minute)
        elif ctx.first_goal_minute is not None:
            first_goal_minutes.append(int(ctx.first_goal_minute))

    fg_total = max(first_goal_scored + first_goal_conceded + first_goal_none, 1)
    return {
        "samples": samples,
        "samples_with_goal_minute_data": with_event_data,
        "goals_scored_by_range": counts_to_probabilities(scored),
        "goals_conceded_by_range": counts_to_probabilities(conceded),
        "home_goals_scored_by_range": counts_to_probabilities(home_scored),
        "away_goals_scored_by_range": counts_to_probabilities(away_scored),
        "first_goal_team_distribution": {
            "scored_first": round(first_goal_scored / fg_total, 4),
            "conceded_first": round(first_goal_conceded / fg_total, 4),
            "no_first_goal_data": round(first_goal_none / fg_total, 4),
        },
        "first_goal_minute_distribution": _minute_histogram(first_goal_minutes),
        "goals_before_minute_rates": {
            str(t): round(goals_before[t] / max(samples, 1), 4) for t in CUMULATIVE_MINUTE_THRESHOLDS
        },
        "no_goal_before_minute_probability": no_goal_before_minute_probs(first_goal_minutes),
    }


def _minute_histogram(minutes: list[int]) -> dict[str, float]:
    counts = empty_range_counts()
    for m in minutes:
        key = minute_to_range_key(m)
        if key:
            counts[key] += 1
    return counts_to_probabilities(counts)


def league_baseline_timing(matches: list[HistoricalMatchContext]) -> dict[str, Any]:
    all_minutes: list[int] = []
    first_home = 0
    first_away = 0
    first_unknown = 0
    for ctx in matches:
        if ctx.goal_events:
            first = ctx.goal_events[0]
            if first.team == ctx.home_team:
                first_home += 1
            elif first.team == ctx.away_team:
                first_away += 1
            else:
                first_unknown += 1
            for ev in ctx.goal_events:
                m = effective_minute(ev.minute, ev.extra_minute)
                if m is not None:
                    all_minutes.append(m)
        elif ctx.first_goal_minute is not None:
            all_minutes.append(int(ctx.first_goal_minute))
    total = max(len(matches), 1)
    fg_total = max(first_home + first_away + first_unknown, 1)
    return {
        "samples": len(matches),
        "first_goal_team_distribution": {
            "home": round(first_home / fg_total, 4),
            "away": round(first_away / fg_total, 4),
            "unknown": round(first_unknown / fg_total, 4),
        },
        "first_goal_minute_distribution": _minute_histogram(all_minutes),
        "avg_goals_per_match": round(len(all_minutes) / total, 4),
        "no_goal_before_minute_probability": no_goal_before_minute_probs(all_minutes),
    }


def opponent_adjusted_features(
    team_features: dict[str, Any],
    opponent_features: dict[str, Any],
) -> dict[str, Any]:
    """Blend team attack timing with opponent conceding timing."""
    scored = team_features.get("goals_scored_by_range") or {}
    opp_conceded = opponent_features.get("goals_conceded_by_range") or {}
    blend: dict[str, float] = {}
    for key in GOAL_TIMING_MINUTE_RANGES:
        blend[key] = round((float(scored.get(key, 0)) + float(opp_conceded.get(key, 0))) / 2, 4)
    return {
        "adjusted_scoring_by_range": blend,
        "team_scoring": scored,
        "opponent_conceding": opp_conceded,
    }


def recent_form_timing(matches: list[HistoricalMatchContext], team_name: str, *, last_n: int = 5) -> dict[str, Any]:
    subset = matches[:last_n]
    return accumulate_team_timing(subset, team_name)
