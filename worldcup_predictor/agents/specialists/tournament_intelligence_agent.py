"""Tournament Intelligence V2 — Phase 43."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.agents.base import AgentResult, BaseAgent
from worldcup_predictor.agents.specialists.helpers import make_signal, require_intelligence
from worldcup_predictor.schedule.context_loader import fixture_tournament_context, load_tournament_context
from worldcup_predictor.tournament.tournament_intelligence_engine import build_tournament_intelligence


class TournamentIntelligenceAgent(BaseAgent):
    """Tournament-aware context — groups, knockout rounds, qualification dynamics."""

    name = "tournament_intelligence_agent"
    domain = "tournament_intelligence_v2"

    def run(self, **kwargs: Any) -> AgentResult:
        report = require_intelligence(self.context, kwargs.get("fixture_id"))
        if report is None:
            return self._fail("No intelligence report available.")

        load_tournament_context(self.context)
        fixture_id = int(kwargs.get("fixture_id") or report.fixture_id)
        tctx = fixture_tournament_context(self.context, fixture_id)

        result = build_tournament_intelligence(report, tournament_context=tctx)
        payload = result.to_dict()

        status = "unavailable" if not result.data_available else "available"
        if result.competition_type == "league" or result.competition_type == "friendly":
            status = "partial"

        warnings: list[str] = []
        if not result.data_available:
            warnings.append("Tournament standings unavailable — adjustments remain minimal.")
        if "high_rotation_risk" in result.risk_flags:
            warnings.append("High rotation risk — lineup volatility possible (analysis only).")
        if "final_match_pressure" in result.risk_flags:
            warnings.append("Final match pressure elevated — interpret cautiously (analysis only).")
        if tctx.get("is_placeholder"):
            warnings.append("Placeholder group table — tournament context unconfirmed.")

        signal = make_signal(
            self.name,
            self.domain,
            status,
            payload,
            warnings=warnings,
            missing_data=["standings"] if not result.data_available else [],
            impact_score=round(result.pressure_score, 1),
            notes=result.summary,
        )
        self.context.shared.setdefault("specialist_signals", {})[self.name] = signal
        return self._ok(data=signal, message="Tournament Intelligence V2 complete")
