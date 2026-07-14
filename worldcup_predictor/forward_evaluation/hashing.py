"""Deterministic hashing for forward-evaluation freeze envelopes."""

from __future__ import annotations

import hashlib
import json
from typing import Any

_FORBIDDEN_RESULT_KEYS = frozenset(
    {
        "actual_score",
        "actual_home_goals",
        "actual_away_goals",
        "actual_1x2",
        "actual_btts",
        "actual_ou25",
        "result_status",
        "finished_at",
        "frozen_at",
        "frozen_at_utc",
        "prediction_id",
        "batch_id",
        "request_id",
        "runtime_duration_ms",
    }
)

_VOLATILE_ENVELOPE_KEYS = frozenset(
    {
        "frozen_at",
        "frozen_at_utc",
        "prediction_id",
        "freeze_id",
        "batch_id",
        "source_commit_sha",
        "evaluation_status",
        "quarantine_reason",
        "supersedes_freeze_id",
    }
)


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))


def payload_hash(payload: dict[str, Any], *, exclude: frozenset[str] | None = None) -> str:
    skip = _FORBIDDEN_RESULT_KEYS | (exclude or frozenset())
    clean = {k: v for k, v in payload.items() if k not in skip}
    blob = canonical_json(clean)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def source_payload_hash(
    *,
    fixture_id: int,
    wsp_predicted_at: str | None,
    wsp_payload: dict[str, Any],
    ecse_snapshot_id: int | None,
    ecse_generated_at: str | None,
    ecse_top5: list[dict[str, Any]],
) -> str:
    material = {
        "fixture_id": int(fixture_id),
        "wsp_predicted_at": wsp_predicted_at,
        "wsp_payload": wsp_payload,
        "ecse_snapshot_id": ecse_snapshot_id,
        "ecse_generated_at": ecse_generated_at,
        "ecse_top5": ecse_top5,
    }
    return payload_hash(material)


def content_hash(envelope: dict[str, Any]) -> str:
    return payload_hash(envelope, exclude=_VOLATILE_ENVELOPE_KEYS)
