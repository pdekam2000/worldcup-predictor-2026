"""Persist odds snapshots when bookmaker data is fetched."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.domain.intelligence import MatchIntelligenceReport

logger = logging.getLogger(__name__)


class OddsSnapshotService:
    """Save timestamped odds payloads to SQLite for movement analysis."""

    def __init__(self, repository: FootballIntelligenceRepository | None = None) -> None:
        self._repo = repository or FootballIntelligenceRepository()

    def persist_from_report(self, report: MatchIntelligenceReport) -> bool:
        """Store API-Sports + supplemental odds when available."""
        odds = report.odds
        supplemental = getattr(report, "supplemental_sources", None) or {}
        fixture = getattr(report, "fixture", None)
        competition_key = getattr(fixture, "competition_key", None) or "world_cup_2026"
        fixture_id = int(report.fixture_id)

        payload: dict[str, Any] = {
            "snapshot_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "source": report.source,
        }
        if odds and odds.available and odds.bookmakers:
            payload["api_sports"] = {"bookmakers": odds.bookmakers}
        if supplemental.get("rapid_football_stats"):
            payload["rapid_football_stats"] = supplemental["rapid_football_stats"]
        if supplemental.get("rapid_xg_statistics"):
            payload["rapid_xg_statistics"] = supplemental["rapid_xg_statistics"]
        if supplemental.get("the_odds_api"):
            payload["the_odds_api"] = supplemental["the_odds_api"]

        if len(payload) <= 2:
            return False

        try:
            self._repo.save_snapshot(
                "odds_snapshots",
                fixture_id=fixture_id,
                competition_key=competition_key,
                payload=payload,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.debug("Odds snapshot save skipped for %s: %s", fixture_id, exc)
            return False
