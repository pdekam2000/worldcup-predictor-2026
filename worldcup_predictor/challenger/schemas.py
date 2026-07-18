"""Challenger prediction / freeze schemas."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.challenger.constants import (
    CHALLENGER_FINAL_DECISION_AUTHORITY,
    CHALLENGER_IS_SHADOW,
    CHALLENGER_PUBLIC_VISIBLE,
    CHALLENGER_USER_VISIBLE,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def content_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_challenger_prediction_envelope(
    *,
    fixture_id: int,
    model_id: str,
    model_version: str,
    outputs: dict[str, Any],
    feature_snapshot_id: str | None,
    feature_snapshot_hash: str | None,
    prediction_time: str,
    kickoff: str | None,
    home_team: str | None,
    away_team: str | None,
    competition: str | None,
    prediction_scope: str,
    validation_tier: str | None,
    confidence: float | None,
    data_quality: str | None,
    missing_features: list[str],
    warnings: list[str],
    status: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated = generated_at or utc_now()
    core = {
        "fixture_id": int(fixture_id),
        "model_id": model_id,
        "model_version": model_version,
        "generated_at": generated,
        "feature_snapshot_id": feature_snapshot_id,
        "feature_snapshot_hash": feature_snapshot_hash,
        "prediction_time": prediction_time,
        "kickoff": kickoff,
        "home_team": home_team,
        "away_team": away_team,
        "competition": competition,
        "prediction_scope": prediction_scope,
        "validation_tier": validation_tier,
        "output_probabilities": outputs,
        "confidence": confidence,
        "data_quality": data_quality,
        "missing_features": list(missing_features),
        "warnings": list(warnings),
        "status": status,
        "is_shadow": CHALLENGER_IS_SHADOW,
        "is_user_visible": CHALLENGER_USER_VISIBLE,
        "public_visible": CHALLENGER_PUBLIC_VISIBLE,
        "final_decision_authority": CHALLENGER_FINAL_DECISION_AUTHORITY,
    }
    core["prediction_content_hash"] = content_hash(
        {
            "fixture_id": core["fixture_id"],
            "model_id": core["model_id"],
            "model_version": core["model_version"],
            "feature_snapshot_hash": core["feature_snapshot_hash"],
            "output_probabilities": core["output_probabilities"],
            "status": core["status"],
        }
    )
    return core
