"""Capture learning records at prediction time — append-only, non-blocking."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.domain.specialist import MatchSpecialistReport

logger = logging.getLogger(__name__)

_AGENT_LABELS: dict[str, str] = {
    "team_form_agent": "Form",
    "elo_team_strength_intelligence_agent": "ELO & Strength",
    "xg_chance_quality_intelligence_agent": "xG & Chance Quality",
    "lineup_intelligence_agent": "Lineup Intelligence",
    "lineup_agent": "Lineup",
    "injury_suspension_intelligence_agent": "Injury Intelligence",
    "injury_suspension_agent": "Injuries",
    "sharp_money_intelligence_agent": "Sharp Money",
    "market_consensus_agent": "Market Consensus",
    "odds_movement_agent": "Odds Movement",
    "weather_agent": "Weather",
    "motivation_psychology_agent": "Motivation",
    "referee_agent": "Referee",
    "player_quality_agent": "Player Quality",
    "tactics_agent": "Tactics",
    "odds_control_agent": "Odds Control",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _specialist_lean(agent_key: str, signals: dict[str, Any]) -> str | None:
    impact = signals.get("prediction_impact") or {}
    if impact:
        try:
            h = float(impact.get("home_adjustment", 0) or 0)
            a = float(impact.get("away_adjustment", 0) or 0)
            if h - a > 0.5:
                return "home"
            if a - h > 0.5:
                return "away"
        except (TypeError, ValueError):
            pass

    if agent_key == "team_form_agent":
        h = float(signals.get("form_score_home", 50) or 50)
        a = float(signals.get("form_score_away", 50) or 50)
        if h > a + 5:
            return "home"
        if a > h + 5:
            return "away"
        return "neutral"

    if agent_key == "elo_team_strength_intelligence_agent":
        matchup = (signals.get("matchup_advantage") or {}).get("side")
        if matchup == "home":
            return "home"
        if matchup == "away":
            return "away"
        diff = signals.get("elo_difference")
        if diff is not None:
            if float(diff) > 40:
                return "home"
            if float(diff) < -40:
                return "away"
        return "neutral"

    if agent_key == "xg_chance_quality_intelligence_agent":
        adv = (signals.get("chance_quality_advantage") or {}).get("side")
        if adv == "home":
            return "home"
        if adv == "away":
            return "away"
        home_edge = signals.get("home_chance_edge")
        if home_edge is not None:
            if float(home_edge) > 15:
                return "home"
            if float(home_edge) < -15:
                return "away"
        return "neutral"

    if agent_key == "market_consensus_agent":
        h = signals.get("home_implied_probability")
        a = signals.get("away_implied_probability")
        if h is not None and a is not None:
            if float(h) > float(a) + 0.05:
                return "home"
            if float(a) > float(h) + 0.05:
                return "away"
        return "neutral"

    if agent_key in {"lineup_intelligence_agent", "injury_suspension_intelligence_agent"}:
        home = signals.get("home") or {}
        away = signals.get("away") or {}
        if agent_key == "lineup_intelligence_agent":
            hs = float(home.get("lineup_strength", 50) or 50)
            aw = float(away.get("lineup_strength", 50) or 50)
        else:
            hs = 100 - float(home.get("injury_impact_score", 0) or 0)
            aw = 100 - float(away.get("injury_impact_score", 0) or 0)
        if hs > aw + 5:
            return "home"
        if aw > hs + 5:
            return "away"
        return "neutral"

    return None


def _summarize_specialists(specialist: MatchSpecialistReport | None) -> dict[str, Any]:
    if not specialist:
        return {}
    out: dict[str, Any] = {}
    for agent_key, label in _AGENT_LABELS.items():
        sig = specialist.signal(agent_key)
        if not sig or not sig.signals:
            continue
        lean = _specialist_lean(agent_key, sig.signals)
        out[agent_key] = {
            "label": label,
            "status": sig.status,
            "impact_score": sig.impact_score,
            "lean": lean,
            "missing_data": sig.missing_data or [],
        }
    return out


def _summarize_fusion(prediction: MatchPrediction | None) -> dict[str, Any]:
    if not prediction:
        return {}
    try:
        from worldcup_predictor.fusion.final_decision_fusion_engine_v2 import load_fusion_from_prediction

        fusion = load_fusion_from_prediction(prediction)
        if not fusion:
            return {}
        return {
            "consensus_strength": fusion.consensus_strength,
            "decision_quality_score": fusion.decision_quality_score,
            "decision_quality_band": fusion.decision_quality_band,
            "confidence_adjustment": fusion.confidence_adjustment,
            "risk_flags": fusion.risk_flags,
        }
    except Exception:
        return {}


def build_learning_payload(
    prediction: MatchPrediction,
    *,
    competition_key: str,
    prediction_id: str,
    specialist_report: MatchSpecialistReport | None = None,
) -> dict[str, Any]:
    return {
        "fixture_id": prediction.fixture_id,
        "prediction_id": prediction_id,
        "competition_key": competition_key,
        "match_name": prediction.match_name,
        "predicted_1x2": prediction.one_x_two.selection,
        "predicted_over_under": prediction.over_under.selection,
        "confidence": prediction.confidence_score,
        "risk_level": prediction.risk_level.value if hasattr(prediction.risk_level, "value") else str(prediction.risk_level),
        "no_bet_flag": prediction.no_bet_flag,
        "specialists": _summarize_specialists(specialist_report),
        "fusion": _summarize_fusion(prediction),
        "actual_1x2": None,
        "actual_over_under": None,
        "one_x_two_correct": None,
        "over_under_correct": None,
        "draw_correct": None,
    }


def capture_learning_record(
    prediction: MatchPrediction,
    *,
    competition_key: str = "world_cup_2026",
    prediction_id: str | None = None,
    specialist_report: MatchSpecialistReport | None = None,
    repository: Any | None = None,
) -> bool:
    """Persist append-only learning record — never raises."""
    try:
        from worldcup_predictor.database.repository import FootballIntelligenceRepository

        repo = repository or FootballIntelligenceRepository()
        pid = prediction_id or prediction.metadata.get("prediction_id") or uuid.uuid4().hex
        record_id = f"{prediction.fixture_id}-{pid}"
        payload = build_learning_payload(
            prediction,
            competition_key=competition_key,
            prediction_id=pid,
            specialist_report=specialist_report,
        )
        created = repo.append_learning_record_v2(
            record_id=record_id,
            fixture_id=prediction.fixture_id,
            prediction_id=pid,
            competition_key=competition_key,
            payload=payload,
            created_at=_utc_now(),
        )
        if hasattr(repo, "close") and repository is None:
            repo.close()
        return created
    except Exception as exc:  # noqa: BLE001
        logger.debug("Learning record capture skipped: %s", exc)
        return False
