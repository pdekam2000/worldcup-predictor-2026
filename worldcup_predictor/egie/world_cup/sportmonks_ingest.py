"""Sportmonks bulk import for World Cup fixtures — cache-first."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.egie.config import PROVIDER_SPORTMONKS
from worldcup_predictor.egie.world_cup.raw_cache import save_raw_with_fallback
from worldcup_predictor.egie.uefa_club.config import UEFA_FULL_INCLUDES
from worldcup_predictor.egie.world_cup.config import RAW_CACHE_DIR, SPORTMONKS_LEAGUE_ID, WORLD_CUP_COMPETITION_KEY
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider

logger = logging.getLogger(__name__)


def cache_root(settings: Settings) -> Path:
    return Path.cwd() / RAW_CACHE_DIR


def ingest_sportmonks_wc_fixtures(
    fixtures: list[dict[str, Any]],
    *,
    settings: Settings | None = None,
    max_api_calls: int = 80,
) -> dict[str, Any]:
    settings = settings or get_settings()
    provider = SportmonksProvider(settings)
    store = None
    root = cache_root(settings)
    root.mkdir(parents=True, exist_ok=True)
    api_calls = 0
    saved = 0
    cache_hits = 0
    errors: list[str] = []

    if not getattr(provider, "is_configured", False):
        return {"status": "skipped", "reason": "sportmonks_not_configured"}

    for fx in fixtures:
        sm_id = int(fx.get("sportmonks_fixture_id") or fx.get("fixture_id") or 0)
        if sm_id <= 0:
            continue
        cache_file = root / f"{sm_id}.json"
        cached = None
        from_cache = False
        if cache_file.is_file():
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                from_cache = True
                cache_hits += 1
            except (json.JSONDecodeError, OSError):
                cached = None
        if cached is None:
            if api_calls >= max_api_calls:
                break
            status, payload, error = provider.safe_get(
                f"/fixtures/{sm_id}",
                params={"include": UEFA_FULL_INCLUDES},
            )
            api_calls += 1
            if error or not isinstance(payload, dict) or not payload.get("data"):
                errors.append(f"{sm_id}:{error or 'no_data'}"[:100])
                continue
            cached = {
                "sportmonks_fixture_id": sm_id,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "payload": payload,
            }
            cache_file.write_text(json.dumps(cached, indent=2, default=str), encoding="utf-8")

        envelope = {
            "sportmonks_fixture_id": sm_id,
            "fetched_at": cached.get("fetched_at"),
            "response": cached.get("payload"),
            "source": "world_cup_ingest",
        }
        save_raw_with_fallback(
            settings=settings,
            provider=PROVIDER_SPORTMONKS,
            resource_type="fixture_enrichment",
            fixture_id=int(fx.get("api_football_fixture_id") or fx.get("fixture_id") or sm_id),
            payload_json=envelope,
            request_endpoint=f"/fixtures/{sm_id}",
            request_params={"include": UEFA_FULL_INCLUDES},
            source="cache" if from_cache else "live",
            sportmonks_fixture_id=sm_id,
            competition_key=WORLD_CUP_COMPETITION_KEY,
            league_id=SPORTMONKS_LEAGUE_ID,
            season=int(fx.get("season") or 0) or None,
        )
        saved += 1

    return {
        "status": "ok",
        "saved": saved,
        "cache_hits": cache_hits,
        "api_calls": api_calls,
        "errors": errors[:15],
    }
