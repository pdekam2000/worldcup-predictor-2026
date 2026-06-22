from __future__ import annotations

from typing import Any

from worldcup_predictor.goal_timing.agents._helpers import feature_agent_output, range_entropy
from worldcup_predictor.goal_timing.agents.base import GoalTimingAgentBase
from worldcup_predictor.goal_timing.models import GoalTimingAgentOutput


class TacticalGoalFlowAgent(GoalTimingAgentBase):
    name = "tactical_goal_flow"

    def analyze(self, fixture_id: int, *, features: dict[str, Any], context: dict[str, Any]) -> GoalTimingAgentOutput:
        split = features.get("home_away_split") or {}
        home_home = split.get("home_team_home_scoring") or {}
        home_away = split.get("home_team_away_scoring") or {}
        away_home = split.get("away_team_home_scoring") or {}
        away_away = split.get("away_team_away_scoring") or {}
        home_venue_edge = sum(float(home_home.get(k, 0)) for k in home_home) - sum(
            float(home_away.get(k, 0)) for k in home_away
        )
        away_venue_edge = sum(float(away_home.get(k, 0)) for k in away_home) - sum(
            float(away_away.get(k, 0)) for k in away_away
        )
        flow = round(home_venue_edge - away_venue_edge, 4)
        impact = min(1.0, 0.35 + abs(flow) / 10.0 + (1.0 - range_entropy(home_home)) * 0.2)
        return feature_agent_output(
            self.name,
            features=features,
            signals={
                "home_venue_flow_edge": round(home_venue_edge, 4),
                "away_venue_flow_edge": round(away_venue_edge, 4),
                "combined_flow_edge": flow,
            },
            impact_score=impact,
            missing=[] if home_home or away_away else ["tactical_style_vectors"],
            notes="Home/away scoring split as tactical flow proxy.",
        )
