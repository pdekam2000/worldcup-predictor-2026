"""Prediction endpoints — thin wrappers over PredictPipeline."""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from worldcup_predictor.api.audit_trace_helpers import build_audit_trace
from worldcup_predictor.api.display_helpers import enrich_prediction_payload
from worldcup_predictor.api.prediction_output import build_prediction_output
from worldcup_predictor.providers.sportmonks_xg_extraction import load_sportmonks_xg_from_prediction
from worldcup_predictor.providers.weather_extraction import load_weather_from_prediction
from worldcup_predictor.providers.safe_enrichment_logger import log_enrichment_failure
from worldcup_predictor.api.deps import get_optional_current_user
from worldcup_predictor.api.web_auth import WebAuthUser

from worldcup_predictor.config.competitions import DEFAULT_COMPETITION_KEY, get_competition
from worldcup_predictor.config.settings import Locale, get_settings
from worldcup_predictor.database.postgres.enums import Prediction1x2, PredictionResult
from worldcup_predictor.database.saas_factory import saas_uow
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline, PredictPipelineResult
from worldcup_predictor.quota.prediction_cache import get_cached_prediction, kickoff_from_payload, store_prediction
from worldcup_predictor.quota.quota_guard import (
    QuotaGuardError,
    assert_force_refresh_allowed,
    check_daily_live_budget,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["predictions"])

_WRONG_ENDPOINT_MSG = (
    "Wrong path: use GET or POST /api/predict/{fixture_id} — not /api/predictions/{fixture_id}."
)


@router.get("/predictions/{fixture_id}")
@router.post("/predictions/{fixture_id}")
def wrong_predictions_endpoint(fixture_id: int) -> None:
    """Fast 404 for common typo — avoids hanging clients on non-existent route."""
    raise HTTPException(
        status_code=404,
        detail={
            "status": "error",
            "code": "wrong_endpoint",
            "message": _WRONG_ENDPOINT_MSG,
            "fixture_id": fixture_id,
            "correct_path": f"/api/predict/{fixture_id}",
        },
    )

_SELECTION_TO_API = {
    "home_win": "home",
    "draw": "draw",
    "away_win": "away",
}


def _split_teams(match_name: str) -> tuple[str, str]:
    if " vs " in match_name:
        home, away = match_name.split(" vs ", 1)
        return home.strip(), away.strip()
    return match_name.strip(), "Unknown"


def _map_prediction_selection(selection: str) -> str:
    return _SELECTION_TO_API.get(selection, selection)


def _extract_probabilities(prediction: MatchPrediction) -> dict[str, Any]:
    """Backward-compatible wrapper — delegates to Phase 30A output builder."""
    block = build_prediction_output(prediction)
    return block["probabilities"]


def _data_quality_score(prediction: MatchPrediction) -> float:
    if prediction.confidence_breakdown is not None:
        return float(prediction.confidence_breakdown.data_quality_score)
    raw = (prediction.metadata or {}).get("data_quality_pct")
    if raw is not None:
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass
    return float(prediction.prediction_quality_score or 0.0)


def _specialist_summary(
    result: PredictPipelineResult,
    prediction: MatchPrediction,
) -> dict[str, Any]:
    report: MatchSpecialistReport | None = None
    for agent_result in result.agent_results:
        if agent_result.agent_name == "specialist_orchestrator" and isinstance(
            agent_result.data, MatchSpecialistReport
        ):
            report = agent_result.data
            break

    if report is not None:
        agents: dict[str, Any] = {}
        for name, signal in report.signals.items():
            agents[name] = {
                "domain": signal.domain,
                "status": signal.status,
                "status_reason": signal.status_reason,
                "impact_score": signal.impact_score,
            }
        return {
            "aggregated_score": report.aggregated_signal_score,
            "source": report.source,
            "agents": agents,
        }

    score = (prediction.metadata or {}).get("specialist_score")
    if score:
        try:
            return {"aggregated_score": float(score)}
        except (TypeError, ValueError):
            return {"aggregated_score": score}
    return {}


