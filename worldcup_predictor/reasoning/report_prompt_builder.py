from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.decision.audit_report import PredictionAuditReport
from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.domain.specialist import MatchSpecialistReport, SpecialistSignal


def build_prompt_payload(
    *,
    prediction: MatchPrediction,
    audit: PredictionAuditReport | None,
    intelligence: MatchIntelligenceReport,
    specialists: MatchSpecialistReport,
    locale: str,
) -> dict[str, Any]:
    """Compact structured JSON for OpenAI — no secrets, no raw cache blobs."""
    generated_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    dq = intelligence.data_quality
    intel_summary = {
        "fixture_id": intelligence.fixture_id,
        "source": intelligence.source,
        "is_placeholder": intelligence.is_placeholder,
        "missing_data": intelligence.missing_data[:20],
        "data_quality_score": round(dq.score, 3) if dq else None,
        "data_quality_grade": dq.grade if dq else None,
        "data_quality_breakdown": dq.breakdown if dq else {},
        "data_quality_total": dq.breakdown_total if dq else 0,
        "home_team": _team_summary(intelligence.home_team, intelligence.home_recent_fixtures),
        "away_team": _team_summary(intelligence.away_team, intelligence.away_recent_fixtures),
        "head_to_head": _trim_dict(intelligence.head_to_head, max_keys=8),
        "standings_context": _trim_dict(intelligence.standings_context, max_keys=6),
        "group_context": _trim_dict(intelligence.group_context, max_keys=10),
        "odds_available": bool(intelligence.odds and intelligence.odds.available),
        "odds_snapshot": _trim_dict(
            {"bookmaker_count": len(intelligence.odds.bookmakers)} if intelligence.odds and intelligence.odds.available else None,
            max_keys=4,
        ),
        "lineups_available": bool(intelligence.lineups and intelligence.lineups.get("available")),
        "fixture_statistics_available": bool(intelligence.fixture_statistics),
        "referee": intelligence.referee,
        "weather": intelligence.weather,
        "api_endpoint_summary": intelligence.api_inspection.as_dict() if intelligence.api_inspection else {},
    }

    specialist_summary = {
        "source": specialists.source,
        "aggregated_signal_score": specialists.aggregated_signal_score,
        "agents": [_signal_summary(name, sig) for name, sig in specialists.signals.items()],
    }

    audit_summary = None
    if audit is not None:
        audit_summary = {
            "supported_factors": [
                {
                    "factor": c.factor_name,
                    "direction": c.direction,
                    "contribution": round(c.contribution, 3),
                }
                for c in audit.supported_factors[:8]
            ],
            "opposed_factors": [
                {"factor": c.factor_name, "contribution": round(c.contribution, 3)}
                for c in audit.opposed_factors[:6]
            ],
            "conflicts": [
                {"severity": c.severity, "description": c.description[:200]}
                for c in audit.conflicts[:6]
            ],
            "limitations": [
                {"field": lim.field, "impact": lim.impact[:160]}
                for lim in audit.limitations[:8]
            ],
            "trace": None
            if audit.trace is None
            else {
                "baseline_confidence": audit.trace.baseline_confidence,
                "final_confidence": audit.trace.final_confidence,
                "watch_only": audit.trace.watch_only,
                "no_bet_reasons": audit.trace.no_bet_reasons[:6],
                "confidence_caps_applied": audit.trace.confidence_caps_applied[:6],
            },
            "market_disagreement_warnings": audit.market_disagreement_warnings[:4],
        }

    frozen_prediction = {
        "match_name": prediction.match_name,
        "one_x_two_selection": prediction.one_x_two.selection,
        "one_x_two_probability": prediction.one_x_two.probability,
        "over_under_selection": prediction.over_under.selection,
        "over_under_probability": prediction.over_under.probability,
        "halftime_goals_estimate": prediction.halftime.estimated_total_goals,
        "first_goal_team": prediction.first_goal.team,
        "first_goal_player": prediction.first_goal.player,
        "confidence_score": prediction.confidence_score,
        "confidence_level": prediction.confidence_level.value,
        "risk_level": prediction.risk_level,
        "no_bet_flag": prediction.no_bet_flag,
        "stage": prediction.stage,
        "confidence_breakdown": {
            "form": prediction.confidence_breakdown.form_score,
            "h2h": prediction.confidence_breakdown.h2h_score,
            "injuries": prediction.confidence_breakdown.injuries_score,
            "lineups": prediction.confidence_breakdown.lineups_score,
            "odds": prediction.confidence_breakdown.odds_score,
            "data_quality": prediction.confidence_breakdown.data_quality_score,
        },
        "prediction_reasons": [
            {"key": r.key, "weight": r.weight} for r in prediction.reasons[:8]
        ],
        "scoreline": prediction.scoreline.label if prediction.scoreline else None,
        "scoreline_candidates": [
            {"score": c.label, "probability": c.probability}
            for c in (prediction.scoreline_candidates or [])[:3]
        ],
        "prediction_quality_score": prediction.prediction_quality_score,
        "consistency_notes": prediction.consistency_notes[:4],
        "explanation": prediction.explanation.get("en") if prediction.explanation else None,
    }

    return {
        "generated_at_utc": generated_at,
        "locale": locale,
        "task": "Write an analytical match report JSON. Explain existing model outputs only.",
        "rules": [
            "Do NOT change numeric predictions or probabilities.",
            "Do NOT remove or contradict no_bet_flag.",
            "Do NOT claim certainty or guaranteed outcomes.",
            f"Use generated_at_utc ({generated_at}) as the analysis timestamp — never cite old training cutoffs like October 2023.",
            "Explain why the model is weak or strong using data_quality_breakdown and missing_data.",
            "Mention missing data when data_quality_total is below 65.",
            "Odds are informational context only — no betting instruction.",
            "If confidence_score < 60 or no_bet_flag is true, emphasize watch only / wait for more data.",
            f"Respond in locale '{locale}' for all narrative string fields.",
        ],
        "frozen_prediction": frozen_prediction,
        "intelligence": intel_summary,
        "specialists": specialist_summary,
        "audit": audit_summary,
        "required_output_keys": [
            "executive_summary",
            "key_factors",
            "tactical_context",
            "risk_notes",
            "data_limitations",
            "market_analysis_information_only",
            "final_analytical_view",
            "disclaimer",
        ],
    }


