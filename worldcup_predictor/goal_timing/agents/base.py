"""Base class for goal timing specialist agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from worldcup_predictor.goal_timing.models import GoalTimingAgentOutput


class GoalTimingAgentBase(ABC):
    name: str = "goal_timing_agent"

    @abstractmethod
    def analyze(
        self,
        fixture_id: int,
        *,
        features: dict[str, Any],
        context: dict[str, Any],
    ) -> GoalTimingAgentOutput:
        ...
