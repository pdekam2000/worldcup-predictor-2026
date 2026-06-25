"""First-goal team probabilities from survival + historical rates."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.egie.survival.config import TEAM_ABSTAIN_RATE_GAP
from worldcup_predictor.egie.survival.kaplan_meier import survival_at


def team_first_goal_probabilities(
    *,
    home_rate: float,
    away_rate: float,
    league_survival_curve: list[dict[str, float]],
    range_probs: dict[str, float] | None = None,
) -> dict[str, float]:
    """
    Competing-risks style team probabilities.

    Uses historical first-goal rates adjusted by survival no-goal mass.
    """
    s90 = survival_at(league_survival_curve, 90.0)
    p_goal = max(0.0, 1.0 - s90)

    # Normalize directional rates
    total_rate = max(1e-9, home_rate + away_rate)
    p_home_cond = home_rate / total_rate
    p_away_cond = away_rate / total_rate

    p_home = round(p_home_cond * p_goal, 4)
    p_away = round(p_away_cond * p_goal, 4)
    p_no_goal = round(max(0.0, 1.0 - p_home - p_away), 4)

    # Slight timing-edge nudge from early-bucket mass (home advantage in early goals)
    if range_probs:
        early = float(range_probs.get("0-15") or 0.0) + float(range_probs.get("16-30") or 0.0)
        if early > 0.55:
            bump = min(0.03, (early - 0.55) * 0.05)
            p_home = round(min(p_goal, p_home + bump), 4)
            p_away = round(max(0.0, p_away - bump * 0.5), 4)
            p_no_goal = round(max(0.0, 1.0 - p_home - p_away), 4)

    return {
        "home_first_goal_probability": p_home,
        "away_first_goal_probability": p_away,
        "no_goal_probability": p_no_goal,
    }


def pick_team_with_abstain(
    probs: dict[str, float],
    *,
    threshold: float = TEAM_ABSTAIN_RATE_GAP,
) -> str:
    """
    Map probabilities to home / away / none using same gap rule as baseline.

    Compares home vs away conditional rates (re-normalized excluding no-goal).
    """
    p_home = float(probs.get("home_first_goal_probability") or 0.0)
    p_away = float(probs.get("away_first_goal_probability") or 0.0)
    directional = p_home + p_away
    if directional <= 0:
        return "none"
    home_cond = p_home / directional
    away_cond = p_away / directional
    if abs(home_cond - away_cond) < threshold:
        return "none"
    return "home" if home_cond > away_cond else "away"
