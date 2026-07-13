"""Top5 coverage diagnostics for ECSE scorelines."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from worldcup_predictor.research.ecse_rerank.features import (
    is_btts,
    is_clean_sheet,
    parse_scoreline,
    winner_side,
)


def _entropy(probs: list[float]) -> float:
    s = 0.0
    for p in probs:
        if p > 0:
            s -= p * math.log(p)
    return round(s, 6)


def diagnose_top5_coverage(
    top5: list[str] | list[dict[str, Any]],
    *,
    top5_probs: list[float] | None = None,
) -> dict[str, Any]:
    """Analyze scenario coverage of canonical or shadow Top5."""
    lines: list[str] = []
    probs: list[float] = []
    if top5 and isinstance(top5[0], dict):
        for item in top5[:5]:
            lines.append(str(item.get("scoreline") or ""))
            probs.append(float(item.get("probability") or 0.0))
    else:
        lines = [str(x) for x in top5[:5]]
        probs = list(top5_probs or [0.0] * len(lines))

    directions = set()
    clean_sheet_count = 0
    btts_count = 0
    opponent_one_goal = 0
    opponent_two_plus = 0
    draw_count = 0
    total_goal_bands: Counter[int] = Counter()
    home_goal_counts: Counter[int] = Counter()
    away_goal_counts: Counter[int] = Counter()
    flags: list[str] = []

    for line in lines:
        parsed = parse_scoreline(line)
        if not parsed:
            continue
        h, a = parsed
        side = winner_side(line)
        if side:
            directions.add(side)
        if is_clean_sheet(line):
            clean_sheet_count += 1
        if is_btts(line):
            btts_count += 1
        if a == 1 or h == 1:
            opponent_one_goal += 1
        if a >= 2 or h >= 2:
            opponent_two_plus += 1
        if h == a:
            draw_count += 1
        total_goal_bands[h + a] += 1
        home_goal_counts[h] += 1
        away_goal_counts[a] += 1

    # Refined opponent-one-goal: away scores exactly 1 OR home scores exactly 1
    opp_one = sum(1 for line in lines if _line_has_exactly_one_opponent_goal(line))
    high_tail = sum(1 for line in lines if _line_high_score_tail(line))

    if clean_sheet_count == 5:
        flags.append("ALL_TOP5_SAME_CLEAN_SHEET_SCENARIO")
    if btts_count == 0 and lines:
        flags.append("ALL_TOP5_BTTS_NO")
    if opp_one == 0:
        flags.append("NO_OPPONENT_ONE_GOAL_COVERAGE")
    if draw_count == 0:
        flags.append("NO_DRAW_COVERAGE")
    if high_tail == 0:
        flags.append("NO_HIGH_SCORE_TAIL_COVERAGE")

    top5_mass = round(sum(probs[:5]), 6)
    concentration = round(max(probs) / top5_mass, 4) if top5_mass > 0 else None
    if concentration and concentration > 0.45:
        flags.append("TOP5_OVER_CONCENTRATED")

    unique_directions = len(directions)
    pairwise_similarity = _pairwise_similarity(lines)

    return {
        "scorelines": lines,
        "unique_end_result_directions": unique_directions,
        "end_result_directions": sorted(directions),
        "clean_sheet_scenario_count": clean_sheet_count,
        "btts_scenario_count": btts_count,
        "opponent_exactly_one_goal_count": opp_one,
        "opponent_2plus_goal_count": opponent_two_plus,
        "draw_scenario_count": draw_count,
        "high_score_tail_count": high_tail,
        "total_goal_bands": dict(sorted(total_goal_bands.items())),
        "home_goal_counts": dict(sorted(home_goal_counts.items())),
        "away_goal_counts": dict(sorted(away_goal_counts.items())),
        "pairwise_score_similarity": pairwise_similarity,
        "scenario_concentration": concentration,
        "top5_cumulative_mass": top5_mass,
        "entropy": _entropy(probs[:5]),
        "coverage_flags": flags,
    }


def _line_has_exactly_one_opponent_goal(line: str) -> bool:
    parsed = parse_scoreline(line)
    if not parsed:
        return False
    h, a = parsed
    return h == 1 or a == 1


def _line_high_score_tail(line: str) -> bool:
    parsed = parse_scoreline(line)
    if not parsed:
        return False
    h, a = parsed
    return h + a >= 5 or max(h, a) >= 3 and min(h, a) >= 2


def _pairwise_similarity(lines: list[str]) -> float:
    if len(lines) < 2:
        return 0.0
    parsed = [parse_scoreline(l) for l in lines]
    parsed = [p for p in parsed if p]
    if len(parsed) < 2:
        return 0.0
    diffs = []
    for i in range(len(parsed)):
        for j in range(i + 1, len(parsed)):
            h1, a1 = parsed[i]
            h2, a2 = parsed[j]
            diffs.append(abs(h1 - h2) + abs(a1 - a2))
    return round(sum(diffs) / len(diffs), 4)
