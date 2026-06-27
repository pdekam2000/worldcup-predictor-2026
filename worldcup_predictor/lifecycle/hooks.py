"""Phase A23 — non-blocking integration hooks."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def hook_after_prediction_upsert(
    fixture_id: int,
    payload: dict[str, Any],
    *,
    source: str = "background",
) -> None:
    try:
        from worldcup_predictor.lifecycle.capture import capture_prediction_from_payload

        capture_prediction_from_payload(payload, fixture_id=fixture_id, source=source)
    except Exception as exc:
        logger.debug("lifecycle_hook_upsert fixture_id=%s: %s", fixture_id, exc)


def hook_after_predops_snapshot(
    *,
    fixture_id: int,
    snapshot_id: str,
    payload: dict[str, Any],
    predops_snapshot: dict[str, Any] | None = None,
    egie_snapshot: dict[str, Any] | None = None,
) -> None:
    try:
        from worldcup_predictor.lifecycle.capture import capture_prediction_from_payload

        capture_prediction_from_payload(
            payload,
            fixture_id=fixture_id,
            source="predops",
            snapshot_id=snapshot_id,
            predops_snapshot=predops_snapshot,
            egie_snapshot=egie_snapshot,
        )
    except Exception as exc:
        logger.debug("lifecycle_hook_predops fixture_id=%s: %s", fixture_id, exc)


def hook_after_worldcup_evaluation(
    fixture_id: int,
    *,
    payload: dict[str, Any],
    competition_key: str | None = None,
) -> None:
    try:
        from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcomeResolver
        from worldcup_predictor.config.settings import get_settings
        from worldcup_predictor.lifecycle.evaluator import evaluate_lifecycle_fixture

        settings = get_settings()
        resolver = FixtureOutcomeResolver(settings)
        outcome = resolver.resolve(fixture_id)
        evaluate_lifecycle_fixture(
            fixture_id,
            payload=payload,
            outcome=outcome,
            competition_key=competition_key,
        )
    except Exception as exc:
        logger.debug("lifecycle_hook_eval fixture_id=%s: %s", fixture_id, exc)
