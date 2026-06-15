from __future__ import annotations

from typing import Any

from worldcup_predictor.agents.base import AgentResult, BaseAgent
from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.competitions import get_competition
from worldcup_predictor.domain.fixture import FixtureCollection


class FixtureAgent(BaseAgent):
    """Fetches upcoming fixtures for the active competition."""

    name = "fixture_agent"

    def __init__(self, context, api_client: ApiFootballClient | None = None) -> None:
        super().__init__(context)
        self._api = api_client or ApiFootballClient(context.settings)

    def run(self, **kwargs: Any) -> AgentResult:
        limit = int(kwargs.get("limit", self.context.settings.upcoming_fixture_limit))
        competition = get_competition(self.context.competition_key)

        collection: FixtureCollection = self._api.fetch_upcoming_fixtures(
            competition=competition,
            limit=limit,
        )

        self.context.shared["fixtures"] = collection
        self.context.shared["competition"] = competition

        source_label = "live API" if not collection.is_placeholder else "placeholder data"
        return self._ok(
            data=collection,
            message=f"Loaded {len(collection.fixtures)} fixtures from {source_label}",
        )
