"""Injury & Suspension Intelligence V2 — Phase 39."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.agents.base import AgentResult, BaseAgent
from worldcup_predictor.agents.specialists.helpers import make_signal, require_intelligence
from worldcup_predictor.injuries.injury_intelligence_engine import build_injury_intelligence


class InjurySuspensionIntelligenceAgent(BaseAgent):
    """Deep injury/suspension impact analysis — API-Football data only."""

    name = "injury_suspension_intelligence_agent"
    domain = "injury_suspension_intelligence_v2"

    def run(self, **kwargs: Any) -> AgentResult:
        report = require_intelligence(self.context, kwargs.get("fixture_id"))
        if report is None:
            return self._fail("No intelligence report available.")

        result = build_injury_intelligence(report)
        payload = result.to_dict()

        has_data = result.home.data_available or result.away.data_available
        has_absences = bool(result.home.unavailable_players or result.away.unavailable_players)
        status = "unavailable" if not has_data else ("partial" if not has_absences else "available")

        warnings: list[str] = []
        if not has_data:
            warnings.append("Injury/suspension data unavailable — adjustments remain minimal.")
        if "severe_injury_crisis" in result.home.risk_flags + result.away.risk_flags:
            warnings.append("Severe injury crisis detected — treat prediction cautiously (analysis only).")
        if "key_goalkeeper_missing" in result.home.risk_flags + result.away.risk_flags:
            warnings.append("Key goalkeeper absence — goal volatility elevated (analysis only).")

        avg_impact = (result.home.injury_impact_score + result.away.injury_impact_score) / 2
        signal = make_signal(
            self.name,
            self.domain,
            status,
            payload,
            warnings=warnings,
            missing_data=["injuries"] if not has_data else [],
            impact_score=round(100.0 - avg_impact, 1),
            notes=result.summary,
        )
        self.context.shared.setdefault("specialist_signals", {})[self.name] = signal
        return self._ok(data=signal, message="Injury & Suspension Intelligence V2 complete")
