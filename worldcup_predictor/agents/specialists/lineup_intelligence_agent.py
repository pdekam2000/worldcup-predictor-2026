"""Lineup Intelligence V2 specialist agent — Phase 38."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.agents.base import AgentResult, BaseAgent
from worldcup_predictor.agents.specialists.helpers import make_signal, require_intelligence
from worldcup_predictor.lineups.lineup_intelligence_engine import build_lineup_intelligence


class LineupIntelligenceAgent(BaseAgent):
    """Deep lineup analysis — official XI, rotations, GK status, risk flags."""

    name = "lineup_intelligence_agent"
    domain = "lineup_intelligence_v2"

    def run(self, **kwargs: Any) -> AgentResult:
        report = require_intelligence(self.context, kwargs.get("fixture_id"))
        if report is None:
            return self._fail("No intelligence report available.")

        api_client = None
        try:
            if self.context.settings.api_football_configured:
                from worldcup_predictor.clients.api_football import ApiFootballClient

                api_client = ApiFootballClient(self.context.settings)
        except Exception:
            api_client = None

        result = build_lineup_intelligence(report, api_client=api_client)
        payload = result.to_dict()

        both_missing = not result.home.lineup_available and not result.away.lineup_available
        status = "unavailable" if both_missing else ("partial" if not result.home.official_lineup else "available")

        warnings: list[str] = []
        if both_missing:
            warnings.append("Official lineups not published yet — adjustments remain minimal.")
        if "backup_goalkeeper" in result.home.risk_flags + result.away.risk_flags:
            warnings.append("Backup goalkeeper detected — defensive uncertainty elevated (analysis only).")
        if "many_rotations" in result.home.risk_flags + result.away.risk_flags:
            warnings.append("Heavy rotation detected — reduce lineup confidence.")

        avg_strength = (result.home.lineup_strength + result.away.lineup_strength) / 2
        signal = make_signal(
            self.name,
            self.domain,
            status,
            payload,
            warnings=warnings,
            missing_data=["lineups"] if both_missing else [],
            impact_score=round(avg_strength, 1),
            notes=result.summary,
        )
        self.context.shared.setdefault("specialist_signals", {})[self.name] = signal
        return self._ok(data=signal, message="Lineup Intelligence V2 complete")