def build_system_prompt() -> str:
    return (
        "You are an analytical football report writer for WorldCup Predictor Pro 2026. "
        "You explain deterministic model outputs — you never invent missing stats or override safety. "
        "Use generated_at_utc from the user payload as the report date. "
        "Never reference outdated knowledge cutoffs (e.g. October 2023). "
        "Return valid JSON with the required keys only. "
        "All text must be analytical, probabilistic, and must not recommend betting."
    )


def build_user_prompt(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _team_summary(team, recent: list | None = None) -> dict[str, Any]:
    form = team.form[:5] if team.form else None
    if not form and recent and team.team_id:
        from worldcup_predictor.data_quality.intelligence_scoring import form_string_from_recent

        form = form_string_from_recent(recent, team.team_id)[:5]
    injury_count = len(team.injuries.players) if team.injuries and team.injuries.players else 0
    stats_loaded = bool(team.statistics)
    return {
        "name": team.team_name,
        "team_id": team.team_id,
        "form_last5": form,
        "injury_count": injury_count,
        "team_statistics_loaded": stats_loaded,
        "recent_fixtures_count": len(recent) if recent else 0,
        "source": team.source,
    }


def _signal_summary(name: str, signal: SpecialistSignal) -> dict[str, Any]:
    keys = list(signal.signals.keys())[:6]
    trimmed = {k: signal.signals[k] for k in keys}
    return {
        "agent": name,
        "status": signal.status,
        "impact_score": signal.impact_score,
        "signals": trimmed,
        "warnings": signal.warnings[:4],
        "missing_data": signal.missing_data[:4],
    }


def _trim_dict(value: dict | None, *, max_keys: int = 8) -> dict | None:
    if not value:
        return None
    items = list(value.items())[:max_keys]
    return {str(k): value[k] for k, _ in items if not str(k).startswith("_")}
