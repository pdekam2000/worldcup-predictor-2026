from __future__ import annotations

from typing import Any

from worldcup_predictor.goal_timing.agents._helpers import feature_agent_output
from worldcup_predictor.goal_timing.agents.base import GoalTimingAgentBase
from worldcup_predictor.goal_timing.models import GoalTimingAgentOutput


class PlayerGoalThreatAgent(GoalTimingAgentBase):
    name = "player_goal_threat"

    def analyze(self, fixture_id: int, *, features: dict[str, Any], context: dict[str, Any]) -> GoalTimingAgentOutput:
        scored = features.get("team_goals_scored_by_range") or {}
        home_total = sum(float(v) for v in (scored.get("home") or {}).values())
        away_total = sum(float(v) for v in (scored.get("away") or {}).values())
        total = home_total + away_total
        home_share = round(home_total / total, 4) if total > 0 else 0.5
        impact = min(1.0, 0.35 + (total / 40.0))
        return feature_agent_output(
            self.name,
            features=features,
            signals={
                "home_scoring_volume": round(home_total, 2),
                "away_scoring_volume": round(away_total, 2),
                "home_scoring_share": home_share,
            },
            impact_score=impact,
            missing=[] if total > 0 else ["player_goal_stats"],
            notes="Proxy threat from team goal-minute scoring volume (no player-level stats yet).",
        )
