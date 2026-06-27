"""Phase A23 — automatic knowledge records after evaluation."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcome
from worldcup_predictor.lifecycle.store import LifecycleStore


def create_knowledge_from_evaluation(
    *,
    fixture_id: int,
    record_id: int,
    payload: dict[str, Any],
    evaluation: dict[str, Any],
    outcome: FixtureOutcome,
    store: LifecycleStore,
) -> int:
    created = 0
    markets = dict(evaluation.get("markets") or {})
    adv = evaluation.get("advanced_markets") or {}
    if isinstance(adv, dict):
        for key, block in adv.items():
            if isinstance(block, dict) and block.get("status") in {"correct", "wrong"}:
                markets[key] = block["status"]

    engine = payload.get("prediction_engine_version") or payload.get("engine") or "production"
    confidence = payload.get("confidence")
    bq = payload.get("bet_quality_score")
    if bq is None and isinstance(payload.get("bet_quality"), dict):
        bq = payload["bet_quality"].get("score")

    for market_id, result in markets.items():
        result_str = str(result).lower()
        if result_str not in {"correct", "wrong"}:
            continue
        knowledge = {
            "fixture_id": fixture_id,
            "market_id": market_id,
            "result": result_str,
            "final_score": outcome.final_score,
            "prediction": payload.get("prediction"),
            "tier": (payload.get("accuracy_tracking") or {}).get("pick_tier"),
            "no_bet": payload.get("no_bet"),
        }
        raw = json.dumps(knowledge, sort_keys=True, default=str)
        knowledge_key = hashlib.sha256(f"{record_id}:{market_id}:{raw}".encode()).hexdigest()[:32]
        reason = f"{market_id} was {result_str} (actual {outcome.actual_result}, score {outcome.final_score})"
        kid = store.insert_knowledge_record(
            knowledge_key=knowledge_key,
            fixture_id=fixture_id,
            record_id=record_id,
            market_id=market_id,
            outcome=result_str,
            reason=reason,
            confidence=float(confidence) if confidence is not None else None,
            quality_score=float(bq) if bq is not None else None,
            engine=str(engine),
            knowledge=knowledge,
        )
        if kid:
            created += 1
    return created
