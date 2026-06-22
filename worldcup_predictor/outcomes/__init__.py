"""Phase 46C-1 — persisted fixture outcomes for advanced market evaluation."""

from worldcup_predictor.outcomes.models import GoalEvent, ParsedFixtureOutcome
from worldcup_predictor.outcomes.event_parser import parse_api_football_goal_events
from worldcup_predictor.outcomes.outcome_persistence import (
    build_parsed_outcome,
    needs_outcome_backfill,
    persist_fixture_outcome,
)

__all__ = [
    "GoalEvent",
    "ParsedFixtureOutcome",
    "parse_api_football_goal_events",
    "build_parsed_outcome",
    "needs_outcome_backfill",
    "persist_fixture_outcome",
]
