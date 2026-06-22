from __future__ import annotations

from typing import Any

from worldcup_predictor.goal_timing.agents._helpers import feature_agent_output
from worldcup_predictor.goal_timing.agents.base import GoalTimingAgentBase
from worldcup_predictor.goal_timing.models import GoalTimingAgentOutput


class MotivationGoalAgent(GoalTimingAgentBase):
    name = "motivation_goal"

    def analyze(self, fixture_id: int, *, features: dict[str, Any], context: dict[str, Any]) -> GoalTimingAgentOutput:
        comp = str(features.get("competition_key") or "")
        league_base = features.get("league_baseline_timing") or {}
        samples = int(league_base.get("samples") or 0)
        is_league = comp in {"premier_league", "la_liga", "bundesliga", "serie_a", "ligue_1"}
        impact = min(1.0, 0.4 + samples / 200.0) if is_league else 0.3
        return feature_agent_output(
            self.name,
            features=features,
            signals={
                "competition_context": comp,
                "league_baseline_samples": samples,
                "must_win_proxy": False,
            },
            impact_score=impact,
            missing=["tournament_context"] if not is_league else [],
            notes="Domestic league context only; tournament motivation deferred.",
        )
