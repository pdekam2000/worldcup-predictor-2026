"""Tournament Context Agent — Phase 22E (benchmark/trace, no WDE changes)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.agents.base import AgentResult, BaseAgent
from worldcup_predictor.agents.specialists.helpers import make_signal, require_intelligence
from worldcup_predictor.intelligence.tournament_context_engine import (
    SPORTMONKS_TOURNAMENT_STANDINGS_KEY,
    build_tournament_context_intelligence,
)
from worldcup_predictor.schedule.context_loader import fixture_tournament_context, load_tournament_context


class TournamentContextAgent(BaseAgent):
    """
    Dedicated tournament context layer — standings, form, qualification scenarios.

    Compares against motivation_psychology_agent; does not override predictions.
    """

    name = "tournament_context_agent"
    domain = "tournament_context"

    def run(self, **kwargs: Any) -> AgentResult:
        report = require_intelligence(self.context, kwargs.get("fixture_id"))
        if report is None:
            return self._fail("No intelligence report available.")

        load_tournament_context(self.context)
        fixture_id = int(kwargs.get("fixture_id") or report.fixture_id)
        tctx = fixture_tournament_context(self.context, fixture_id)

        supplemental = getattr(report, "supplemental_sources", None) or {}
        sm_standings = supplemental.get(SPORTMONKS_TOURNAMENT_STANDINGS_KEY)
        signals_map: dict[str, Any] = self.context.shared.get("specialist_signals") or {}

        result = build_tournament_context_intelligence(
            report,
            tournament_context=tctx,
            sportmonks_standings=sm_standings if isinstance(sm_standings, dict) else None,
            specialist_signals=signals_map,
        )
        payload = result.to_dict()

        has_data = bool(result.data_sources)
        status = "unavailable" if not has_data else "available"
        if has_data and result.group_context_strength < 36:
            status = "partial"

        warnings: list[str] = []
        if not has_data:
            warnings.append("Tournament standings/form context unavailable — minimal benchmark.")
        warnings.append(
            "Tournament context is supplemental — internal motivation/WDE unchanged (trace only)."
        )
        if result.must_win_flag:
            warnings.append("Must-win flag set — informational only.")
        if not result.context_supports_internal and result.disagreement_score >= 0.35:
            warnings.append(
                f"Context vs motivation disagreement {result.disagreement_score:.0%} — benchmark review."
            )

        signal = make_signal(
            self.name,
            self.domain,
            status,
            {
                "group_position_home": payload["group_position_home"],
                "group_position_away": payload["group_position_away"],
                "points_home": payload["points_home"],
                "points_away": payload["points_away"],
                "goal_difference_home": payload["goal_difference_home"],
                "goal_difference_away": payload["goal_difference_away"],
                "qualification_status_home": payload["qualification_status_home"],
                "qualification_status_away": payload["qualification_status_away"],
                "qualification_probability_home": payload["qualification_probability_home"],
                "qualification_probability_away": payload["qualification_probability_away"],
                "elimination_risk_home": payload["elimination_risk_home"],
                "elimination_risk_away": payload["elimination_risk_away"],
                "must_win_flag": payload["must_win_flag"],
                "pressure_rating": payload["pressure_rating"],
                "motivation_score_home": payload["motivation_score_home"],
                "motivation_score_away": payload["motivation_score_away"],
                "recent_form_score_home": payload["recent_form_score_home"],
                "recent_form_score_away": payload["recent_form_score_away"],
                "tournament_importance": payload["tournament_importance"],
                "rotation_risk": payload["rotation_risk"],
                "group_context_strength": payload["group_context_strength"],
                "expected_conservatism": payload["expected_conservatism"],
                "expected_aggression": payload["expected_aggression"],
                "draw_acceptability": payload["draw_acceptability"],
                "likely_rotation_behavior": payload["likely_rotation_behavior"],
                "agreement_score": payload["agreement_score"],
                "disagreement_score": payload["disagreement_score"],
                "context_supports_internal": payload["context_supports_internal"],
                "match_context": payload["match_context"],
                "data_sources": payload["data_sources"],
                "notes": payload["notes"],
                "version": payload["version"],
                "disclaimer": (
                    "Tournament context benchmark — does not override scoreline, motivation weights, or WDE."
                ),
            },
            warnings=warnings,
            missing_data=[] if has_data else ["standings", "form"],
            impact_score=round(result.group_context_strength, 1),
            notes="; ".join(result.notes) if result.notes else "Tournament context intelligence complete.",
        )
        self.context.shared.setdefault("specialist_signals", {})[self.name] = signal
        return self._ok(data=signal, message="Tournament context intelligence complete")