def _sportmonks_xg_block(prediction: MatchPrediction) -> dict[str, Any]:
    loaded = load_sportmonks_xg_from_prediction(prediction)
    if loaded is not None:
        return loaded
    try:
        from worldcup_predictor.database.repository import FootballIntelligenceRepository
        from worldcup_predictor.providers.sportmonks_xg_extraction import (
            build_sportmonks_xg_api_block,
            extract_fixture_xg_match,
        )

        row = FootballIntelligenceRepository().get_fixture_row(prediction.fixture_id)
        if not row:
            return {"available": False, "source": "sportmonks", "data_source": "none"}
        extraction = extract_fixture_xg_match(
            api_fixture_id=prediction.fixture_id,
            home_team=str(row.get("home_team") or ""),
            away_team=str(row.get("away_team") or ""),
            kickoff_date=str(row.get("kickoff_utc") or "")[:10] or None,
        )
        return build_sportmonks_xg_api_block(extraction.parsed)
    except Exception:
        return {"available": False, "source": "sportmonks", "data_source": "none"}


def _weather_intelligence_block(prediction: MatchPrediction) -> dict[str, Any]:
    loaded = load_weather_from_prediction(prediction)
    if loaded is not None:
        return loaded
    return {
        "available": False,
        "source": "none",
        "data_source": "none",
        "weather_summary": None,
        "weather_impact_score": None,
        "weather_risk_level": None,
    }


def _success_payload(result: PredictPipelineResult) -> dict[str, Any]:
    from worldcup_predictor.api.prediction_metadata import stamp_prediction_engine_metadata

    prediction = result.prediction
    home_team, away_team = _split_teams(prediction.match_name)
    specialist_summary = _specialist_summary(result, prediction)
    output_block = build_prediction_output(prediction, specialist_summary=specialist_summary)
    payload = {
        "status": "ok",
        "fixture_id": prediction.fixture_id,
        "home_team": home_team,
        "away_team": away_team,
        "prediction": _map_prediction_selection(prediction.one_x_two.selection),
        "confidence": prediction.confidence_score,
        "probabilities": output_block["probabilities"],
        "recommended_bets": output_block["recommended_bets"],
        "detailed_markets": output_block["detailed_markets"],
        "primary_recommendation": output_block["primary_recommendation"],
        "market_ranking": output_block.get("market_ranking") or [],
        "safe_pick": output_block.get("safe_pick"),
        "value_pick": output_block.get("value_pick"),
        "aggressive_pick": output_block.get("aggressive_pick"),
        "caution_pick": output_block.get("caution_pick"),
        "best_available_pick": output_block.get("best_available_pick"),
        "user_visible_pick": output_block.get("user_visible_pick"),
        "pick_tier": output_block.get("pick_tier"),
        "caution_reason": output_block.get("caution_reason"),
        "confidence_gap_to_threshold": output_block.get("confidence_gap_to_threshold"),
        "accuracy_tracking": output_block.get("accuracy_tracking"),
        "risk_level": output_block["risk_level"],
        "no_bet": output_block["no_bet"],
        "specialist_summary": specialist_summary,
        "audit_trace": build_audit_trace(prediction, specialist_summary),
        "data_quality": _data_quality_score(prediction),
        "sportmonks_xg": _sportmonks_xg_block(prediction),
        "weather_intelligence": _weather_intelligence_block(prediction),
    }
    return stamp_prediction_engine_metadata(payload, prediction=prediction, generated_by="live")


def _failure_payload(fixture_id: int, result: PredictPipelineResult) -> dict[str, Any]:
    errors = [
        {
            "agent": agent_result.agent_name,
            "message": agent_result.message,
            "errors": list(agent_result.errors),
        }
        for agent_result in result.agent_results
        if not agent_result.success
    ]
    if not errors:
        errors = [{"agent": "predict_pipeline", "message": "Prediction failed.", "errors": []}]
    return {
        "status": "error",
        "fixture_id": fixture_id,
        "message": "Prediction pipeline failed.",
        "errors": errors,
    }


def _kickoff_for_fixture(fixture_id: int):
    try:
        from datetime import datetime

        from worldcup_predictor.database.repository import FootballIntelligenceRepository

        row = FootballIntelligenceRepository().get_fixture_row(fixture_id)
        if row and row.get("kickoff_utc"):
            return datetime.fromisoformat(str(row["kickoff_utc"]).replace("Z", "+00:00"))
    except Exception as exc:
        log_enrichment_failure(
            "worldcup_predictor.api.routes.predictions",
            exc,
            fixture_id=fixture_id,
            layer="kickoff_lookup",
        )
    return None


