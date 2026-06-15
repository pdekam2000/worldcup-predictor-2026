from __future__ import annotations

from typing import Any

from worldcup_predictor.agents.base import AgentResult, BaseAgent
from worldcup_predictor.clients.openai_client import OpenAIClient
from worldcup_predictor.domain.fixture import FixtureCollection
from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.domain.prediction import (
    ConfidenceLevel,
    MatchPrediction,
    MultilingualText,
    PredictionPlaceholder,
    RiskProfile,
)
from worldcup_predictor.i18n.translator import Translator
from worldcup_predictor.prediction.scoring_engine import ScoringEngine
from worldcup_predictor.schedule.context_loader import fixture_tournament_context


class PredictionAgent(BaseAgent):
    """
    Phase 3 prediction agent.

    Converts MatchIntelligenceReport into structured MatchPrediction via ScoringEngine.
    Optionally enriches explanation with OpenAI; falls back to rule-based text.
    """

    name = "prediction_agent"

    def __init__(
        self,
        context,
        openai_client: OpenAIClient | None = None,
        translator: Translator | None = None,
        scoring_engine: ScoringEngine | None = None,
    ) -> None:
        super().__init__(context)
        self._openai = openai_client or OpenAIClient(context.settings)
        self._translator = translator or Translator()
        self._engine = scoring_engine or ScoringEngine()

    def run(self, **kwargs: Any) -> AgentResult:
        fixture_id = kwargs.get("fixture_id")
        intelligence_reports: dict[int, MatchIntelligenceReport] = (
            self.context.shared.get("intelligence_reports") or {}
        )

        if fixture_id is not None and int(fixture_id) not in intelligence_reports:
            return self._fail(
                f"No intelligence report for fixture {fixture_id}. Run DataCollectorAgent first."
            )

        if fixture_id is not None:
            report = intelligence_reports[int(fixture_id)]
            prediction = self._predict_from_report(report)
            self.context.shared.setdefault("match_predictions", {})[prediction.fixture_id] = prediction
            self.context.shared["predictions"] = [self._to_placeholder(prediction)]
            return self._ok(
                data=prediction,
                message=f"Generated prediction for fixture {fixture_id}",
            )

        collection: FixtureCollection | None = self.context.shared.get("fixtures")
        if not intelligence_reports and collection is None:
            return self._fail("No fixtures or intelligence reports in context.")

        reports: list[MatchIntelligenceReport] = []
        if intelligence_reports:
            if collection:
                reports = [
                    intelligence_reports[f.id]
                    for f in collection.fixtures
                    if f.id in intelligence_reports
                ]
            else:
                reports = list(intelligence_reports.values())
        elif collection:
            return self._fail("No intelligence reports in context. Run DataCollectorAgent first.")

        match_predictions: dict[int, MatchPrediction] = {}
        placeholders: list[PredictionPlaceholder] = []

        for report in reports:
            prediction = self._predict_from_report(report)
            match_predictions[prediction.fixture_id] = prediction
            placeholders.append(self._to_placeholder(prediction))

        self.context.shared["match_predictions"] = match_predictions
        self.context.shared["predictions"] = placeholders
        return self._ok(
            data=match_predictions,
            message=f"Generated {len(match_predictions)} predictions",
        )

    def _predict_from_report(self, report: MatchIntelligenceReport) -> MatchPrediction:
        specialist_reports = self.context.shared.get("specialist_reports") or {}
        specialist = specialist_reports.get(report.fixture_id) or report.specialist_report
        prediction = self._engine.predict(
            report,
            specialist_report=specialist,
            text_builder=self._text_builder,
        )
        prediction = self._apply_labels(prediction, report)
        prediction.explanation = self._resolve_explanation(prediction, report)
        prediction.disclaimer = self._text_builder("predict.analytical_disclaimer", None)
        return prediction

    def _apply_labels(self, prediction: MatchPrediction, report: MatchIntelligenceReport) -> MatchPrediction:
        home = report.home_team.team_name
        away = report.away_team.team_name
        selection = prediction.one_x_two.selection
        team_name = home if selection == "home_win" else away if selection == "away_win" else ""
        prediction.one_x_two.label = self._text_builder(
            f"predict.selection.{selection}",
            {"team": team_name, "home": home, "away": away},
        )
        prediction.over_under.label = self._text_builder(
            f"predict.selection.{prediction.over_under.selection}",
            None,
        )
        if prediction.halftime.note is None:
            prediction.halftime.note = self._text_builder(
                "predict.halftime_note",
                {"goals": prediction.halftime.estimated_total_goals},
            )
        return prediction

    def _text_builder(self, key: str, params: dict[str, Any] | None) -> MultilingualText:
        return MultilingualText(
            en=self._format(key, "en", params),
            de=self._format(key, "de", params),
            fa=self._format(key, "fa", params),
        )

    def _format(self, key: str, locale: str, params: dict[str, Any] | None) -> str:
        template = self._translator.t(key, locale)  # type: ignore[arg-type]
        if params:
            try:
                return template.format(**params)
            except KeyError:
                return template
        return template

    def _resolve_explanation(
        self,
        prediction: MatchPrediction,
        report: MatchIntelligenceReport,
    ) -> MultilingualText:
        prompt = (
            f"Match: {prediction.match_name}. "
            f"1X2: {prediction.one_x_two.selection}. "
            f"O/U 2.5: {prediction.over_under.selection}. "
            f"Confidence: {prediction.confidence_score}. "
            "Write a brief analytical summary. Do not guarantee outcomes or recommend betting."
        )
        tctx = fixture_tournament_context(self.context, prediction.fixture_id)
        if tctx:
            prompt += (
                f" Tournament context: group {tctx.get('group')}, "
                f"importance {tctx.get('match_importance')}, "
                f"home status {tctx.get('home_qualification_status')}, "
                f"away status {tctx.get('away_qualification_status')}."
            )
        ai_text = self._openai.generate_multilingual_summary(prompt)
        if ai_text:
            return ai_text

        return MultilingualText(
            en=self._format("predict.explanation.template", "en", self._explanation_params(prediction, report, "en")),
            de=self._format("predict.explanation.template", "de", self._explanation_params(prediction, report, "de")),
            fa=self._format("predict.explanation.template", "fa", self._explanation_params(prediction, report, "fa")),
        )

    def _tournament_explanation_addon(self, fixture_id: int, locale: str) -> str:
        tctx = fixture_tournament_context(self.context, fixture_id)
        if not tctx:
            return ""
        home_status = self._format(
            f"schedule.qualification.{tctx.get('home_qualification_status', 'unknown')}",
            locale,
            None,
        )
        away_status = self._format(
            f"schedule.qualification.{tctx.get('away_qualification_status', 'unknown')}",
            locale,
            None,
        )
        importance = self._format(
            f"schedule.importance.{tctx.get('match_importance', 'standard')}",
            locale,
            None,
        )
        rotation_note = ""
        statuses = {
            str(tctx.get("home_qualification_status", "")),
            str(tctx.get("away_qualification_status", "")),
        }
        if "rotation_risk" in statuses or "likely_qualified" in statuses:
            rotation_note = self._format("predict.explanation.rotation_risk_note", locale, None)
        placeholder_note = ""
        if tctx.get("is_placeholder"):
            placeholder_note = self._format("predict.explanation.placeholder_table_note", locale, None)
        return self._format(
            "predict.explanation.tournament_addon",
            locale,
            {
                "group": tctx.get("group", "TBD"),
                "importance": importance,
                "home_status": home_status,
                "away_status": away_status,
                "rotation_note": rotation_note,
                "placeholder_note": placeholder_note,
            },
        )

    def _explanation_params(
        self,
        prediction: MatchPrediction,
        report: MatchIntelligenceReport,
        locale: str,
    ) -> dict[str, Any]:
        team_name = (
            report.home_team.team_name
            if prediction.one_x_two.selection == "home_win"
            else report.away_team.team_name
            if prediction.one_x_two.selection == "away_win"
            else ""
        )
        params = {
            "match": prediction.match_name,
            "one_x_two": self._format(
                f"predict.selection.{prediction.one_x_two.selection}",
                locale,
                {"team": team_name, "home": report.home_team.team_name, "away": report.away_team.team_name},
            ),
            "over_under": self._format(
                f"predict.selection.{prediction.over_under.selection}",
                locale,
                None,
            ),
            "confidence": f"{prediction.confidence_score:.0f}",
            "risk": prediction.risk_level,
            "tournament_context": self._tournament_explanation_addon(prediction.fixture_id, locale),
        }
        return params

    def _to_placeholder(self, prediction: MatchPrediction) -> PredictionPlaceholder:
        risk = RiskProfile(
            risk_level="high" if prediction.risk_level == "high" else "medium",
            warnings=prediction.risk_warnings[0].messages if prediction.risk_warnings else MultilingualText.uniform(""),
            disclaimer=prediction.disclaimer or self._text_builder("predict.analytical_disclaimer", None),
        )
        level = prediction.confidence_level
        note_key = {
            ConfidenceLevel.UNAVAILABLE: "confidence.unavailable",
            ConfidenceLevel.LOW: "confidence.low",
            ConfidenceLevel.MEDIUM: "confidence.medium",
            ConfidenceLevel.HIGH: "confidence.high",
        }[level]

        return PredictionPlaceholder(
            fixture_id=prediction.fixture_id,
            competition_key=prediction.competition_key,
            confidence_score=prediction.confidence_score,
            confidence_level=level,
            confidence_note=self._text_builder(note_key, None),
            risk=risk,
            summary=prediction.explanation,
            data_collected=not prediction.is_placeholder,
            model_ready=True,
            metadata={
                "phase": "5" if prediction.audit_report else "3",
                "no_bet_flag": str(prediction.no_bet_flag),
                "one_x_two": prediction.one_x_two.selection,
                "watch_only": prediction.metadata.get("watch_only", "False"),
            },
        )
