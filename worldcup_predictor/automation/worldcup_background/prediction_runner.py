"""Build and persist full API prediction payloads — Phase 33."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from worldcup_predictor.config.competitions import get_competition
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline, PredictPipelineResult
from worldcup_predictor.quota.prediction_cache import kickoff_from_payload, store_prediction
from worldcup_predictor.config.provider_readiness import stamp_provider_readiness
from worldcup_predictor.automation.worldcup_background.prediction_store_guard import assert_can_run_production_prediction


def _national_block_from_intel(
    report: MatchIntelligenceReport | None,
    specialist_report: MatchSpecialistReport | None,
) -> dict[str, Any] | None:
    if report is None:
        return None
    try:
        from worldcup_predictor.intelligence.national_team.orchestrator import build_national_team_intelligence

        block = build_national_team_intelligence(report, specialist_report=specialist_report)
        if not block.get("applicable"):
            return None
        return {
            "version": block.get("version"),
            "national_form_score": block.get("national_form_score"),
            "national_h2h_score": block.get("national_h2h_score"),
            "squad_strength_score": block.get("squad_strength_score"),
            "injury_impact_score": block.get("injury_impact_score"),
            "consensus_strength_score": block.get("consensus_strength_score"),
            "data_coverage": block.get("data_coverage"),
        }
    except Exception as exc:
        from worldcup_predictor.providers.safe_enrichment_logger import log_enrichment_failure

        log_enrichment_failure(
            "worldcup_predictor.automation.worldcup_background.prediction_runner",
            exc,
            fixture_id=getattr(report, "fixture_id", None),
            layer="national_team_block",
        )
        return None


def build_api_payload(
    result: PredictPipelineResult,
    *,
    intelligence_report: MatchIntelligenceReport | None = None,
    specialist_report: MatchSpecialistReport | None = None,
) -> dict[str, Any]:
    """Reuse API success payload builder + national intel supplemental."""
    from worldcup_predictor.api.routes.predictions import _success_payload

    payload = _success_payload(result)
    nat = _national_block_from_intel(intelligence_report, specialist_report)
    if nat:
        payload["national_team_intelligence"] = nat
    payload["predicted_at"] = datetime.utcnow().isoformat() + "Z"
    payload["cache_source"] = "live"
    payload["cached_at"] = time.time()
    from worldcup_predictor.api.prediction_metadata import stamp_prediction_engine_metadata

    return stamp_prediction_engine_metadata(
        payload,
        prediction=result.prediction,
        generated_by="live",
    )


def run_and_store_prediction(
    fixture_id: int,
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
    locale: str = "en",
    record_history: bool = False,
    source: str = "background",
) -> dict[str, Any]:
    """Run full pipeline once and persist to SQLite + file cache."""
    from worldcup_predictor.automation.worldcup_background.prediction_store import WorldcupPredictionStore

    settings = settings or get_settings()
    assert_can_run_production_prediction(settings)
    comp = get_competition(competition_key)
    pipeline = PredictPipeline(settings, competition_key=competition_key, locale=locale)
    result = pipeline.run(fixture_id=fixture_id, record_history=record_history)
    if not result.success:
        return {
            "status": "error",
            "fixture_id": fixture_id,
            "message": "pipeline_failed",
        }

    payload = build_api_payload(
        result,
        intelligence_report=result.intelligence_report,
        specialist_report=result.specialist_report,
    )
    from worldcup_predictor.api.prediction_metadata import stamp_prediction_engine_metadata

    gen_by = "background_daily" if source == "background" else source
    payload = stamp_prediction_engine_metadata(payload, prediction=result.prediction, generated_by=gen_by)
    payload = stamp_provider_readiness(payload, settings=settings)
    payload["is_placeholder"] = bool(getattr(result.prediction, "is_placeholder", False))
    payload["cache_source"] = payload.get("cache_source") or gen_by
    try:
        from worldcup_predictor.automation.prediction_prefetch.smart_refresh import build_prefetch_signals

        payload["_prefetch_signals"] = build_prefetch_signals(payload)
    except Exception:
        pass
    kickoff = kickoff_from_payload(payload)
    if kickoff is None:
        try:
            from worldcup_predictor.database.repository import FootballIntelligenceRepository

            row = FootballIntelligenceRepository(settings.sqlite_path or None).get_fixture_row(fixture_id)
            if row and row.get("kickoff_utc"):
                payload["kickoff_utc"] = str(row["kickoff_utc"])
                kickoff = kickoff_from_payload(payload)
        except Exception as exc:
            from worldcup_predictor.providers.safe_enrichment_logger import log_enrichment_failure

            log_enrichment_failure(
                "worldcup_predictor.automation.worldcup_background.prediction_runner",
                exc,
                fixture_id=fixture_id,
                layer="kickoff_lookup",
            )

    store_prediction(
        fixture_id,
        payload,
        competition_key=comp.key,
        season=comp.season,
        locale=locale,
        kickoff_utc=kickoff,
        settings=settings,
        prediction_is_placeholder=bool(getattr(result.prediction, "is_placeholder", False)),
    )
    WorldcupPredictionStore(settings).upsert(
        fixture_id,
        payload,
        kickoff_utc=payload.get("kickoff_utc"),
        source=source,
        prediction_is_placeholder=bool(getattr(result.prediction, "is_placeholder", False)),
    )
    if getattr(settings, "predops_enabled", True):
        try:
            from worldcup_predictor.predops.snapshots import create_snapshot_from_payload
            from worldcup_predictor.predops.store import PredOpsStore

            create_snapshot_from_payload(
                PredOpsStore(settings),
                fixture_id=fixture_id,
                competition_key=comp.key,
                kickoff_utc=payload.get("kickoff_utc"),
                payload=payload,
                trigger_reason=source or "pipeline",
            )
        except Exception:
            pass
    return payload