def _record_user_history(user: WebAuthUser | None, payload: dict[str, Any]) -> None:
    if user is None or payload.get("status") != "ok":
        return
    try:
        import uuid
        from decimal import Decimal

        pick = Prediction1x2(payload.get("prediction", "home"))
        with saas_uow() as uow:
            uow.prediction_history.add(
                uuid.UUID(user.id),
                fixture_id=int(payload["fixture_id"]),
                home_team=str(payload.get("home_team", "")),
                away_team=str(payload.get("away_team", "")),
                prediction_1x2=pick,
                confidence=Decimal(str(payload["confidence"])) if payload.get("confidence") is not None else None,
                result=PredictionResult.PENDING,
            )
    except Exception:
        logger.exception("Failed to record user prediction history for fixture %s", payload.get("fixture_id"))


def _resolve_competition(competition: str, season: int | None):
    try:
        comp = get_competition(competition)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if season is not None:
        comp = replace(comp, season=season)
    return comp


def _predops_snapshot_as_cached(fixture_id: int) -> dict[str, Any] | None:
    """Read-only fallback: serve latest immutable PredOps payload when predict cache misses."""
    try:
        from worldcup_predictor.predops.store import PredOpsStore

        snap = PredOpsStore().get_latest_snapshot(int(fixture_id))
        if not snap:
            return None
        payload = snap.get("payload")
        if not isinstance(payload, dict) or not payload:
            return None
        out = dict(payload)
        out.setdefault("fixture_id", int(fixture_id))
        if snap.get("competition_key"):
            out.setdefault("competition_key", snap["competition_key"])
        out["cache_source"] = "predops_snapshot"
        out["snapshot_id"] = snap.get("snapshot_id")
        markets_doc = snap.get("markets")
        if isinstance(markets_doc, dict):
            overlay = markets_doc.get("publication_overlay")
            if isinstance(overlay, dict) and "publication_overlay" not in out:
                out["publication_overlay"] = overlay
        return out
    except Exception:
        return None


def _cache_lookup(
    fixture_id: int,
    *,
    competition_key: str,
    season: int,
    locale: Locale,
) -> dict[str, Any] | None:
    try:
        from worldcup_predictor.automation.worldcup_background.prediction_store import WorldcupPredictionStore

        cached = WorldcupPredictionStore().get(
            fixture_id,
            competition_key=competition_key,
            season=season,
            locale=locale,
        )
    except Exception:
        cached = get_cached_prediction(
            fixture_id,
            competition_key=competition_key,
            season=season,
            locale=locale,
        )
    if cached is None:
        cached = _predops_snapshot_as_cached(fixture_id)
    if cached is None:
        return None
    if "audit_trace" not in cached:
        cached["audit_trace"] = build_audit_trace(
            None,
            cached.get("specialist_summary") if isinstance(cached.get("specialist_summary"), dict) else None,
        )
    return cached


