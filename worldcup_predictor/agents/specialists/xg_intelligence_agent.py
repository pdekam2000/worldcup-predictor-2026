"""Sportmonks xG Intelligence Agent — Phase 22D (benchmark only, no WDE changes)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.agents.base import AgentResult, BaseAgent
from worldcup_predictor.agents.specialists.helpers import make_signal, require_intelligence
from worldcup_predictor.intelligence.sportmonks_xg_intelligence_engine import (
    build_sportmonks_xg_intelligence,
)
from worldcup_predictor.providers.sportmonks_consumption import SPORTMONKS_XG_INTELLIGENCE_KEY


class XGIntelligenceAgent(BaseAgent):
    """
    Dedicated Sportmonks xG intelligence layer.

    Compares Sportmonks xG vs internal metrics — trace/benchmark only.
    """

    name = "xg_intelligence_agent"
    domain = "sportmonks_xg_intelligence"

    def run(self, **kwargs: Any) -> AgentResult:
        report = require_intelligence(self.context, kwargs.get("fixture_id"))
        if report is None:
            return self._fail("No intelligence report available.")

        supplemental = getattr(report, "supplemental_sources", None) or {}
        xg_block = supplemental.get(SPORTMONKS_XG_INTELLIGENCE_KEY)

        signals_map: dict[str, Any] = self.context.shared.get("specialist_signals") or {}
        xg_v2 = signals_map.get("xg_chance_quality_intelligence_agent")
        xg_v2_payload = xg_v2.signals if xg_v2 and hasattr(xg_v2, "signals") else None

        result = build_sportmonks_xg_intelligence(
            xg_block=xg_block if isinstance(xg_block, dict) else None,
            report=report,
            xg_chance_quality_signal=xg_v2_payload if isinstance(xg_v2_payload, dict) else None,
        )
        payload = result.to_dict()

        status = "unavailable" if not xg_block or not xg_block.get("available") else "available"
        if status == "available" and result.plan_support == "partial":
            status = "partial"

        warnings: list[str] = []
        if status == "unavailable":
            warnings.append(
                "Sportmonks xG not in fixture payload — verify xG add-on or wait for post-match/live window."
            )
        warnings.append(
            "Sportmonks xG is supplemental benchmark only — internal model and WDE weights unchanged."
        )
        if result.plan_support == "partial":
            warnings.append("Partial xG plan access — statistics fallback or empty xGFixture include.")
        if result.comparison_available and not result.xg_supports_internal:
            warnings.append(
                f"Sportmonks xG disagreement {result.disagreement_score:.0%} vs internal reference."
            )

        signal = make_signal(
            self.name,
            self.domain,
            status,
            {
                "home_xg": payload["home_xg"],
                "away_xg": payload["away_xg"],
                "xg_difference": payload["xg_difference"],
                "xg_total": payload["xg_total"],
                "xg_attack_rating_home": payload["xg_attack_rating_home"],
                "xg_attack_rating_away": payload["xg_attack_rating_away"],
                "xg_defense_rating_home": payload["xg_defense_rating_home"],
                "xg_defense_rating_away": payload["xg_defense_rating_away"],
                "xg_strength_rating": payload["xg_strength_rating"],
                "xg_confidence": payload["xg_confidence"],
                "rolling_xg_for_home": payload["rolling_xg_for_home"],
                "rolling_xg_for_away": payload["rolling_xg_for_away"],
                "rolling_xg_against_home": payload["rolling_xg_against_home"],
                "rolling_xg_against_away": payload["rolling_xg_against_away"],
                "xg_form_home": payload["xg_form_home"],
                "xg_form_away": payload["xg_form_away"],
                "xg_momentum_home": payload["xg_momentum_home"],
                "xg_momentum_away": payload["xg_momentum_away"],
                "expected_goal_range": payload["expected_goal_range"],
                "agreement_score": payload["agreement_score"],
                "disagreement_score": payload["disagreement_score"],
                "xg_supports_internal": payload["xg_supports_internal"],
                "xg_source": payload["xg_source"],
                "plan_support": payload["plan_support"],
                "plan_access_message": payload["plan_access_message"],
                "internal_xg_source": payload["internal_xg_source"],
                "comparison_available": payload["comparison_available"],
                "notes": payload["notes"],
                "version": payload["version"],
                "disclaimer": (
                    "Sportmonks xG benchmark — does not override scoreline, O/U, BTTS, or WDE decisions."
                ),
            },
            warnings=warnings,
            missing_data=[] if status != "unavailable" else ["sportmonks_xg"],
            impact_score=round(result.xg_confidence, 1),
            notes="; ".join(result.notes) if result.notes else "Sportmonks xG intelligence complete.",
        )
        self.context.shared.setdefault("specialist_signals", {})[self.name] = signal
        return self._ok(data=signal, message="Sportmonks xG intelligence complete")
