"""Sportmonks World Cup 2026 fixture enrichment — single-fixture fetch with SQLite cache."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.providers.sportmonks_provider import (
    WORLD_CUP_2026_LEAGUE_ID,
    WORLD_CUP_2026_SEASON_ID,
    SportmonksProvider,
)
from worldcup_predictor.quota.cache_policy import DAILY_TTL_SECONDS, MATCH_TTL_SECONDS

logger = logging.getLogger(__name__)

# High-value includes only — no predictions; odds deferred to later step.
WORLD_CUP_FIXTURE_INCLUDES: tuple[str, ...] = (
    "scores",
    "participants",
    "state",
    "statistics",
    "lineups",
    "events",
    "formations",
    "sidelined.sideline",
)

_FINISHED_STATE_SHORT_NAMES = frozenset(
    {"FT", "AET", "FT_PEN", "AWARDED", "ABANDONED", "CANCELLED", "POSTPONED"}
)


@dataclass(frozen=True)
class SportmonksFixtureEnrichmentResult:
    """Outcome of fetch_worldcup_fixture_enrichment — no secrets."""

    success: bool
    source: str
    sportmonks_fixture_id: int
    status_code: int | None
    endpoint_path: str
    includes: tuple[str, ...]
    keys_present: tuple[str, ...]
    raw_json_size: int
    message: str
    configured: bool


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _include_params_string() -> str:
    return ";".join(WORLD_CUP_FIXTURE_INCLUDES)


def _payload_keys_present(payload: Any) -> tuple[str, ...]:
    if not isinstance(payload, dict):
        return ()
    data = payload.get("data")
    if not isinstance(data, dict):
        return ()
    keys: list[str] = []
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, (list, dict, str)) and len(value) == 0:
            continue
        keys.append(str(key))
    return tuple(sorted(keys))


def _fixture_league_id(data: dict[str, Any]) -> int | None:
    league_id = data.get("league_id")
    if isinstance(league_id, int):
        return league_id
    if isinstance(league_id, str) and league_id.isdigit():
        return int(league_id)
    league = data.get("league")
    if isinstance(league, dict):
        nested = league.get("id")
        if isinstance(nested, int):
            return nested
        if isinstance(nested, str) and nested.isdigit():
            return int(nested)
    return None


def _is_world_cup_fixture(data: dict[str, Any]) -> bool:
    league_id = _fixture_league_id(data)
    return league_id == WORLD_CUP_2026_LEAGUE_ID


def _cache_ttl_seconds(data: dict[str, Any]) -> int:
    state = data.get("state")
    short_name = ""
    if isinstance(state, dict):
        short_name = str(state.get("short_name") or state.get("state") or "").upper()
    if short_name in _FINISHED_STATE_SHORT_NAMES:
        return DAILY_TTL_SECONDS
    return MATCH_TTL_SECONDS


def _result_from_cache_row(
    row: dict[str, Any],
    *,
    sportmonks_fixture_id: int,
) -> SportmonksFixtureEnrichmentResult:
    raw_json = row.get("raw_json") or ""
    try:
        payload = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        payload = None
    return SportmonksFixtureEnrichmentResult(
        success=True,
        source="cache",
        sportmonks_fixture_id=sportmonks_fixture_id,
        status_code=200,
        endpoint_path=str(row.get("endpoint") or f"/fixtures/{sportmonks_fixture_id}"),
        includes=tuple(str(row.get("include_params") or "").split(";")),
        keys_present=_payload_keys_present(payload),
        raw_json_size=len(raw_json),
        message="Loaded valid cache row (not expired).",
        configured=True,
    )


def fetch_worldcup_fixture_enrichment(
    sportmonks_fixture_id: int,
    *,
    fixture_id_api_football: int | None = None,
    settings: Settings | None = None,
    repo: FootballIntelligenceRepository | None = None,
    force_refresh: bool = False,
) -> SportmonksFixtureEnrichmentResult:
    """
    Fetch one World Cup fixture enrichment payload — cache-first, one API call max.

    Not wired into prediction pipeline.
    """
    settings = settings or get_settings()
    provider = SportmonksProvider(settings)
    endpoint_path = f"/fixtures/{int(sportmonks_fixture_id)}"
    includes = WORLD_CUP_FIXTURE_INCLUDES

    if not provider.is_configured:
        return SportmonksFixtureEnrichmentResult(
            success=False,
            source="none",
            sportmonks_fixture_id=sportmonks_fixture_id,
            status_code=None,
            endpoint_path=endpoint_path,
            includes=includes,
            keys_present=(),
            raw_json_size=0,
            message="Set SPORTMONKS_API_TOKEN in .env to enable Sportmonks enrichment.",
            configured=False,
        )

    repository = repo or FootballIntelligenceRepository(settings.sqlite_path or None)

    if not force_refresh:
        cached = repository.get_sportmonks_fixture_enrichment_cache(sportmonks_fixture_id)
        if cached:
            return _result_from_cache_row(cached, sportmonks_fixture_id=sportmonks_fixture_id)

    status_code, payload, error = provider.safe_get(
        endpoint_path,
        params={"include": _include_params_string()},
    )
    if error or not isinstance(payload, dict):
        return SportmonksFixtureEnrichmentResult(
            success=False,
            source="api",
            sportmonks_fixture_id=sportmonks_fixture_id,
            status_code=status_code,
            endpoint_path=endpoint_path,
            includes=includes,
            keys_present=(),
            raw_json_size=0,
            message=error or "empty Sportmonks response",
            configured=True,
        )

    data = payload.get("data")
    if not isinstance(data, dict):
        return SportmonksFixtureEnrichmentResult(
            success=False,
            source="api",
            sportmonks_fixture_id=sportmonks_fixture_id,
            status_code=status_code,
            endpoint_path=endpoint_path,
            includes=includes,
            keys_present=(),
            raw_json_size=0,
            message="Sportmonks response missing fixture data object.",
            configured=True,
        )

    if not _is_world_cup_fixture(data):
        league_id = _fixture_league_id(data)
        return SportmonksFixtureEnrichmentResult(
            success=False,
            source="api",
            sportmonks_fixture_id=sportmonks_fixture_id,
            status_code=status_code,
            endpoint_path=endpoint_path,
            includes=includes,
            keys_present=_payload_keys_present(payload),
            raw_json_size=len(json.dumps(payload)),
            message=(
                f"Fixture league_id={league_id} is not World Cup 2026 "
                f"(expected {WORLD_CUP_2026_LEAGUE_ID}). Not cached."
            ),
            configured=True,
        )

    raw_json = json.dumps(payload, ensure_ascii=False)
    fetched_at = _utc_now()
    ttl = _cache_ttl_seconds(data)
    expires_at = (fetched_at + timedelta(seconds=ttl)).isoformat()

    repository.save_sportmonks_fixture_enrichment(
        sportmonks_fixture_id=sportmonks_fixture_id,
        fixture_id_api_football=fixture_id_api_football,
        league_id=WORLD_CUP_2026_LEAGUE_ID,
        season_id=WORLD_CUP_2026_SEASON_ID,
        endpoint=endpoint_path,
        include_params=_include_params_string(),
        raw_json=raw_json,
        fetched_at_utc=fetched_at.isoformat(),
        expires_at_utc=expires_at,
        status="ok",
    )

    return SportmonksFixtureEnrichmentResult(
        success=True,
        source="api",
        sportmonks_fixture_id=sportmonks_fixture_id,
        status_code=status_code,
        endpoint_path=endpoint_path,
        includes=includes,
        keys_present=_payload_keys_present(payload),
        raw_json_size=len(raw_json),
        message="Fetched and cached World Cup fixture enrichment.",
        configured=True,
    )
