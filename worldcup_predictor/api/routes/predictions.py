"""Prediction endpoints — thin wrappers over PredictPipeline."""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from worldcup_predictor.config.competitions import DEFAULT_COMPETITION_KEY, get_competition
from worldcup_predictor.config.settings import Locale, get_settings
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline, PredictPipelineResult

logger = logging.getLogger(__name__)

router = APIRouter(tags=["predictions"])

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
    raw_ft = (prediction.metadata or {}).get("extended_markets_ft_1x2")
    if raw_ft:
        try:
            ft = json.loads(raw_ft) if isinstance(raw_ft, str) else raw_ft
            if isinstance(ft, dict) and "home" in ft:
                return {
                    "home_win": round(float(ft["home"]) * 100, 1),
                    "draw": round(float(ft["draw"]) * 100, 1),
                    "away_win": round(float(ft["away"]) * 100, 1),
                }
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    raw_ext = (prediction.metadata or {}).get("extended_markets")
    if raw_ext:
        try:
            data = json.loads(raw_ext) if isinstance(raw_ext, str) else raw_ext
            ft = (data or {}).get("full_time_1x2") or {}
            if ft:
                return {
                    "home_win": round(float(ft.get("home", 0)) * 100, 1),
                    "draw": round(float(ft.get("draw", 0)) * 100, 1),
                    "away_win": round(float(ft.get("away", 0)) * 100, 1),
                }
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    return {
        "selection": prediction.one_x_two.selection,
        "selection_probability": prediction.one_x_two.probability,
        "over_under_2_5": {
            "selection": prediction.over_under.selection,
            "probability": prediction.over_under.probability,
        },
    }


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


def _success_payload(result: PredictPipelineResult) -> dict[str, Any]:
    prediction = result.prediction
    home_team, away_team = _split_teams(prediction.match_name)
    return {
        "status": "ok",
        "fixture_id": prediction.fixture_id,
        "home_team": home_team,
        "away_team": away_team,
        "prediction": _map_prediction_selection(prediction.one_x_two.selection),
        "confidence": prediction.confidence_score,
        "probabilities": _extract_probabilities(prediction),
        "specialist_summary": _specialist_summary(result, prediction),
        "data_quality": _data_quality_score(prediction),
    }


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


@router.post("/predict/{fixture_id}")
def predict_fixture(
    fixture_id: int,
    competition: str = Query(default=DEFAULT_COMPETITION_KEY, description="Competition registry key"),
    season: int | None = Query(default=None, description="Season year override"),
    locale: Locale = Query(default="en", description="Output locale"),
) -> dict[str, Any]:
    """
    Run the full prediction pipeline for one fixture.

    Wraps ``PredictPipeline.run()`` (same path as ``python main.py predict``
    and GUI ``match_action_panel``).
    """
    try:
        comp = get_competition(competition)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if season is not None:
        comp = replace(comp, season=season)

    settings = get_settings()

    try:
        pipeline = PredictPipeline(
            settings,
            competition_key=comp.key,
            locale=locale,
        )
        result = pipeline.run(
            fixture_id=fixture_id,
            season=comp.season if season is not None else None,
        )
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

    return _success_payload(result)
