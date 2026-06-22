"""Human-readable explanation generator."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.goal_timing.models import GoalTimingAgentOutput


class GoalTimingExplanationGenerator:
    def generate(
        self,
        calibrated: dict[str, Any],
        agent_outputs: dict[str, GoalTimingAgentOutput],
        *,
        data_quality: float,
        no_prediction: bool,
        home_team: str = "Home",
        away_team: str = "Away",
    ) -> str:
        if no_prediction:
            dq = agent_outputs.get("data_quality")
            missing = ", ".join(dq.missing_data[:4]) if dq and dq.missing_data else "core inputs"
            return (
                f"No goal-timing prediction published — data quality ({data_quality:.0%}) is below threshold. "
                f"Missing or limited: {missing}."
            )
        team = calibrated.get("first_goal_team", "none")
        if team == "home":
            team_label = home_team
        elif team == "away":
            team_label = away_team
        else:
            team_label = "no clear first scorer"
        rng = calibrated.get("first_goal_time_range", "—")
        minute = calibrated.get("display_estimated_first_goal_minute")
        minute_txt = f"~{minute:.0f}'" if minute is not None else "n/a"
        pattern = agent_outputs.get("goal_timing_pattern")
        dom = pattern.signals.get("league_dominant_range") if pattern else None
        league_note = f" League timing baseline favors {dom}." if dom else ""
        return (
            f"Baseline model: first goal {team_label} in {rng} ({minute_txt}). "
            f"Data quality {data_quality:.0%}.{league_note}"
        )
