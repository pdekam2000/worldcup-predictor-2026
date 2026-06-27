"""Persist raw provider payloads — PostgreSQL when available, else local JSON cache."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.postgres.session import postgres_configured
from worldcup_predictor.egie.storage.repository import EgieRawStoreRepository
from worldcup_predictor.egie.world_cup.config import RAW_CACHE_DIR

logger = logging.getLogger(__name__)


_pg_save_disabled = False


def save_raw_with_fallback(
    *,
    settings: Settings | None = None,
    provider: str,
    resource_type: str,
    fixture_id: int,
    payload_json: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    global _pg_save_disabled
    settings = settings or get_settings()
    result: dict[str, Any] = {"postgres": False, "file_cache": False}

    if postgres_configured(settings) and not _pg_save_disabled:
        try:
            store = EgieRawStoreRepository(settings)
            save = store.save_raw_response(
                provider=provider,
                resource_type=resource_type,
                request_endpoint=kwargs.get("request_endpoint", ""),
                request_params=kwargs.get("request_params") or {},
                payload_json=payload_json,
                source=kwargs.get("source", "live"),
                competition_key=kwargs.get("competition_key"),
                league_id=kwargs.get("league_id"),
                season=kwargs.get("season"),
                fixture_id=fixture_id,
                sportmonks_fixture_id=kwargs.get("sportmonks_fixture_id"),
            )
            result["postgres"] = bool(save.saved or save.skipped_duplicate)
        except Exception as exc:
            logger.warning("egie_raw_postgres_save_failed fixture=%s: %s", fixture_id, exc)
            result["postgres_error"] = str(exc)[:200]
            _pg_save_disabled = True

    root = Path.cwd() / RAW_CACHE_DIR / provider / resource_type
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{fixture_id}.json"
    path.write_text(
        json.dumps(
            {
                "provider": provider,
                "resource_type": resource_type,
                "fixture_id": fixture_id,
                "saved_at": datetime.now(timezone.utc).isoformat(),
                "payload": payload_json,
                "meta": {k: v for k, v in kwargs.items() if k != "request_params"},
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    result["file_cache"] = True
    result["file_path"] = str(path)
    return result
