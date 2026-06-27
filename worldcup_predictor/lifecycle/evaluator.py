"""Phase A23 — per-market evaluation for lifecycle records."""

from __future__ import annotations

import logging
from typing import Any

from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcome
from worldcup_predictor.automation.worldcup_background.pick_evaluator import evaluate_stored_prediction
from worldcup_predictor.lifecycle.accuracy import rebuild_market_accuracy_rollups
from worldcup_predictor.lifecycle.config import RESULT_COLORS
from worldcup_predictor.lifecycle.knowledge import create_knowledge_from_evaluation
from worldcup_predictor.lifecycle.store import LifecycleStore

logger = logging.getLogger(__name__)


def _color_for_result(result: str) -> str:
    return RESULT_COLORS.get(str(result).lower(), "gray")


def _market_prediction(payload: dict[str, Any], market_id: str) -> str | None:
    mid = market_id.lower()
    if mid == "1x2":
        return str(payload.get("prediction") or "")
    probs = payload.get("probabilities") or {}
    if mid == "over_under_2_5" and isinstance(probs.get("over_under_2_5"), dict):
        return str(probs["over_under_2_5"].get("selection") or "")
    if mid == "btts" and isinstance(probs.get("btts"), dict):
        return str(probs["btts"].get("selection") or "")
    dm = payload.get("detailed_markets") or {}
    if mid == "double_chance" and isinstance(dm.get("double_chance"), dict):
        dc = dm["double_chance"]
        best = max(
            [("home_or_draw", dc.get("home_or_draw")), ("draw_or_away", dc.get("draw_or_away")), ("home_or_away", dc.get("home_or_away"))],
            key=lambda x: float(x[1] or 0),
        )[0]
        return best
    adv = payload.get("advanced_markets") or {}
    if mid in adv and isinstance(adv[mid], dict):
        return str(adv[mid].get("selection") or adv[mid].get("predicted") or "")
    pick_keys = {
        "safe_pick": "safe_pick",
        "value_pick": "value_pick",
        "caution_pick": "caution_pick",
        "halftime": "halftime",
        "correct_score": "correct_score",
        "first_goal_team": "first_goal_team",
        "goal_timing": "goal_timing",
        "goalscorer": "goalscorer",
    }
    pk = pick_keys.get(mid)
    if pk:
        val = payload.get(pk) or (dm.get(pk) if isinstance(dm, dict) else None)
        if isinstance(val, dict):
            return str(val.get("selection") or val.get("pick") or val.get("predicted") or "")
        if val:
            return str(val)
    return None


def _market_actual(outcome: FixtureOutcome, evaluation: dict[str, Any], market_id: str) -> str | None:
    mid = market_id.lower()
    if mid == "1x2":
        return outcome.actual_result
    if mid == "over_under_2_5" and outcome.final_score and "-" in outcome.final_score:
        parts = outcome.final_score.split("-", 1)
        try:
            total = int(parts[0].strip()) + int(parts[1].strip())
            return "over" if total > 2.5 else "under"
        except ValueError:
            return None
    if mid == "btts" and outcome.final_score and "-" in outcome.final_score:
        parts = outcome.final_score.split("-", 1)
        try:
            h, a = int(parts[0].strip()), int(parts[1].strip())
            return "yes" if h > 0 and a > 0 else "no"
        except ValueError:
            return None
    adv = evaluation.get("advanced_markets") or {}
    block = adv.get(mid) or adv.get(mid.replace("_", ""))
    if isinstance(block, dict):
        return str(block.get("actual") or block.get("actual_result") or "")
    if mid == "halftime":
        return outcome.ht_result
    if mid == "correct_score":
        return outcome.final_score
    if mid == "first_goal_team":
        return outcome.first_goal_team
    return None


def _extract_fixture_results(outcome: FixtureOutcome, evaluation: dict[str, Any]) -> dict[str, Any]:
    markets = dict(evaluation.get("markets") or {})
    adv = evaluation.get("advanced_markets") or {}
    if isinstance(adv, dict):
        for k, v in adv.items():
            if isinstance(v, dict) and v.get("status"):
                markets[k] = v.get("status")

    btts_actual = _market_actual(outcome, evaluation, "btts")
    ou_actual = _market_actual(outcome, evaluation, "over_under_2_5")

    goalscorer_results: dict[str, Any] = {}
    gs = adv.get("goalscorer") if isinstance(adv, dict) else None
    if isinstance(gs, dict):
        goalscorer_results = {
            "predicted": gs.get("predicted") or gs.get("selection"),
            "actual": gs.get("actual"),
            "status": gs.get("status"),
        }

    return {
        "ft_score": outcome.final_score,
        "ht_score": outcome.ht_score,
        "winner": outcome.actual_result,
        "btts_result": btts_actual,
        "over_under_result": ou_actual,
        "correct_score_result": outcome.final_score,
        "goal_timing_result": (adv.get("goal_timing") or {}).get("actual") if isinstance(adv.get("goal_timing"), dict) else None,
        "first_goal_team_result": outcome.first_goal_team,
        "goalscorer_results": goalscorer_results,
        "markets": markets,
    }


