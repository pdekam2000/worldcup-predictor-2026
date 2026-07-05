"""Central evaluation score policy — RESULT-TRUTH-SCHEMA-V8."""

from __future__ import annotations

from typing import Any, Literal

from worldcup_predictor.outcomes.market_result_resolver import (
    REGULATION_MARKETS,
    resolve_market_result,
)

MarketType = Literal[
    "1x2",
    "btts",
    "over_under_2_5",
    "correct_score",
    "double_chance",
    "ht_result",
    "qualification",
    "penalty_winner",
]

ResultResolutionType = Literal["REGULATION", "EXTRA_TIME", "PENALTIES"]


def result_resolution_type(result_row: dict[str, Any] | None) -> ResultResolutionType | None:
    """Map stored stage fields to canonical resolution type."""
    if not result_row:
        return None
    stage = str(result_row.get("final_stage") or result_row.get("match_outcome_type") or "FT").upper()
    if stage == "AET":
        return "EXTRA_TIME"
    if stage == "PEN":
        return "PENALTIES"
    return "REGULATION"


def select_evaluation_score(
    result_row: dict[str, Any] | None,
    fixture_row: dict[str, Any] | None = None,
    *,
    market_type: MarketType = "correct_score",
) -> dict[str, Any]:
    """
    Single entry point for prematch market evaluation score selection.

    EXACT SCORE / BTTS / O-U / 1X2 / DOUBLE CHANCE → regulation-time truth.
    QUALIFICATION / PENALTY WINNER → advancement or shootout truth.
    """
    if market_type in REGULATION_MARKETS or market_type == "correct_score":
        return resolve_market_result(result_row, fixture_row, market_type="correct_score" if market_type == "correct_score" else market_type)
    if market_type == "qualification":
        return resolve_market_result(result_row, fixture_row, market_type="qualification")
    if market_type == "penalty_winner":
        return resolve_market_result(result_row, fixture_row, market_type="penalty_winner")
    return resolve_market_result(result_row, fixture_row, market_type=market_type)


def regulation_score_for_evaluation(
    result_row: dict[str, Any] | None,
    fixture_row: dict[str, Any] | None = None,
) -> tuple[int | None, int | None, str | None, str]:
    """Return (home, away, scoreline, score_basis) for exact-score / standard prematch eval."""
    resolved = select_evaluation_score(result_row, fixture_row, market_type="correct_score")
    return (
        resolved.get("home_goals"),
        resolved.get("away_goals"),
        resolved.get("final_score"),
        str(resolved.get("score_basis") or "missing"),
    )
