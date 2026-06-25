"""Map fixture outcomes to Elite Goal Timing evaluation fields (Phase 51E)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcome
from worldcup_predictor.automation.worldcup_background.advanced_market_evaluator import _actual_first_goal_side
from worldcup_predictor.automation.worldcup_background.goal_minute_evaluator import (
    resolve_actual_first_goal_minute,
)


def resolve_actual_first_goal_team_side(
    outcome: FixtureOutcome,
    *,
    home_team: str | None,
    away_team: str | None,
) -> str | None:
    """Return home / away / none for comparison with predictions."""
    if not outcome.is_finished:
        return None
    final_score = getattr(outcome, "final_score", None)
    if final_score:
        try:
            left, _, right = str(final_score).partition("-")
            if int(left.strip()) + int(right.strip()) == 0:
                return "none"
        except ValueError:
            pass
    side = _actual_first_goal_side(outcome, home_team=home_team or "", away_team=away_team or "")
    if side in {"home", "away", "none"}:
        return side
    return None


def resolve_effective_first_goal_minute(outcome: FixtureOutcome) -> int | None:
    """Effective minute for range/minute evaluation (stoppage normalized)."""
    _raw, effective, _display = resolve_actual_first_goal_minute(outcome)
    return effective


def build_evaluation_actuals(
    outcome: FixtureOutcome,
    *,
    home_team: str | None,
    away_team: str | None,
) -> dict[str, Any]:
    team_side = resolve_actual_first_goal_team_side(
        outcome,
        home_team=home_team,
        away_team=away_team,
    )
    minute = resolve_effective_first_goal_minute(outcome)
    return {
        "actual_first_goal_team": team_side,
        "actual_first_goal_minute": minute,
        "is_finished": outcome.is_finished,
        "final_score": outcome.final_score,
    }
