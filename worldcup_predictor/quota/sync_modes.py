"""League sync modes — Phase 40A."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Literal

SyncMode = Literal["fast", "standard", "full"]
DEFAULT_SYNC_MODE: SyncMode = "fast"


def normalize_sync_mode(value: str | None) -> SyncMode:
    token = (value or DEFAULT_SYNC_MODE).strip().lower()
    if token in {"fast", "standard", "full"}:
        return token  # type: ignore[return-value]
    return DEFAULT_SYNC_MODE


def fixture_query_params_for_mode(
    base_params: dict[str, Any],
    mode: SyncMode | None = None,
) -> dict[str, Any]:
    """Return API-Football fixtures params scoped by sync mode."""
    active = normalize_sync_mode(mode)
    params = dict(base_params)
    today = date.today()
    if active == "fast":
        params["from"] = today.isoformat()
        params["to"] = (today + timedelta(days=7)).isoformat()
        params.pop("season", None)
    elif active == "standard":
        params["from"] = (today - timedelta(days=30)).isoformat()
        params["to"] = (today + timedelta(days=7)).isoformat()
    # full: keep season/league only — manual backfill
    return params
