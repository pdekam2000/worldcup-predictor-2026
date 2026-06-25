from __future__ import annotations

from typing import Any

from worldcup_predictor.goal_timing.agents._helpers import feature_agent_output
from worldcup_predictor.goal_timing.agents.base import GoalTimingAgentBase
from worldcup_predictor.goal_timing.models import GoalTimingAgentOutput


class OddsGoalIntelligenceAgent(GoalTimingAgentBase):
    name = "odds_goal_intelligence"

    def analyze(self, fixture_id: int, *, features: dict[str, Any], context: dict[str, Any]) -> GoalTimingAgentOutput:
        strategy = str(features.get("paid_provider_strategy") or "production")
        reliable = bool(features.get("has_reliable_goal_odds"))
        pf = features.get("provider_features") or {}
        if strategy != "A" and reliable and pf.get("odds_implied_home") is not None:
            home = float(pf["odds_implied_home"])
            away = float(pf.get("odds_implied_away") or 0.0)
            return feature_agent_output(
                self.name,
                features=features,
                signals={
                    "reliable_odds": True,
                    "implied_home": home,
                    "implied_away": away,
                    "implied_draw": pf.get("odds_implied_draw"),
                    "odds_movement_home": pf.get("odds_movement_home"),
                    "market_favorite": "home" if home >= away else "away",
                    "focus": "goal_timing_odds",
                },
                impact_score=min(1.0, 0.4 + abs(home - away)),
                missing=[],
                notes="Goal-market odds from stored SQLite snapshots.",
            )
        return feature_agent_output(
            self.name,
            features=features,
            signals={"reliable_odds": reliable, "focus": "goal_timing_odds"},
            impact_score=0.6 if reliable else 0.15,
            missing=[] if reliable else ["goal_market_odds"],
            notes="Goal-market odds not available in Phase 51D baseline.",
        )
