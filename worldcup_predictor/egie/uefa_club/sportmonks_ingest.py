"""STEP 3 — Sportmonks UEFA feature ingest (cache-first, resumable)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.egie.config import PROVIDER_SPORTMONKS
from worldcup_predictor.egie.storage.repository import EgieRawStoreRepository
from worldcup_predictor.egie.uefa_club.config import RAW_CACHE_DIR, UEFA_FULL_INCLUDES
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider

logger = logging.getLogger(__name__)


def uefa_data_root(settings: Settings) -> Path:
    return Path.cwd() / "data"


def cache_path(settings: Settings, sportmonks_fixture_id: int) -> Path:
    primary = uefa_data_root(settings) / "egie" / "uefa_club" / "raw" / f"{sportmonks_fixture_id}.json"
    legacy = uefa_data_root(settings) / "data" / "egie" / "uefa_club" / "raw" / f"{sportmonks_fixture_id}.json"
    if legacy.is_file() and not primary.is_file():
        return legacy
    return primary


def load_cache(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def ingest_uefa_sportmonks_features(
    fixtures: list[dict[str, Any]],
    *,
    settings: Settings | None = None,
    max_api_calls: int = 120,
    force_refresh: bool = False,
) -> dict[str, Any]:
    settings = settings or get_settings()
    provider = SportmonksProvider(settings)
    store = EgieRawStoreRepository(settings)
    api_calls = 0
    saved = 0
    skipped_cache = 0
    skipped_cap = 0
    errors: list[str] = []

    for fx in fixtures:
        sm_id = int(fx.get("sportmonks_fixture_id") or fx.get("fixture_id") or 0)
        if sm_id <= 0:
            continue
        cache_file = cache_path(settings, sm_id)
        cached = None if force_refresh else load_cache(cache_file)

        if cached is None:
            if api_calls >= max_api_calls:
                skipped_cap += 1
                continue
            endpoint = f"/fixtures/{sm_id}"
            status, payload, error = provider.safe_get(
                endpoint,
                params={"include": UEFA_FULL_INCLUDES},
            )
            api_calls += 1
            if error or not isinstance(payload, dict) or not payload.get("data"):
                errors.append(f"{sm_id}:{error or payload.get('message', 'no_data')}"[:120])
                continue
            cached = {
                "sportmonks_fixture_id": sm_id,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "status_code": status,
                "payload": payload,
            }
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(cached, indent=2, default=str), encoding="utf-8")
        else:
            skipped_cache += 1

        envelope = {
            "endpoint": f"/fixtures/{sm_id}",
            "includes": UEFA_FULL_INCLUDES,
            "response": cached.get("payload"),
            "source": "uefa_club_ingest",
        }
        comp_key = str(fx.get("competition_key") or "champions_league")
        league_id = int(fx.get("league_id") or 0)
        season = int(fx.get("season_id") or 0) if fx.get("season_id") else None

        save = store.save_raw_response(
            provider=PROVIDER_SPORTMONKS,
            resource_type="fixture_enrichment",
            request_endpoint=f"/fixtures/{sm_id}",
            request_params={"sportmonks_fixture_id": sm_id, "include": UEFA_FULL_INCLUDES},
            payload_json=envelope,
            source="cache" if skipped_cache else "live",
            competition_key=comp_key,
            league_id=league_id or None,
            season=season,
            fixture_id=sm_id,
            sportmonks_fixture_id=sm_id,
        )
        if save.saved or save.skipped_duplicate:
            saved += 1

    return {
        "fixtures_targeted": len(fixtures),
        "api_calls_live": api_calls,
        "fixtures_cached_or_saved": saved + skipped_cache,
        "skipped_cache_hits": skipped_cache,
        "skipped_api_cap": skipped_cap,
        "errors_sample": errors[:20],
    }