@router.get("/predict/{fixture_id}")
def get_cached_prediction_endpoint(
    fixture_id: int,
    competition: str = Query(default=DEFAULT_COMPETITION_KEY, description="Competition registry key"),
    season: int | None = Query(default=None, description="Season year override"),
    locale: Locale = Query(default="en", description="Output locale"),
    user: WebAuthUser | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    """Return a cached prediction payload when fresh; does not run the pipeline."""
    comp = _resolve_competition(competition, season)
    cached = _cache_lookup(
        fixture_id,
        competition_key=comp.key,
        season=comp.season,
        locale=locale,
    )
    if cached is None:
        raise HTTPException(
            status_code=404,
            detail={
                "status": "not_cached",
                "fixture_id": fixture_id,
                "message": "No fresh cached prediction. Use Run Prediction to generate one.",
            },
        )
    return enrich_prediction_payload(
        cached,
        competition_key=comp.key,
        season=comp.season,
        user_id=user.id if user else None,
        role=user.role if user else None,
    )


@router.post("/predict/{fixture_id}")
def predict_fixture(
    fixture_id: int,
    competition: str = Query(default=DEFAULT_COMPETITION_KEY, description="Competition registry key"),
    season: int | None = Query(default=None, description="Season year override"),
    locale: Locale = Query(default="en", description="Output locale"),
    force_refresh: bool = Query(default=False, description="Bypass prediction cache (admin or cooldown)"),
    user: WebAuthUser | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    """
    Run the full prediction pipeline for one fixture when cache is stale or missing.

    Returns cached result when fresh unless ``force_refresh=true``.
    """
    comp = _resolve_competition(competition, season)
    settings = get_settings()
    is_admin = user is not None and user.role in ("admin", "super_admin")

    if user is not None:
        from worldcup_predictor.api.deps import assert_prediction_access

        assert_prediction_access(user)

    if not force_refresh:
        cached = _cache_lookup(
            fixture_id,
            competition_key=comp.key,
            season=comp.season,
            locale=locale,
        )
        if cached is not None:
            return enrich_prediction_payload(
                cached,
                competition_key=comp.key,
                season=comp.season,
                user_id=user.id if user else None,
                role=user.role if user else None,
            )

    # Phase 34 — subscription quota (pipeline runs only; cache reuse exempt)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail={
                "status": "error",
                "code": "auth_required",
                "message": "Sign in to run a new prediction. Cached predictions may be viewed when available.",
            },
        )
    try:
        from worldcup_predictor.subscription.quota_service import assert_prediction_allowed

        assert_prediction_allowed(user.id, role=user.role, fixture_id=fixture_id)
    except Exception as exc:
        from worldcup_predictor.subscription.quota_service import SubscriptionQuotaError

        if isinstance(exc, SubscriptionQuotaError):
            raise HTTPException(
                status_code=402,
                detail={
                    "status": "error",
                    "code": exc.code,
                    "message": str(exc),
                    "limit": exc.limit,
                    "used": exc.used,
                    "upgrade_url": "/subscription",
                },
            ) from exc
        raise

    try:
        if force_refresh:
            assert_force_refresh_allowed(
                fixture_id,
                user_id=user.id if user else None,
                is_admin=is_admin,
                settings=settings,
            )
        check_daily_live_budget(settings=settings)
    except QuotaGuardError as exc:
        raise HTTPException(
            status_code=429,
            detail={
                "status": "error",
                "fixture_id": fixture_id,
                "message": str(exc),
                "code": exc.code,
            },
        ) from exc

    try:
        pipeline = PredictPipeline(
            settings,
            competition_key=comp.key,
            locale=locale,
        )
        result = pipeline.run(fixture_id=fixture_id)
    except RuntimeError as exc:
        logger.warning("Predict API runtime error for fixture %s: %s", fixture_id, exc)
        raise HTTPException(
            status_code=503,
            detail={
                "status": "error",
                "fixture_id": fixture_id,
                "message": str(exc),
                "errors": [],
            },
        ) from exc
    except Exception as exc:
        logger.exception("Predict API error for fixture %s", fixture_id)
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "fixture_id": fixture_id,
                "message": "Failed to run prediction pipeline.",
                "errors": [],
            },
        ) from exc

    if not result.success:
        return JSONResponse(status_code=422, content=_failure_payload(fixture_id, result))

    payload = _success_payload(result)
    try:
        from worldcup_predictor.automation.worldcup_background.prediction_runner import build_api_payload

        payload = build_api_payload(
            result,
            intelligence_report=result.intelligence_report,
            specialist_report=result.specialist_report,
        )
    except Exception:
        payload["cache_source"] = "live"
    kickoff = kickoff_from_payload(payload) or _kickoff_for_fixture(fixture_id)
    if kickoff is not None:
        payload["kickoff_utc"] = kickoff.isoformat()
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
    try:
        from worldcup_predictor.automation.worldcup_background.prediction_store import WorldcupPredictionStore

        WorldcupPredictionStore(settings).upsert(
            fixture_id,
            payload,
            kickoff_utc=payload.get("kickoff_utc"),
            source="user_predict",
            prediction_is_placeholder=bool(getattr(result.prediction, "is_placeholder", False)),
        )
    except Exception as exc:
        log_enrichment_failure(
            "worldcup_predictor.api.routes.predictions",
            exc,
            fixture_id=fixture_id,
            layer="prediction_store_upsert",
        )
    if user is not None and not is_admin:
        try:
            from worldcup_predictor.subscription.quota_service import record_prediction_usage

            record_prediction_usage(user.id, fixture_id)
        except Exception as exc:
            log_enrichment_failure(
                "worldcup_predictor.api.routes.predictions",
                exc,
                fixture_id=fixture_id,
                layer="quota_usage_record",
            )
    _record_user_history(user, payload)
    return enrich_prediction_payload(
        payload,
        competition_key=comp.key,
        season=comp.season,
        user_id=user.id if user else None,
        role=user.role if user else None,
        settings=settings,
    )
