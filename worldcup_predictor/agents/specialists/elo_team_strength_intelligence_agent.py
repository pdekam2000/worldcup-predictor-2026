"""ELO & Team Strength Intelligence V2 — Phase 44."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.agents.base import AgentResult, BaseAgent
from worldcup_predictor.agents.specialists.helpers import make_signal, require_intelligence
from worldcup_predictor.strength.team_strength_intelligence_engine import build_elo_team_strength_intelligence


class EloTeamStrengthIntelligenceAgent(BaseAgent):
    """Relative team strength via ELO-style ratings, form windows, and attack/defense profiles."""

    name = "elo_team_strength_intelligence_agent"
    domain = "elo_team_strength_intelligence_v2"

    def run(self, **kwargs: Any) -> AgentResult:
        report = require_intelligence(self.context, kwargs.get("fixture_id"))
        if report is None:
            return self._fail("No intelligence report available.")

        result = build_elo_team_strength_intelligence(report)
        payload = result.to_dict()

        status = "available" if result.data_available else "partial"
        if not result.sample_size_home and not result.sample_size_away:
            status = "unavailable"

        warnings: list[str] = []
        if not result.data_available:
            warnings.append("Limited match history — strength adjustments remain minimal.")
        if report.is_placeholder:
            warnings.append("Placeholder intelligence — ELO derived from unconfirmed data only.")
        if "large_elo_gap" in result.risk_flags:
            warnings.append("Large ELO gap detected — favourite profile clear (analysis only).")
        if "form_mismatch" in result.risk_flags:
            warnings.append("Recent form diverges from ELO expectation — interpret cautiously.")
        if "unreliable_history" in result.risk_flags:
            warnings.append("Small sample size — history may not be representative.")

        impact_strength = abs(result.elo_difference) / 4.0 + (
            result.home.overall_team_strength + result.away.overall_team_strength
        ) / 20.0

        signal = make_signal(
            self.name,
            self.domain,
            status,
            payload,
            warnings=warnings,
            missing_data=["recent_fixtures"] if not result.data_available else [],
            impact_score=round(min(impact_strength, 95.0), 1),
            notes=result.summary,
        )
        self.context.shared.setdefault("specialist_signals", {})[self.name] = signal
        return self._ok(data=signal, message="ELO & Team Strength Intelligence V2 complete")
