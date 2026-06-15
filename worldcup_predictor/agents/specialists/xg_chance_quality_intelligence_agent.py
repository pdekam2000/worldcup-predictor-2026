"""xG & Chance Quality Intelligence V2 — Phase 45."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.agents.base import AgentResult, BaseAgent
from worldcup_predictor.agents.specialists.helpers import make_signal, require_intelligence
from worldcup_predictor.chance_quality.xg_chance_quality_intelligence_engine import (
    build_xg_chance_quality_intelligence,
)


class XGChanceQualityIntelligenceAgent(BaseAgent):
    """Chance quality via real xG (when available) and shooting statistics."""

    name = "xg_chance_quality_intelligence_agent"
    domain = "xg_chance_quality_intelligence_v2"

    def run(self, **kwargs: Any) -> AgentResult:
        report = require_intelligence(self.context, kwargs.get("fixture_id"))
        if report is None:
            return self._fail("No intelligence report available.")

        result = build_xg_chance_quality_intelligence(report)
        payload = result.to_dict()

        if result.chance_quality_available:
            status = "available" if result.xg_available else "partial"
        else:
            status = "unavailable"

        warnings: list[str] = []
        if not result.xg_available:
            warnings.append("Real xG unavailable — using shot-based chance quality fallback only.")
        if not result.chance_quality_available:
            warnings.append("Limited shooting statistics — adjustments remain minimal.")
        if report.is_placeholder:
            warnings.append("Placeholder intelligence — statistics may be unconfirmed.")
        if "defensive_leak" in result.risk_flags:
            warnings.append("Defensive leak detected — goal volatility possible (analysis only).")
        if "unsustainable_finishing" in result.risk_flags:
            warnings.append("Unsustainably clinical finishing — regression risk noted.")
        if "low_xg_data_confidence" in result.risk_flags:
            warnings.append("Low xG data confidence — minimal xG weight applied.")

        impact_strength = result.goals_pressure_score * 0.4 + abs(result.home_chance_edge) * 0.3

        signal = make_signal(
            self.name,
            self.domain,
            status,
            payload,
            warnings=warnings,
            missing_data=["xg"] if not result.xg_available else [],
            impact_score=round(min(impact_strength, 95.0), 1),
            notes=result.summary,
        )
        self.context.shared.setdefault("specialist_signals", {})[self.name] = signal
        return self._ok(data=signal, message="xG & Chance Quality Intelligence V2 complete")
