"""SQLite durable store for World Cup prediction payloads — Phase 33."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.automation.worldcup_background.freshness import is_prediction_fresh
from worldcup_predictor.automation.worldcup_background.prediction_store_guard import evaluate_prediction_storage
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.quota.prediction_cache import kickoff_from_payload


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


class WorldcupPredictionStore:
    """Dual-layer store: SQLite primary + existing file cache for API fast path."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._repo = FootballIntelligenceRepository(self._settings.sqlite_path or None)

    def get(
        self,
        fixture_id: int,
        *,
        competition_key: str = "world_cup_2026",
        season: int = 2026,
        locale: str = "en",
    ) -> dict[str, Any] | None:
        row = self._repo.get_worldcup_stored_prediction(fixture_id)
        if row and row.get("payload_json"):
            try:
                payload = json.loads(row["payload_json"])
                kick = kickoff_from_payload(payload)
                fresh, reason = is_prediction_fresh(payload, kickoff_utc=kick)
                if fresh:
                    from worldcup_predictor.automation.worldcup_background.stale_prediction_policy import (
                        is_stored_prediction_quality_valid,
                    )

                    quality_ok, quality_reason = is_stored_prediction_quality_valid(payload)
                    if not quality_ok:
                        return None
                    out = dict(payload)
                    out["cache_source"] = "sqlite_store"
                    out["cache_validated"] = True
                    out["cache_validation_reason"] = reason
                    out["quality_validation_reason"] = quality_reason
                    return out
            except (json.JSONDecodeError, TypeError):
                pass

        from worldcup_predictor.quota.prediction_cache import get_cached_prediction

        cached = get_cached_prediction(
            fixture_id,
            competition_key=competition_key,
            season=season,
            locale=locale,
            settings=self._settings,
        )
        if cached is None:
            return None
        kick = kickoff_from_payload(cached)
        fresh, reason = is_prediction_fresh(cached, kickoff_utc=kick)
        if not fresh:
            return None
        out = dict(cached)
        out["cache_validation_reason"] = reason
        return out

    def upsert(
        self,
        fixture_id: int,
        payload: dict[str, Any],
        *,
        kickoff_utc: str | None = None,
        source: str = "background",
        prediction_is_placeholder: bool | None = None,
    ) -> tuple[bool, str]:
        existing_payload: dict[str, Any] | None = None
        existing_row = self._repo.get_worldcup_stored_prediction(fixture_id, include_inactive=True)
        if existing_row and existing_row.get("payload_json"):
            try:
                existing_payload = json.loads(existing_row["payload_json"])
            except (json.JSONDecodeError, TypeError):
                existing_payload = None

        allow, reason = evaluate_prediction_storage(
            payload,
            settings=self._settings,
            prediction_is_placeholder=prediction_is_placeholder,
            existing_payload=existing_payload,
        )
        if not allow:
            return False, reason

        if "cached_at" not in payload:
            payload["cached_at"] = time.time()
        self._repo.upsert_worldcup_stored_prediction(
            fixture_id=fixture_id,
            payload=payload,
            kickoff_utc=kickoff_utc or payload.get("kickoff_utc"),
            source=source,
            predicted_at=payload.get("predicted_at") or _utc_now(),
        )
        return True, "ok"

    def list_in_window(
        self,
        *,
        competition_key: str = "world_cup_2026",
        window_days: int = 3,
        season: int | None = 2026,
    ) -> list[dict[str, Any]]:
        return self._repo.list_fixtures_in_kickoff_window(
            competition_key,
            window_days=window_days,
            season=season,
        )
