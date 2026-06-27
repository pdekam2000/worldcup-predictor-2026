"""Part C/D — shadow prediction JSONL store with duplicate protection."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.elite_orchestrator.shadow_config import MODEL_VERSION, PREDICTIONS_PATH
from worldcup_predictor.elite_orchestrator.shadow_jsonl_io import append_jsonl_rows, load_jsonl


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _prediction_day(iso_ts: str | None = None) -> str:
    ts = iso_ts or _utc_now()
    return ts[:10]


def duplicate_key(row: dict[str, Any]) -> tuple[int, str, str, str]:
    return (
        int(row.get("fixture_id") or 0),
        str(row.get("market_id") or row.get("market") or ""),
        str(row.get("model_version") or MODEL_VERSION),
        str(row.get("prediction_day") or ""),
    )


def load_existing_keys(path: Path | None = None) -> set[tuple[int, str, str, str]]:
    p = path or PREDICTIONS_PATH
    return {duplicate_key(row) for row in load_jsonl(p)}


def flatten_prediction_record(
    bundle: dict[str, Any],
    *,
    market_id: str,
    market_block: dict[str, Any],
) -> dict[str, Any]:
    """One JSONL row per market per fixture."""
    generated_at = bundle.get("generated_at") or _utc_now()
    contributions = market_block.get("component_contributions") or []
    tiers = {
        "market_tier": market_block.get("tier"),
        "overall_tier": (bundle.get("confidence_tiers") or {}).get("overall"),
    }
    return {
        "fixture_id": bundle.get("fixture_id"),
        "sportmonks_fixture_id": bundle.get("sportmonks_fixture_id"),
        "competition_key": bundle.get("competition_key"),
        "league_id": bundle.get("league_id"),
        "generated_at": generated_at,
        "kickoff_time": bundle.get("kickoff_time"),
        "prediction_day": _prediction_day(generated_at),
        "market_id": market_id,
        "market_predictions": {
            "prediction": market_block.get("prediction"),
            "confidence": market_block.get("confidence"),
            "tier": market_block.get("tier"),
            "evidence": market_block.get("evidence"),
            "reasoning": market_block.get("reasoning"),
        },
        "component_contributions": contributions,
        "confidence_tiers": tiers,
        "model_versions": bundle.get("model_versions") or {"elite_orchestrator": MODEL_VERSION},
        "fusion": bundle.get("fusion"),
        "is_shadow": True,
        "is_user_visible": False,
        "meta": bundle.get("meta") or {},
    }


def append_predictions(
    rows: list[dict[str, Any]],
    *,
    path: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    p = path or PREDICTIONS_PATH
    return append_jsonl_rows(p, rows, dedupe_key=duplicate_key, force=force)


def validate_row(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = (
        "fixture_id",
        "generated_at",
        "kickoff_time",
        "market_predictions",
        "component_contributions",
        "confidence_tiers",
        "model_versions",
        "is_shadow",
        "is_user_visible",
    )
    for field in required:
        if field not in row:
            errors.append(f"missing:{field}")
    if row.get("is_shadow") is not True:
        errors.append("is_shadow_not_true")
    if row.get("is_user_visible") is not False:
        errors.append("is_user_visible_not_false")
    return errors
