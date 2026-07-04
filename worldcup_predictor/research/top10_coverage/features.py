"""Coverage rank buckets and actual outcome helpers."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.ecse_rerank.features import (
    is_btts,
    is_clean_sheet,
    parse_scoreline,
    total_goals,
    winner_side,
)

PHASE = "TOP10-COVERAGE-1"

RANK_BUCKETS = ("rank_1_5", "rank_6_10", "rank_11_20", "outside_stored", "unavailable")


def actual_outcome(actual: str | None) -> dict[str, Any]:
    if not actual:
        return {}
    parsed = parse_scoreline(actual)
    if not parsed:
        return {}
    h, a = parsed
    tg = h + a
    return {
        "actual_90min": actual,
        "total_goals": tg,
        "btts": "yes" if is_btts(actual) else "no",
        "winner": winner_side(actual),
        "clean_sheet": is_clean_sheet(actual),
        "over_25": "over_2_5" if tg > 2 else "under_2_5",
    }


def rank_bucket(rank: int | None, *, in_full: bool) -> str:
    if rank is None:
        return "outside_stored" if in_full else "unavailable"
    if rank <= 5:
        return "rank_1_5"
    if rank <= 10:
        return "rank_6_10"
    if rank <= 20:
        return "rank_11_20"
    return "outside_stored"


def hit_in_topn(actual: str | None, lines: list[str], n: int) -> bool:
    return bool(actual and actual in lines[:n])
