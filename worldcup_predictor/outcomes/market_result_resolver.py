"""Central market-specific result resolver — RESULT-TRUTH-REPAIR-1."""

from __future__ import annotations

from typing import Any, Literal

from worldcup_predictor.outcomes.provider_score_truth import ResultStageTruth, truth_from_result_row
from worldcup_predictor.schedule.match_center import actual_result

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

REGULATION_MARKETS = frozenset(
    {"1x2", "btts", "over_under_2_5", "correct_score", "double_chance"}
)


def _score_pair(home: int | None, away: int | None) -> str | None:
    if home is None or away is None:
        return None
    return f"{int(home)}-{int(away)}"


def _actual_side(home: int, away: int) -> str:
    act = actual_result(home, away)
    return act or "unknown"


def resolve_market_result(
    result_row: dict[str, Any] | None,
    fixture_row: dict[str, Any] | None = None,
    *,
    market_type: MarketType = "1x2",
) -> dict[str, Any]:
    """
    Resolve the authoritative score/outcome for a market type.

    Standard pre-match markets use regulation (90-minute) scores.
    Qualification / penalty_winner use post-AET/PEN advancement truth.
    """
    empty: dict[str, Any] = {
        "market_type": market_type,
        "home_goals": None,
        "away_goals": None,
        "final_score": None,
        "actual_result": None,
        "qualified_team": None,
        "penalties_score": None,
        "score_basis": "missing",
    }
    if not result_row:
        return empty

    truth = truth_from_result_row(result_row)
    fixture_row = fixture_row or {}

    if market_type == "ht_result":
        ht_h = result_row.get("ht_home_goals")
        ht_a = result_row.get("ht_away_goals")
        if ht_h is not None and ht_a is not None:
            h, a = int(ht_h), int(ht_a)
            return {
                "market_type": market_type,
                "home_goals": h,
                "away_goals": a,
                "final_score": _score_pair(h, a),
                "actual_result": _actual_side(h, a),
                "qualified_team": None,
                "penalties_score": None,
                "score_basis": "halftime",
            }
        ht = result_row.get("halftime_score")
        if ht and "-" in str(ht):
            try:
                h, a = [int(x.strip()) for x in str(ht).split("-", 1)]
                return {
                    "market_type": market_type,
                    "home_goals": h,
                    "away_goals": a,
                    "final_score": _score_pair(h, a),
                    "actual_result": _actual_side(h, a),
                    "qualified_team": None,
                    "penalties_score": None,
                    "score_basis": "halftime",
                }
            except ValueError:
                pass
        return empty

    if market_type == "qualification":
        qt = (truth.qualified_team if truth else None) or result_row.get("qualified_team") or result_row.get("winner")
        stage = (truth.final_stage if truth else str(result_row.get("final_stage") or result_row.get("match_outcome_type") or "FT"))
        return {
            "market_type": market_type,
            "home_goals": None,
            "away_goals": None,
            "final_score": truth.extra_time_score if truth and truth.final_stage == "AET" else truth.regulation_score if truth else result_row.get("final_score"),
            "actual_result": None,
            "qualified_team": qt,
            "penalties_score": truth.penalties_score if truth else result_row.get("penalty_score"),
            "score_basis": f"advancement_{stage.lower()}",
        }

    if market_type == "penalty_winner":
        pen = truth.penalties_score if truth else result_row.get("penalty_score")
        qt = None
        if truth and truth.penalties_home is not None and truth.penalties_away is not None:
            home_team = fixture_row.get("home_team") or ""
            away_team = fixture_row.get("away_team") or ""
            if truth.penalties_home > truth.penalties_away:
                qt = home_team
            elif truth.penalties_away > truth.penalties_home:
                qt = away_team
        return {
            "market_type": market_type,
            "home_goals": truth.penalties_home if truth else None,
            "away_goals": truth.penalties_away if truth else None,
            "final_score": pen,
            "actual_result": None,
            "qualified_team": qt,
            "penalties_score": pen,
            "score_basis": "penalties",
        }

    # Regulation markets
    if truth and truth.regulation_home is not None and truth.regulation_away is not None:
        h, a = truth.regulation_home, truth.regulation_away
        basis = "regulation_explicit"
    elif str(result_row.get("match_outcome_type") or "FT").upper() == "FT":
        h = result_row.get("home_goals")
        a = result_row.get("away_goals")
        basis = "legacy_ft"
    else:
        h = result_row.get("regulation_home_goals")
        a = result_row.get("regulation_away_goals")
        basis = "regulation_fallback"

    if h is None or a is None:
        return empty

    hi, ai = int(h), int(a)
    return {
        "market_type": market_type,
        "home_goals": hi,
        "away_goals": ai,
        "final_score": _score_pair(hi, ai),
        "actual_result": _actual_side(hi, ai),
        "qualified_team": None,
        "penalties_score": None,
        "score_basis": basis,
    }


def regulation_fixture_outcome_fields(
    result_row: dict[str, Any] | None,
    fixture_row: dict[str, Any] | None = None,
) -> tuple[int | None, int | None, str | None, str | None]:
    """Return (home_goals, away_goals, final_score, actual_result) for standard evaluation."""
    resolved = resolve_market_result(result_row, fixture_row, market_type="1x2")
    return (
        resolved.get("home_goals"),
        resolved.get("away_goals"),
        resolved.get("final_score"),
        resolved.get("actual_result"),
    )
