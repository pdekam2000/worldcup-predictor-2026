from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.clients.openai_client import OpenAIClient
from worldcup_predictor.config.settings import Locale, Settings, get_settings
from worldcup_predictor.decision.audit_report import PredictionAuditReport
from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.i18n.translator import get_translator
from worldcup_predictor.orchestration.report_pipeline import ReportPipeline
from worldcup_predictor.reasoning.report_models import ProfessionalMatchReport
from worldcup_predictor.reasoning.report_prompt_builder import (
    build_prompt_payload,
    build_system_prompt,
    build_user_prompt,
)
from worldcup_predictor.reasoning.safety_guard import apply_safety_guard

logger = logging.getLogger(__name__)

WATCH_ONLY_CONFIDENCE = 60.0
LOW_DATA_QUALITY = 0.65


def _as_str_list(value: Any, *, limit: int = 10) -> list[str]:
    """Safely coerce OpenAI JSON list/dict/str fields into a bounded string list."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value][:limit]
    if isinstance(value, dict):
        items: list[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                items.append(f"{key}: {item}")
            else:
                items.append(f"{key}: {item}")
            if len(items) >= limit:
                break
        return items
    if isinstance(value, list):
        return [str(x) for x in value[:limit]]
    return [str(value)]


class OpenAIReasoningService:
    """
    Explanation/reasoning layer on top of deterministic predictions.
    OpenAI must not invent data or override safety rules.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        openai_client: OpenAIClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._openai = openai_client or OpenAIClient(self._settings)

    def generate_for_fixture(
        self,
        fixture_id: int,
        *,
        locale: Locale = "en",
        competition: str | None = None,
    ) -> tuple[ProfessionalMatchReport, bool]:
        """Run report pipeline and build professional narrative."""
        from worldcup_predictor.config.competitions import normalize_competition_key

        comp_key = normalize_competition_key(competition)
        pipeline = ReportPipeline(self._settings, locale=locale, competition_key=comp_key)
        result = pipeline.run(fixture_id)
        if not result.success:
            report = self._build_failure_report(fixture_id, locale)
            return apply_safety_guard(report), False

        return self.generate(
            prediction=result.prediction,
            audit=result.prediction.audit_report,
            intelligence=result.intelligence,
            specialists=result.specialists,
            locale=locale,
        ), True

    def generate(
        self,
        *,
        prediction: MatchPrediction,
        audit: PredictionAuditReport | None,
        intelligence: MatchIntelligenceReport,
        specialists: MatchSpecialistReport,
        locale: Locale = "en",
    ) -> ProfessionalMatchReport:
        frozen = self._frozen_prediction_summary(prediction)
        audit_highlights = self._audit_highlights(audit)
        watch_only = prediction.no_bet_flag or prediction.confidence_score < WATCH_ONLY_CONFIDENCE

        payload = build_prompt_payload(
            prediction=prediction,
            audit=audit,
            intelligence=intelligence,
            specialists=specialists,
            locale=locale,
        )

        if self._openai.is_configured:
            raw = self._openai.complete_json(
                system_prompt=build_system_prompt(),
                user_prompt=build_user_prompt(payload),
            )
            if raw:
                report = self._from_openai_json(
                    raw,
                    prediction=prediction,
                    frozen=frozen,
                    audit_highlights=audit_highlights,
                    locale=locale,
                    watch_only=watch_only,
                )
                return apply_safety_guard(report)

        report = self._build_local_report(
            prediction=prediction,
            audit=audit,
            intelligence=intelligence,
            specialists=specialists,
            locale=locale,
            frozen=frozen,
            audit_highlights=audit_highlights,
            watch_only=watch_only,
        )
        return apply_safety_guard(report)

    def _from_openai_json(
        self,
        raw: dict[str, Any],
        *,
        prediction: MatchPrediction,
        frozen: dict[str, Any],
        audit_highlights: list[str],
        locale: str,
        watch_only: bool,
    ) -> ProfessionalMatchReport:
        translator = get_translator(locale)  # type: ignore[arg-type]
        disclaimer = raw.get("disclaimer") or translator.t("cli.report.disclaimer")
        generated_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        return ProfessionalMatchReport(
            fixture_id=prediction.fixture_id,
            match_name=prediction.match_name,
            locale=locale,
            executive_summary=str(raw.get("executive_summary", "")),
            key_factors=_as_str_list(raw.get("key_factors")),
            tactical_context=str(raw.get("tactical_context", "")),
            risk_notes=_as_str_list(raw.get("risk_notes")),
            data_limitations=_as_str_list(raw.get("data_limitations")),
            market_analysis_information_only=str(raw.get("market_analysis_information_only", "")),
            final_analytical_view=str(raw.get("final_analytical_view", "")),
            disclaimer=str(disclaimer),
            prediction_summary=frozen,
            audit_highlights=audit_highlights,
            source="openai",
            watch_only=watch_only,
            generated_at_utc=generated_at,
        )

    def _build_local_report(
        self,
        *,
        prediction: MatchPrediction,
        audit: PredictionAuditReport | None,
        intelligence: MatchIntelligenceReport,
        specialists: MatchSpecialistReport,
        locale: str,
        frozen: dict[str, Any],
        audit_highlights: list[str],
        watch_only: bool,
    ) -> ProfessionalMatchReport:
        t = get_translator(locale)  # type: ignore[arg-type]
        x2 = prediction.one_x_two.selection
        ou = prediction.over_under.selection

        if watch_only:
            executive = t.t("cli.report.local.executive_watch_only").format(
                match=prediction.match_name,
                x2=x2,
                ou=ou,
                confidence=f"{prediction.confidence_score:.0f}",
            )
        else:
            executive = t.t("cli.report.local.executive").format(
                match=prediction.match_name,
                x2=x2,
                ou=ou,
                confidence=f"{prediction.confidence_score:.0f}",
            )

        key_factors = self._local_key_factors(audit, specialists, t)
        tactical = self._local_tactical(specialists, intelligence, t)
        risk_notes = self._local_risk_notes(prediction, audit, watch_only, locale, t)
        limitations = self._local_limitations(intelligence, audit, t)
        market = self._local_market(intelligence, t)

        if watch_only:
            final_view = t.t("cli.report.local.final_watch_only")
        else:
            final_view = t.t("cli.report.local.final").format(
                x2=x2,
                ou=ou,
                ht=f"{prediction.halftime.estimated_total_goals:.1f}",
            )

        return ProfessionalMatchReport(
            fixture_id=prediction.fixture_id,
            match_name=prediction.match_name,
            locale=locale,
            executive_summary=executive,
            key_factors=key_factors,
            tactical_context=tactical,
            risk_notes=risk_notes,
            data_limitations=limitations,
            market_analysis_information_only=market,
            final_analytical_view=final_view,
            disclaimer=t.t("cli.report.disclaimer"),
            prediction_summary=frozen,
            audit_highlights=audit_highlights,
            source="local_rules",
            watch_only=watch_only,
            generated_at_utc=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        )

    def _build_failure_report(self, fixture_id: int, locale: str) -> ProfessionalMatchReport:
        t = get_translator(locale)  # type: ignore[arg-type]
        return ProfessionalMatchReport(
            fixture_id=fixture_id,
            match_name="Unknown",
            locale=locale,
            executive_summary=t.t("cli.report.pipeline_failed"),
            disclaimer=t.t("cli.report.disclaimer"),
            source="local_rules",
            watch_only=True,
        )

    @staticmethod
    def _frozen_prediction_summary(prediction: MatchPrediction) -> dict[str, Any]:
        return {
            "1X2": prediction.one_x_two.selection,
            "1X2_probability": prediction.one_x_two.probability,
            "over_under_2_5": prediction.over_under.selection,
            "over_under_probability": prediction.over_under.probability,
            "halftime_goals_estimate": prediction.halftime.estimated_total_goals,
            "first_goal_team": prediction.first_goal.team,
            "first_goal_player": prediction.first_goal.player,
            "confidence_score": prediction.confidence_score,
            "confidence_level": prediction.confidence_level.value,
            "risk_level": prediction.risk_level,
            "no_bet_flag": prediction.no_bet_flag,
        }

    @staticmethod
    def _audit_highlights(audit: PredictionAuditReport | None) -> list[str]:
        if audit is None:
            return []
        highlights: list[str] = []
        for factor in audit.supported_factors[:3]:
            highlights.append(
                f"Supported: {factor.factor_name} ({factor.contribution:+.2f})"
            )
        for conflict in audit.conflicts[:2]:
            highlights.append(f"Conflict ({conflict.severity}): {conflict.description}")
        if audit.trace and audit.trace.watch_only:
            highlights.append("Decision trace: watch only / wait for more data")
        return highlights

    @staticmethod
    def _local_key_factors(audit, specialists, t) -> list[str]:
        factors: list[str] = []
        if audit:
            for contrib in audit.supported_factors[:4]:
                factors.append(
                    t.t("cli.report.local.factor_supported").format(
                        name=contrib.factor_name,
                        contribution=f"{contrib.contribution:+.2f}",
                    )
                )
        tactics = specialists.signals.get("tactics_agent")
        if tactics and tactics.signals:
            factors.append(t.t("cli.report.local.tactics_signal"))
        if not factors:
            factors.append(t.t("cli.report.local.factor_fallback"))
        return factors

    @staticmethod
    def _local_tactical(specialists, intelligence, t) -> str:
        tactics = specialists.signals.get("tactics_agent")
        if tactics and tactics.notes:
            return tactics.notes
        home = intelligence.home_team.team_name
        away = intelligence.away_team.team_name
        return t.t("cli.report.local.tactical_fallback").format(home=home, away=away)

    @staticmethod
    def _local_risk_notes(prediction, audit, watch_only, locale, t) -> list[str]:
        notes: list[str] = []
        if watch_only:
            notes.append(t.t("cli.report.local.risk_watch_only"))
        if prediction.no_bet_flag:
            notes.append(t.t("cli.report.local.risk_no_bet"))
        for warning in prediction.risk_warnings:
            notes.append(warning.messages.get(locale))  # type: ignore[arg-type]
        if audit and audit.trace:
            notes.extend(audit.trace.no_bet_reasons[:3])
        if not notes:
            notes.append(t.t("cli.report.local.risk_fallback"))
        return notes

    @staticmethod
    def _local_limitations(intelligence, audit, t) -> list[str]:
        items: list[str] = []
        if intelligence.data_quality and intelligence.data_quality.score < LOW_DATA_QUALITY:
            items.append(
                t.t("cli.report.local.low_data_quality").format(
                    score=f"{intelligence.data_quality.score:.0%}",
                )
            )
        items.extend(intelligence.missing_data[:6])
        if audit:
            for lim in audit.limitations[:4]:
                items.append(f"{lim.field}: {lim.impact}")
        if not items:
            items.append(t.t("cli.report.local.limitations_fallback"))
        return items

    @staticmethod
    def _local_market(intelligence, t) -> str:
        if intelligence.odds and intelligence.odds.available:
            return t.t("cli.report.local.market_available")
        return t.t("cli.report.local.market_unavailable")
