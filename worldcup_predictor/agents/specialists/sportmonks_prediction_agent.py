"""Sportmonks odds + prediction benchmark agent — Phase 22C (no override authority)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.agents.base import AgentResult, BaseAgent
from worldcup_predictor.agents.specialists.helpers import make_signal, require_intelligence
from worldcup_predictor.intelligence.sportmonks_odds_prediction_engine import (
    build_sportmonks_prediction_intelligence,
)
from worldcup_predictor.providers.sportmonks_consumption import (
    SPORTMONKS_ODDS_PREDICTION_KEY,
    SPORTMONKS_SUPPLEMENTAL_KEY,
)


class SportmonksPredictionAgent(BaseAgent):
    """
    External Sportmonks odds + prediction benchmark.

    Never overrides internal predictions — consensus/conflict signals only.
    """

    name = "sportmonks_prediction_agent"
    domain = "sportmonks_prediction_benchmark"

    def run(self, **kwargs: Any) -> AgentResult:
        report = require_intelligence(self.context, kwargs.get("fixture_id"))
        if report is None:
            return self._fail("No intelligence report available.")

        supplemental = getattr(report, "supplemental_sources", None) or {}
        odds_prediction_block = supplemental.get(SPORTMONKS_ODDS_PREDICTION_KEY)
        sm_block = supplemental.get(SPORTMONKS_SUPPLEMENTAL_KEY) if isinstance(
            supplemental.get(SPORTMONKS_SUPPLEMENTAL_KEY), dict
        ) else {}
        premium_access = sm_block.get("premium_access") if isinstance(sm_block, dict) else None

        signals_map: dict[str, Any] = self.context.shared.get("specialist_signals") or {}
        result = build_sportmonks_prediction_intelligence(
            odds_prediction_block=odds_prediction_block if isinstance(odds_prediction_block, dict) else None,
            specialist_signals=signals_map,
        )
        payload = result.to_dict()

        has_data = result.sportmonks_odds_available or result.sportmonks_prediction_available
        status = "unavailable" if not has_data else "available"

        status_reason = None
        if not has_data and isinstance(premium_access, dict):
            if premium_access.get("premium_predictions_access_denied") or premium_access.get(
                "premium_odds_access_denied"
            ):
                from worldcup_predictor.agents.specialists.status_reasons import (
                    SPORTMONKS_PLAN_NO_PREDICTIONS_ACCESS,
                )

                status_reason = SPORTMONKS_PLAN_NO_PREDICTIONS_ACCESS

        warnings: list[str] = []
        if not has_data:
            warnings.append(
                "Sportmonks odds/prediction not in fixture payload — enable includes or wait for cache refresh."
            )
        warnings.append(
            "Sportmonks signals are benchmark-only — internal model and Master Decision Engine remain authoritative."
        )
        if result.conflict_level == "high":
            warnings.append("High Sportmonks vs internal disagreement — analytical review recommended.")
        if result.recommendation == "no_bet_review":
            warnings.append("Elevated uncertainty flag (no_bet_review) — trace only, not auto no-bet.")

        signal = make_signal(
            self.name,
            self.domain,
            status,
            {
                "sportmonks_home_probability": payload["sportmonks_home_probability"],
                "sportmonks_draw_probability": payload["sportmonks_draw_probability"],
                "sportmonks_away_probability": payload["sportmonks_away_probability"],
                "sportmonks_expected_score": payload["sportmonks_expected_score"],
                "sportmonks_confidence": payload["sportmonks_confidence"],
                "disagreement_vs_internal": payload["disagreement_vs_internal"],
                "consensus_with_internal": payload["consensus_with_internal"],
                "conflict_level": payload["conflict_level"],
                "recommendation": payload["recommendation"],
                "sportmonks_odds_available": payload["sportmonks_odds_available"],
                "sportmonks_prediction_available": payload["sportmonks_prediction_available"],
                "odds_vs_api_football_disagreement": payload["odds_vs_api_football_disagreement"],
                "internal_reference_source": payload["internal_reference_source"],
                "internal_lean": payload["internal_lean"],
                "sportmonks_lean": payload["sportmonks_lean"],
                "raw_odds": payload["raw_odds"],
                "raw_predictions": payload["raw_predictions"],
                "notes": payload["notes"],
                "version": payload["version"],
                "disclaimer": (
                    "External Sportmonks benchmark — not a betting recommendation and "
                    "never overrides production predictions."
                ),
            },
            warnings=warnings,
            missing_data=[] if has_data else ["sportmonks_odds", "sportmonks_predictions"],
            impact_score=round(result.consensus_with_internal, 1),
            notes="; ".join(result.notes) if result.notes else "Sportmonks benchmark intelligence complete.",
            status_reason=status_reason,
        )
        self.context.shared.setdefault("specialist_signals", {})[self.name] = signal
        return self._ok(data=signal, message="Sportmonks odds + prediction benchmark complete")
