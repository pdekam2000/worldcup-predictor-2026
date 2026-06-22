from __future__ import annotations

from typing import Any

from worldcup_predictor.goal_timing.agents._helpers import feature_agent_output
from worldcup_predictor.goal_timing.agents.base import GoalTimingAgentBase
from worldcup_predictor.goal_timing.models import GoalTimingAgentOutput


class FirstGoalPressureAgent(GoalTimingAgentBase):
    name = "first_goal_pressure"

    def analyze(self, fixture_id: int, *, features: dict[str, Any], context: dict[str, Any]) -> GoalTimingAgentOutput:
        recent = features.get("recent_form_timing") or {}
        home_recent = recent.get("home") or {}
        away_recent = recent.get("away") or {}
        home_early = float((home_recent.get("goals_before_minute_rates") or {}).get("15") or 0.0)
        away_early = float((away_recent.get("goals_before_minute_rates") or {}).get("15") or 0.0)
        before = features.get("goals_before_minute") or {}
        home_15 = float((before.get("home") or {}).get("15") or home_early)
        away_15 = float((before.get("away") or {}).get("15") or away_early)
        pressure_home = round((home_early + home_15) / 2, 4)
        pressure_away = round((away_early + away_15) / 2, 4)
        impact = min(1.0, 0.3 + abs(pressure_home - pressure_away) + (pressure_home + pressure_away) / 2)
        return feature_agent_output(
            self.name,
            features=features,
            signals={
                "home_early_pressure": pressure_home,
                "away_early_pressure": pressure_away,
                "pressure_edge": "home" if pressure_home > pressure_away else "away" if pressure_away > pressure_home else "neutral",
            },
            impact_score=impact,
            missing=[] if (home_early or away_early) else ["early_goal_samples"],
            notes="Early scoring pressure from recent form and goals-before-15 rates.",
        )
