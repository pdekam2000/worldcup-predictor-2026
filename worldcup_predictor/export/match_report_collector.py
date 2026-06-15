"""Collect prediction, explainability, fusion, and V2 intelligence for export."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.export.models import ExportLocale, MatchReportBundle
from worldcup_predictor.export.report_i18n import report_t


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _kickoff_str(prediction: MatchPrediction) -> str | None:
    if prediction.kickoff_utc is None:
        return None
    try:
        return prediction.kickoff_utc.isoformat()
    except Exception:
        return str(prediction.kickoff_utc)


def _prediction_block(prediction: MatchPrediction) -> dict[str, Any]:
    fg_v2_raw = (prediction.metadata or {}).get("first_goal_intelligence_v2")
    fg_v2: dict[str, Any] = {}
    if fg_v2_raw:
        try:
            import json

            fg_v2 = json.loads(fg_v2_raw) if isinstance(fg_v2_raw, str) else dict(fg_v2_raw)
        except Exception:
            fg_v2 = {}
    scorers = fg_v2.get("likely_scorers") or fg_v2.get("likely_first_goal_scorers") or []
    if not scorers and prediction.first_goal.scorer_candidates:
        scorers = [
            {
                "player_name": c.player,
                "team": c.team,
                "position": c.position or "",
                "confidence": c.score,
                "reason": c.reason,
            }
            for c in prediction.first_goal.scorer_candidates
        ]
    return {
        "fixture_id": prediction.fixture_id,
        "match_name": prediction.match_name,
        "competition_key": prediction.competition_key,
        "one_x_two": prediction.one_x_two.selection,
        "one_x_two_probability": prediction.one_x_two.probability,
        "one_x_two_label": prediction.one_x_two.label.get("en") if prediction.one_x_two.label else None,
        "over_under": prediction.over_under.selection,
        "over_under_probability": prediction.over_under.probability,
        "confidence_score": prediction.confidence_score,
        "confidence_level": prediction.confidence_level.value if hasattr(prediction.confidence_level, "value") else str(prediction.confidence_level),
        "risk_level": prediction.risk_level,
        "no_bet_flag": prediction.no_bet_flag,
        "scoreline": prediction.scoreline.label if prediction.scoreline else None,
        "stage": prediction.stage,
        "first_goal_team": fg_v2.get("first_goal_team_display") or prediction.first_goal.team,
        "first_goal_minute_band": fg_v2.get("first_goal_minute_band") or prediction.first_goal.minute_range,
        "first_goal_scorer_candidates": scorers,
        "first_goal_confidence": fg_v2.get("confidence"),
        "first_goal_data_available": fg_v2.get("data_available"),
        "first_goal_disclaimer": fg_v2.get("disclaimer"),
        "first_goal_data_limitations": fg_v2.get("player_data_message") or (
            "Player-level scorer data unavailable; team/minute estimate only."
            if fg_v2.get("player_data_unavailable")
            else None
        ),
    }


def _v2_from_signal(
    specialist: MatchSpecialistReport | None,
    agent_key: str,
    *,
    fallback_builder: Any | None = None,
    report: MatchIntelligenceReport | None = None,
) -> dict[str, Any]:
    if specialist:
        sig = specialist.signal(agent_key)
        if sig and sig.signals:
            return {
                "status": sig.status,
                "summary": sig.notes or "",
                "signals": dict(sig.signals),
                "warnings": list(sig.warnings or []),
            }
    if fallback_builder and report is not None:
        try:
            result = fallback_builder(report)
            data = result.to_dict() if hasattr(result, "to_dict") else result
            return {"status": "partial", "summary": data.get("summary", ""), "signals": data}
        except Exception:
            pass
    return {"status": "unavailable", "summary": "", "signals": {}}


def collect_match_report_bundle(
    prediction: MatchPrediction | None,
    *,
    report: MatchIntelligenceReport | None = None,
    specialist_report: MatchSpecialistReport | None = None,
    locale: ExportLocale = "en",
) -> MatchReportBundle:
    """Assemble report bundle from existing pipeline outputs — never raises."""
    try:
        if prediction is None:
            return MatchReportBundle(
                fixture_id=0,
                locale=locale,
                match_name="Unknown",
                kickoff_utc=None,
                stage=None,
                prediction={},
                explainability={},
                fusion={},
                disclaimer=report_t("report.disclaimer", locale),
                generated_at=_utc_now_iso(),
            )

        specialist = specialist_report
        if specialist is None and report is not None:
            specialist = report.specialist_report

        explainability: dict[str, Any] = {}
        try:
            from worldcup_predictor.explainability.prediction_explainability_engine import (
                build_prediction_explainability,
            )

            explainability = build_prediction_explainability(
                prediction, report, specialist_report=specialist
            ).to_dict()
        except Exception:
            explainability = {"executive_summary": report_t("report.unavailable", locale)}

        fusion: dict[str, Any] = explainability.get("fusion_report") or {}
        if not fusion:
            try:
                from worldcup_predictor.fusion.final_decision_fusion_engine_v2 import (
                    build_final_decision_fusion,
                    load_fusion_from_prediction,
                )

                loaded = load_fusion_from_prediction(prediction)
                fusion = (loaded or build_final_decision_fusion(
                    prediction, report=report, specialist_report=specialist
                )).to_dict()
            except Exception:
                fusion = {}

        intelligence_v2 = _build_intelligence_v2(report, specialist, prediction=prediction)
        fg_v2 = intelligence_v2.get("first_goal_intelligence_v2")
        if fg_v2 and explainability.get("executive_summary"):
            band = fg_v2.get("first_goal_minute_band", "—")
            team = fg_v2.get("first_goal_team_display", "—")
            explainability["executive_summary"] = (
                f"{explainability['executive_summary']} "
                f"First goal lean: {team} (band {band}, confidence {fg_v2.get('confidence', '—')}/100)."
            )
        if fg_v2:
            explainability["first_goal_intelligence_v2"] = fg_v2

        if report is not None:
            try:
                from worldcup_predictor.integrations.api_sports_deep_data import build_api_sports_explainability_context

                api_ctx = build_api_sports_explainability_context(report, prediction)
                if api_ctx:
                    explainability["api_sports_context"] = api_ctx
                    intelligence_v2["api_sports_deep"] = (
                        (getattr(report, "supplemental_sources", None) or {}).get("api_sports_deep") or {}
                    )
            except Exception:
                pass

        return MatchReportBundle(
            fixture_id=prediction.fixture_id,
            locale=locale,
            match_name=prediction.match_name,
            kickoff_utc=_kickoff_str(prediction),
            stage=prediction.stage,
            prediction=_prediction_block(prediction),
            explainability=explainability,
            fusion=fusion,
            intelligence_v2=intelligence_v2,
            disclaimer=report_t("report.disclaimer", locale),
            generated_at=_utc_now_iso(),
        )
    except Exception:
        fid = prediction.fixture_id if prediction else 0
        return MatchReportBundle(
            fixture_id=fid,
            locale=locale,
            match_name=getattr(prediction, "match_name", "Unknown") if prediction else "Unknown",
            kickoff_utc=None,
            stage=None,
            prediction=_prediction_block(prediction) if prediction else {},
            explainability={},
            fusion={},
            disclaimer=report_t("report.disclaimer", locale),
            generated_at=_utc_now_iso(),
        )


def _build_intelligence_v2(
    report: MatchIntelligenceReport | None,
    specialist: MatchSpecialistReport | None,
    *,
    prediction: MatchPrediction | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    builders = {
        "lineup_intelligence_v2": (
            "lineup_intelligence_agent",
            "worldcup_predictor.lineups.lineup_intelligence_engine",
            "build_lineup_intelligence",
        ),
        "injury_intelligence_v2": (
            "injury_suspension_intelligence_agent",
            "worldcup_predictor.injuries.injury_intelligence_engine",
            "build_injury_intelligence",
        ),
        "sharp_money_v2": (
            "sharp_money_intelligence_agent",
            "worldcup_predictor.odds.sharp_money_intelligence_engine",
            "build_sharp_money_intelligence",
        ),
        "tournament_v2": (
            "tournament_intelligence_agent",
            "worldcup_predictor.tournament.tournament_intelligence_engine",
            "build_tournament_intelligence",
        ),
        "elo_strength_v2": (
            "elo_team_strength_intelligence_agent",
            "worldcup_predictor.strength.team_strength_intelligence_engine",
            "build_elo_team_strength_intelligence",
        ),
        "xg_chance_quality_v2": (
            "xg_chance_quality_intelligence_agent",
            "worldcup_predictor.chance_quality.xg_chance_quality_intelligence_engine",
            "build_xg_chance_quality_intelligence",
        ),
    }
    for key, (agent_key, module_path, fn_name) in builders.items():
        fallback = None
        if report is not None:
            try:
                import importlib

                mod = importlib.import_module(module_path)
                fn = getattr(mod, fn_name)

                def _builder(r=report, f=fn):  # noqa: B023
                    return f(r)

                fallback = _builder
            except Exception:
                fallback = None
        out[key] = _v2_from_signal(specialist, agent_key, fallback_builder=fallback, report=report)
    if report is not None:
        try:
            from worldcup_predictor.intelligence.first_goal_intelligence_v2 import (
                build_first_goal_intelligence_v2,
                load_first_goal_v2_from_prediction,
            )

            fg = None
            if prediction is not None:
                fg = load_first_goal_v2_from_prediction(prediction)
            if fg is None:
                fg = build_first_goal_intelligence_v2(
                    report,
                    prediction=prediction,
                    specialist_report=specialist,
                )
            out["first_goal_intelligence_v2"] = fg.to_dict()
        except Exception:
            pass
    return out


def collect_match_report_bundle_for_fixture(
    settings: Any,
    fixture_id: int,
    *,
    competition_key: str = "world_cup_2026",
    locale: ExportLocale = "en",
) -> MatchReportBundle:
    """Run prediction pipeline and collect bundle — never raises."""
    try:
        from worldcup_predictor.agents.base import AgentContext
        from worldcup_predictor.agents.data_collector_agent import DataCollectorAgent
        from worldcup_predictor.agents.prediction_agent import PredictionAgent
        from worldcup_predictor.agents.specialists.orchestrator import SpecialistOrchestrator
        from worldcup_predictor.fusion.fusion_applier import apply_fusion_enrichment
        from worldcup_predictor.schedule.context_loader import load_tournament_context

        ctx = AgentContext(settings=settings, competition_key=competition_key, locale=locale)
        load_tournament_context(ctx)
        if not DataCollectorAgent(ctx).run(fixture_id=fixture_id).success:
            return collect_match_report_bundle(None, locale=locale)

        SpecialistOrchestrator(ctx).run(fixture_id=fixture_id)
        pred_result = PredictionAgent(ctx).run(fixture_id=fixture_id)
        if not pred_result.success or not isinstance(pred_result.data, MatchPrediction):
            return collect_match_report_bundle(None, locale=locale)

        prediction = pred_result.data
        intel = (ctx.shared.get("intelligence_reports") or {}).get(fixture_id)
        specialist = (ctx.shared.get("specialist_reports") or {}).get(fixture_id)
        try:
            from worldcup_predictor.intelligence.first_goal_intelligence_v2 import attach_first_goal_v2_to_prediction

            attach_first_goal_v2_to_prediction(prediction, intel, specialist_report=specialist)
        except Exception:
            pass
        try:
            prediction, _ = apply_fusion_enrichment(
                prediction, report=intel, specialist_report=specialist
            )
        except Exception:
            pass
        return collect_match_report_bundle(
            prediction,
            report=intel,
            specialist_report=specialist,
            locale=locale,
        )
    except Exception:
        return collect_match_report_bundle(None, locale=locale)
