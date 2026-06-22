from __future__ import annotations

from typing import Any

from worldcup_predictor.goal_timing.agents._helpers import dominant_range, feature_agent_output
from worldcup_predictor.goal_timing.agents.base import GoalTimingAgentBase
from worldcup_predictor.goal_timing.models import GoalTimingAgentOutput


class GoalTimingPatternAgent(GoalTimingAgentBase):
    name = "goal_timing_pattern"

    def analyze(self, fixture_id: int, *, features: dict[str, Any], context: dict[str, Any]) -> GoalTimingAgentOutput:
        home_dist = (features.get("first_goal_minute_distribution") or {}).get("home") or {}
        away_dist = (features.get("first_goal_minute_distribution") or {}).get("away") or {}
        league_dist = (features.get("first_goal_minute_distribution") or {}).get("league") or {}
        home_dom = dominant_range(home_dist)
        away_dom = dominant_range(away_dist)
        samples = (features.get("history_samples") or {}).get("home_with_goal_minutes", 0)
        samples += int((features.get("history_samples") or {}).get("away_with_goal_minutes") or 0)
        coverage = min(1.0, samples / 20.0)
        impact = 0.25 + 0.55 * coverage
        return feature_agent_output(
            self.name,
            features=features,
            signals={
                "home_dominant_range": home_dom,
                "away_dominant_range": away_dom,
                "league_dominant_range": dominant_range(league_dist),
                "home_first_goal_minute_distribution": home_dist,
                "away_first_goal_minute_distribution": away_dist,
            },
            impact_score=impact,
            missing=[] if samples >= 8 else ["team_goal_minute_histograms"],
            notes="Historical score/concede timing from stored goal-minute data.",
        )