def evaluate_lifecycle_fixture(
    fixture_id: int,
    *,
    payload: dict[str, Any],
    outcome: FixtureOutcome,
    competition_key: str | None = None,
    store: LifecycleStore | None = None,
) -> dict[str, Any]:
    """Evaluate latest lifecycle record(s) for a finished fixture."""
    owned = store is None
    store = store or LifecycleStore()
    try:
        records = store.list_records_for_fixture(fixture_id)
        if not records:
            return {"status": "skipped", "reason": "no_lifecycle_records"}

        evaluation = evaluate_stored_prediction(payload, outcome)
        results_doc = _extract_fixture_results(outcome, evaluation)
        store.upsert_fixture_results(
            fixture_id,
            competition_key=competition_key or payload.get("competition_key"),
            ft_score=results_doc["ft_score"],
            ht_score=results_doc["ht_score"],
            winner=results_doc["winner"],
            btts_result=results_doc["btts_result"],
            over_under_result=results_doc["over_under_result"],
            correct_score_result=results_doc["correct_score_result"],
            goal_timing_result=results_doc["goal_timing_result"],
            first_goal_team_result=results_doc["first_goal_team_result"],
            goalscorer_results=results_doc["goalscorer_results"],
            markets=results_doc["markets"],
        )

        markets_map: dict[str, str] = dict(evaluation.get("markets") or {})
        adv = evaluation.get("advanced_markets") or {}
        if isinstance(adv, dict):
            for key, block in adv.items():
                if isinstance(block, dict) and block.get("status"):
                    markets_map[key] = str(block["status"])

        evaluated_count = 0
        target_record = records[-1]
        record_id = int(target_record["id"])
        payload_use = target_record.get("payload") or payload

        for market_id, result in markets_map.items():
            if not market_id or market_id.startswith("recommended_"):
                continue
            result_str = str(result).lower()
            eval_key = f"{record_id}:{market_id}"
            store.insert_market_evaluation(
                eval_key=eval_key,
                record_id=record_id,
                fixture_id=fixture_id,
                market_id=market_id,
                prediction=_market_prediction(payload_use, market_id),
                actual=_market_actual(outcome, evaluation, market_id),
                result=result_str,
                color=_color_for_result(result_str),
                confidence=target_record.get("confidence"),
                bet_quality_score=target_record.get("bet_quality_score"),
            )
            evaluated_count += 1

        new_state = "evaluated" if outcome.is_finished else "live"
        store.update_record_state(record_id, new_state)
        store.add_event(
            fixture_id=fixture_id,
            record_id=record_id,
            event_type="evaluated" if outcome.is_finished else "live",
            lifecycle_state=new_state,
            summary=f"Evaluated {evaluated_count} markets — {evaluation.get('status')}",
            meta={"final_score": outcome.final_score, "overall": evaluation.get("status")},
        )

        if outcome.is_finished:
            store.update_record_state(record_id, "archived")
            store.add_event(
                fixture_id=fixture_id,
                record_id=record_id,
                event_type="archived",
                lifecycle_state="archived",
                summary="Archived permanently",
            )
            create_knowledge_from_evaluation(
                fixture_id=fixture_id,
                record_id=record_id,
                payload=payload_use,
                evaluation=evaluation,
                outcome=outcome,
                store=store,
            )
            rebuild_market_accuracy_rollups(store=store)

        return {
            "status": "ok",
            "fixture_id": fixture_id,
            "record_id": record_id,
            "evaluated_markets": evaluated_count,
            "overall": evaluation.get("status"),
            "lifecycle_state": "archived" if outcome.is_finished else new_state,
        }
    except Exception as exc:
        logger.exception("lifecycle_evaluate_failed fixture_id=%s", fixture_id)
        return {"status": "error", "reason": str(exc)}
    finally:
        if owned:
            store.close()
