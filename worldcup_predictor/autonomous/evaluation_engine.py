"""Evaluate autonomous prediction snapshots — Phase 61."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcome, FixtureOutcomeResolver
from worldcup_predictor.autonomous.store import AutonomousStore
from worldcup_predictor.automation.worldcup_background.pick_evaluator import evaluate_stored_prediction
from worldcup_predictor.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

EvalStatus = str  # correct | wrong | pending | void | unable_to_evaluate


@dataclass
class EvaluationEngineResult:
    scanned: int = 0
    evaluated: int = 0
    pending: int = 0
    unable: int = 0
    void: int = 0
    errors: int = 0
    api_calls_used: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "evaluated": self.evaluated,
            "pending": self.pending,
            "unable": self.unable,
            "void": self.void,
            "errors": self.errors,
            "api_calls_used": self.api_calls_used,
            "details": self.details[:50],
        }


def _eval_single_market(
    market_id: str,
    prediction: dict[str, Any],
    outcome: FixtureOutcome,
    full_eval: dict[str, Any],
) -> tuple[EvalStatus, str | None]:
    markets = full_eval.get("markets") or {}
    key_map = {
        "1x2": "1x2",
        "over_under_2_5": "over_under_2_5",
        "btts": "btts",
        "double_chance": "double_chance",
        "correct_score": "correct_score",
        "goal_timing": "goal_timing",
        "first_goal_team": "first_goal_team",
        "team_to_score_first": "team_to_score_first",
        "goalscorer": "goalscorer",
    }
    mapped = key_map.get(market_id)
    if mapped and mapped in markets:
        status = str(markets[mapped])
        if status == "unknown":
            return "unable_to_evaluate", "market_unknown"
        if status == "void":
            return "void", "no_selection"
        return status, None

    if not outcome.is_finished:
        return "pending", "fixture_not_finished"
    return "unable_to_evaluate", "no_evaluator_for_market"


def _build_payload_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    pred = snapshot.get("prediction") or {}
    market_id = snapshot.get("market_id")
    payload: dict[str, Any] = {
        "fixture_id": snapshot.get("fixture_id"),
        "probabilities": {},
        "detailed_markets": {},
    }
    selection = pred.get("selection") or pred.get("raw")
    if market_id == "1x2":
        payload["prediction"] = selection
    elif market_id == "over_under_2_5":
        payload["probabilities"]["over_under_2_5"] = pred if isinstance(pred, dict) else {"selection": pred}
    elif market_id == "btts":
        payload["probabilities"]["btts"] = pred if isinstance(pred, dict) else {"selection": pred}
    elif market_id == "double_chance":
        payload["detailed_markets"]["double_chance"] = pred.get("probabilities") or pred
    elif market_id in {"goal_timing", "first_goal_team", "team_to_score_first", "goalscorer", "correct_score"}:
        payload["detailed_markets"][market_id] = pred
    return payload


def run_autonomous_evaluations(
    *,
    settings: Settings | None = None,
    limit: int = 200,
) -> EvaluationEngineResult:
    settings = settings or get_settings()
    store = AutonomousStore(settings)
    resolver = FixtureOutcomeResolver(settings)
    result = EvaluationEngineResult()

    pending_snapshots = store.list_snapshots_needing_evaluation(limit=limit)
    result.scanned = len(pending_snapshots)

    for snap in pending_snapshots:
        fid = int(snap["fixture_id"])
        sid = int(snap["id"])
        market_id = str(snap["market_id"])
        try:
            outcome = resolver.resolve(fid)
            if outcome is None:
                result.unable += 1
                store.upsert_evaluation(
                    snapshot_id=sid,
                    fixture_id=fid,
                    engine=str(snap["engine"]),
                    market_id=market_id,
                    status="unable_to_evaluate",
                    evaluation_reason="outcome_unavailable",
                )
                continue

            payload = _build_payload_from_snapshot(snap)
            full_eval = evaluate_stored_prediction(payload, outcome)
            status, reason = _eval_single_market(market_id, snap.get("prediction") or {}, outcome, full_eval)

            if status == "pending":
                result.pending += 1
            elif status == "unable_to_evaluate":
                result.unable += 1
            elif status == "void":
                result.void += 1
            else:
                result.evaluated += 1

            store.upsert_evaluation(
                snapshot_id=sid,
                fixture_id=fid,
                engine=str(snap["engine"]),
                market_id=market_id,
                status=status,
                evaluation_reason=reason,
                actual={
                    "final_score": outcome.final_score,
                    "actual_result": outcome.actual_result,
                    "is_finished": outcome.is_finished,
                },
            )
            result.details.append({"snapshot_id": sid, "fixture_id": fid, "market_id": market_id, "status": status})
        except Exception as exc:
            result.errors += 1
            logger.warning("autonomous_eval_failed snapshot=%s: %s", sid, exc)

    return result
