"""Sharp Money & Odds Movement Intelligence V2 — Phase 40."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.agents.base import AgentResult, BaseAgent
from worldcup_predictor.agents.specialists.helpers import make_signal, require_intelligence
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.odds.sharp_money_intelligence_engine import build_sharp_money_intelligence
from worldcup_predictor.odds.snapshot_service import OddsSnapshotService


class SharpMoneyIntelligenceAgent(BaseAgent):
    """Detect sharp money, odds movement, and market disagreement — API-Football only."""

    name = "sharp_money_intelligence_agent"
    domain = "sharp_money_intelligence_v2"

    def run(self, **kwargs: Any) -> AgentResult:
        report = require_intelligence(self.context, kwargs.get("fixture_id"))
        if report is None:
            return self._fail("No intelligence report available.")

        fixture_id = int(kwargs.get("fixture_id") or report.fixture_id)

        snapshots: list[dict[str, Any]] = []
        try:
            repo = FootballIntelligenceRepository()
            snapshots = repo.fetch_odds_snapshots(fixture_id)
            OddsSnapshotService(repo).persist_from_report(report)
            repo.close()
        except Exception:
            snapshots = []

        result = build_sharp_money_intelligence(report, stored_snapshots=snapshots)
        payload = result.to_dict()

        has_odds = result.bookmaker_count_1x2 > 0 or result.odds_tracking.history_available
        status = "unavailable" if not has_odds else ("partial" if result.odds_tracking.snapshot_count < 2 else "available")

        warnings: list[str] = []
        if not has_odds:
            warnings.append("API-Football odds unavailable — market intelligence remains minimal.")
        if result.steam_move_detected:
            warnings.append("Steam move detected — informational only, not betting advice.")
        if result.reverse_line_movement:
            warnings.append("Reverse line movement detected — interpret cautiously (analysis only).")
        if "high_market_disagreement" in result.risk_flags:
            warnings.append("Bookmakers disagree — market read uncertain.")

        signal = make_signal(
            self.name,
            self.domain,
            status,
            payload,
            warnings=warnings,
            missing_data=["odds"] if not has_odds else (["odds_snapshots"] if result.odds_tracking.snapshot_count < 2 else []),
            impact_score=result.market_confidence,
            notes=result.summary,
        )
        self.context.shared.setdefault("specialist_signals", {})[self.name] = signal
        return self._ok(data=signal, message="Sharp Money & Market Intelligence V2 complete")
