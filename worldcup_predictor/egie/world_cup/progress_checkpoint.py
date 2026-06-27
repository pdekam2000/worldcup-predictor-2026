"""Phase 62C — resumable progress checkpoint for Sportmonks WC import."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.egie.world_cup.config import PROGRESS_CHECKPOINT_PATH

_DEFAULT: dict[str, Any] = {
    "started_at": None,
    "updated_at": None,
    "last_fixture_id": None,
    "processed_count": 0,
    "success_count": 0,
    "failed_count": 0,
    "skipped_cached_count": 0,
    "api_calls_used": 0,
    "cache_hits": 0,
    "xg_found": 0,
    "xg_missing": 0,
    "lineups_found": 0,
    "lineups_missing": 0,
    "status": "pending",
    "completed_fixture_ids": [],
}


def checkpoint_path(path: str | Path | None = None) -> Path:
    return Path(path or PROGRESS_CHECKPOINT_PATH)


def load_checkpoint(path: str | Path | None = None) -> dict[str, Any]:
    p = checkpoint_path(path)
    if not p.is_file():
        return dict(_DEFAULT)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        out = dict(_DEFAULT)
        out.update(data if isinstance(data, dict) else {})
        return out
    except (json.JSONDecodeError, OSError):
        return dict(_DEFAULT)


def save_checkpoint(state: dict[str, Any], path: str | Path | None = None) -> Path:
    p = checkpoint_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    if not state.get("started_at"):
        state["started_at"] = state["updated_at"]
    p.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    return p


def mark_fixture_complete(state: dict[str, Any], fixture_id: int) -> None:
    done = state.setdefault("completed_fixture_ids", [])
    if fixture_id not in done:
        done.append(fixture_id)


def is_fixture_complete(state: dict[str, Any], fixture_id: int) -> bool:
    return fixture_id in (state.get("completed_fixture_ids") or [])
