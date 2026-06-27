"""Phase A23 — periodic lifecycle evaluation cycle."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcomeResolver
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.lifecycle.evaluator import evaluate_lifecycle_fixture
from worldcup_predictor.lifecycle.store import LifecycleStore

logger = logging.getLogger(__name__)


@dataclass
class LifecycleCycleResult:
    scanned: int = 0
    evaluated: int = 0
    skipped: int = 0
    errors: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)


def run_lifecycle_evaluation_cycle(
    *,
    settings: Settings | None = None,
    limit: int = 100,
) -> LifecycleCycleResult:
    settings = settings or get_settings()
    if not getattr(settings, "prediction_lifecycle_enabled", True):
        return LifecycleCycleResult()

    store = LifecycleStore(settings)
    resolver = FixtureOutcomeResolver(settings)
    result = LifecycleCycleResult()

    try:
        fixture_ids = store.list_pending_fixture_ids(limit=limit)
        result.scanned = len(fixture_ids)

        for fixture_id in fixture_ids:
            records = store.list_records_for_fixture(fixture_id, limit=1)
            if not records:
                result.skipped += 1
                continue
            latest = records[-1]
            payload = latest.get("payload")
            if not isinstance(payload, dict):
                raw = latest.get("payload_json")
                try:
                    payload = json.loads(raw) if raw else None
                except (json.JSONDecodeError, TypeError):
                    payload = None
            if not payload:
                result.skipped += 1
                continue

            outcome = resolver.resolve(fixture_id)
            try:
                eval_result = evaluate_lifecycle_fixture(
                    fixture_id,
                    payload=payload,
                    outcome=outcome,
                    competition_key=latest.get("competition_key"),
                    store=store,
                )
                if eval_result.get("status") == "ok":
                    result.evaluated += 1
                else:
                    result.skipped += 1
                result.details.append(eval_result)
            except Exception as exc:
                logger.exception("lifecycle_cycle fixture_id=%s", fixture_id)
                result.errors += 1
                result.details.append({"fixture_id": fixture_id, "status": "error", "reason": str(exc)})
    finally:
        store.close()

    logger.info("lifecycle_evaluation_cycle %s", {"scanned": result.scanned, "evaluated": result.evaluated})
    return result
