"""Orchestration predict pipeline — enrichment steps with structured failure logging."""

from __future__ import annotations

from dataclasses import dataclass

from worldcup_predictor.agents.base import AgentContext, AgentResult
from worldcup_predictor.agents.data_collector_agent import DataCollectorAgent
from worldcup_predictor.agents.prediction_agent import PredictionAgent
from worldcup_predictor.agents.specialists.orchestrator import SpecialistOrchestrator
from worldcup_predictor.config.settings import Settings
from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.providers.safe_enrichment_logger import log_enrichment_failure
from worldcup_predictor.schedule.context_loader import load_tournament_context

_MODULE = "worldcup_predictor.orchestration.predict_pipeline"


@dataclass
class PredictPipelineResult:
    prediction: MatchPrediction
    agent_results: list[AgentResult]
    success: bool
    intelligence_report: MatchIntelligenceReport | None = None
    specialist_report: MatchSpecialistReport | None = None


class PredictPipeline:
    """Collect intelligence then generate prediction for a single fixture."""

    def __init__(
        self,
        settings: Settings,
        *,
        competition_key: str = "world_cup_2026",
        locale: str = "en",
    ) -> None:
        self._settings = settings
        self._competition_key = competition_key
        self._locale = locale

    def run(self, fixture_id: int, *, record_history: bool = True) -> PredictPipelineResult:
        context = AgentContext(
            settings=self._settings,
            competition_key=self._competition_key,
            locale=self._locale,
        )
        context.shared["smart_prediction_fetch"] = True
        load_tournament_context(context)
        results: list[AgentResult] = []

        collector = DataCollectorAgent(context)
        collect_result = collector.run(fixture_id=fixture_id)
        results.append(collect_result)
        if not collect_result.success:
            return PredictPipelineResult(
                prediction=_empty_prediction(fixture_id),
                agent_results=results,
                success=False,
            )

        specialist = SpecialistOrchestrator(context)
        specialist_result = specialist.run(fixture_id=fixture_id)
        results.append(specialist_result)

        predictor = PredictionAgent(context)
        predict_result = predictor.run(fixture_id=fixture_id)
        results.append(predict_result)

        if not predict_result.success or not isinstance(predict_result.data, MatchPrediction):
            return PredictPipelineResult(
                prediction=_empty_prediction(fixture_id),
                agent_results=results,
                success=False,
            )

        prediction = predict_result.data
        intel = (context.shared.get("intelligence_reports") or {}).get(fixture_id)
        specialist_report = (context.shared.get("specialist_reports") or {}).get(fixture_id)

        try:
            from worldcup_predictor.intelligence.first_goal_intelligence_v2 import attach_first_goal_v2_to_prediction

            attach_first_goal_v2_to_prediction(
                prediction,
                intel,
                specialist_report=specialist_report,
            )
        except Exception as exc:
            log_enrichment_failure(_MODULE, exc, fixture_id=fixture_id, layer="first_goal_v2")

        try:
            from worldcup_predictor.intelligence.first_goal_intelligence_v2 import (
                load_first_goal_v2_from_prediction,
            )
            from worldcup_predictor.prediction.extended_markets import attach_extended_markets_to_prediction

            fg_v2 = load_first_goal_v2_from_prediction(prediction)
            attach_extended_markets_to_prediction(
                prediction,
                intel,
                fg_v2=fg_v2,
            )
        except Exception as exc:
            log_enrichment_failure(_MODULE, exc, fixture_id=fixture_id, layer="extended_markets")

        try:
            from worldcup_predictor.fusion.fusion_applier import apply_fusion_enrichment

            prediction, _ = apply_fusion_enrichment(
                prediction,
                report=intel,
                specialist_report=specialist_report,
            )
        except Exception as exc:
            log_enrichment_failure(_MODULE, exc, fixture_id=fixture_id, layer="fusion")

        try:
            from worldcup_predictor.providers.sportmonks_xg_extraction import attach_sportmonks_xg_to_prediction

            attach_sportmonks_xg_to_prediction(prediction, intel, settings=self._settings)
        except Exception as exc:
            log_enrichment_failure(_MODULE, exc, fixture_id=fixture_id, layer="sportmonks_xg")

        try:
            from worldcup_predictor.providers.weather_extraction import attach_weather_to_prediction

            attach_weather_to_prediction(prediction, intel, settings=self._settings)
        except Exception as exc:
            log_enrichment_failure(_MODULE, exc, fixture_id=fixture_id, layer="weather")

        if record_history:
            try:
                from worldcup_predictor.accuracy.service import record_match_prediction

                hist_record = record_match_prediction(prediction, prediction_version="manual")
                try:
                    from worldcup_predictor.learning.learning_capture import capture_learning_record

                    capture_learning_record(
                        prediction,
                        competition_key=self._competition_key,
                        prediction_id=hist_record.prediction_id,
                        specialist_report=specialist_report,
                    )
                except Exception as exc:
                    log_enrichment_failure(
                        _MODULE,
                        exc,
                        fixture_id=fixture_id,
                        layer="learning_capture",
                    )
            except OSError as exc:
                log_enrichment_failure(_MODULE, exc, fixture_id=fixture_id, layer="history_jsonl")

        return PredictPipelineResult(
            prediction=prediction,
            agent_results=results,
            success=True,
            intelligence_report=intel if isinstance(intel, MatchIntelligenceReport) else None,
            specialist_report=specialist_report if isinstance(specialist_report, MatchSpecialistReport) else None,
        )


def _empty_prediction(fixture_id: int) -> MatchPrediction:
    from worldcup_predictor.domain.prediction import (
        ConfidenceLevel,
        FirstGoalPrediction,
        HalftimePrediction,
        MarketPrediction,
        PredictionConfidenceBreakdown,
    )

    return MatchPrediction(
        fixture_id=fixture_id,
        competition_key="world_cup_2026",
        match_name="Unknown",
        one_x_two=MarketPrediction(market="1x2", selection="draw"),
        over_under=MarketPrediction(market="over_under_2_5", selection="under_2_5"),
        halftime=HalftimePrediction(estimated_total_goals=0.0),
        first_goal=FirstGoalPrediction(team="Unknown"),
        confidence_score=0.0,
        confidence_level=ConfidenceLevel.UNAVAILABLE,
        confidence_breakdown=PredictionConfidenceBreakdown(
            form_score=0,
            h2h_score=0,
            injuries_score=0,
            lineups_score=0,
            odds_score=0,
            data_quality_score=0,
            total=0,
        ),
        risk_level="high",
        no_bet_flag=True,
    )
