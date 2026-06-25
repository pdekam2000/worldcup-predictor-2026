"""Part A — post-match evaluation per market."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.elite_self_learning.models import ConfidenceTier, MarketEvaluation, OutcomeLabel


def _mw_reality(home: int, away: int) -> str:
    if home > away:
        return "home"
    if away > home:
        return "away"
    return "draw"


def reality_from_fixture_row(row: Any) -> dict[str, Any]:
    """Extract ground truth per market from expanded EGIE row."""
    hg = int(row.final_score_home)
    ag = int(row.final_score_away)
    return {
        "1x2": _mw_reality(hg, ag),
        "first_goal_team": str(row.label_first_goal_team),
        "team_to_score_first": str(row.label_first_goal_team),
        "goal_timing": str(getattr(row, "label_goal_range", None) or "unknown"),
        "anytime_goalscorer": None,
        "first_goalscorer": None,
        "over_under": "over_2_5" if int(row.label_over_25) == 1 else "under_2_5",
    }


def evaluate_market(
    *,
    market_id: str,
    prediction: Any,
    reality: Any,
    confidence: float,
    tier: ConfidenceTier,
) -> MarketEvaluation:
    outcome: OutcomeLabel = "abstain"
    brier: float | None = None

    if prediction is None or reality is None:
        outcome = "abstain"
    elif market_id in ("first_goal_team", "team_to_score_first", "1x2"):
        pred = str(prediction).lower()
        real = str(reality).lower()
        outcome = "correct" if pred == real else "incorrect"
        if market_id == "1x2" and confidence:
            hit = 1.0 if outcome == "correct" else 0.0
            brier = round((hit - confidence) ** 2, 4)
    elif market_id == "goal_timing":
        pred = str(prediction)
        real = str(reality)
        outcome = "correct" if pred == real else ("partial" if pred.split("-")[0] in real else "incorrect")
    elif market_id in ("anytime_goalscorer", "first_goalscorer"):
        if isinstance(prediction, list) and reality:
            outcome = "correct" if str(reality) in [str(p) for p in prediction] else "incorrect"
        else:
            outcome = "abstain"
    else:
        outcome = "correct" if prediction == reality else "incorrect"

    return MarketEvaluation(
        market_id=market_id,
        prediction=prediction,
        reality=reality,
        outcome=outcome,
        confidence=round(confidence, 4),
        tier=tier,
        brier=brier,
    )


def evaluate_post_match(
    *,
    fixture_id: int,
    sportmonks_fixture_id: int | None,
    league_id: int | None,
    competition_key: str | None,
    kickoff_utc: str | None,
    evaluated_at: str,
    shadow_markets: dict[str, dict[str, Any]],
    reality: dict[str, Any],
) -> list[MarketEvaluation]:
    results: list[MarketEvaluation] = []
    for market_id, block in shadow_markets.items():
        real = reality.get(market_id)
        if real is None and market_id not in ("anytime_goalscorer", "first_goalscorer"):
            continue
        results.append(
            evaluate_market(
                market_id=market_id,
                prediction=block.get("prediction"),
                reality=real,
                confidence=float(block.get("confidence") or 0.5),
                tier=block.get("tier") or "C",
            )
        )
    return results
