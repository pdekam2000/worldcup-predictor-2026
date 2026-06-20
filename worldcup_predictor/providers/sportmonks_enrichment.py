"""Sportmonks World Cup 2026 fixture enrichment — unified cache-first intelligence path."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.providers.sportmonks_fixture_lookup import lookup_world_cup_fixture
from worldcup_predictor.providers.sportmonks_provider import (
    WORLD_CUP_2026_COMPETITION_KEY,
    WORLD_CUP_2026_LEAGUE_ID,
    WORLD_CUP_2026_SEASON_ID,
    SportmonksProvider,
)
from worldcup_predictor.quota.cache_policy import DAILY_TTL_SECONDS, MATCH_TTL_SECONDS

logger = logging.getLogger(__name__)

# Phase 22C/22D: supplemental intelligence includes (benchmark + xG).
WORLD_CUP_FIXTURE_INCLUDES: tuple[str, ...] = (
    "scores",
    "participants",
    "state",
    "statistics",
    "lineups",
    "events",
    "formations",
    "sidelined.sideline",
    "odds",
    "predictions",
    "metadata",
    "xGFixture",
)

PHASE_22C_REQUIRED_INCLUDES: tuple[str, ...] = ("odds", "predictions", "metadata")
PHASE_22D_REQUIRED_INCLUDES: tuple[str, ...] = ("xGFixture",)
CACHE_REQUIRED_INCLUDES: tuple[str, ...] = PHASE_22C_REQUIRED_INCLUDES + PHASE_22D_REQUIRED_INCLUDES

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
    fixture: dict[str, Any] | None = None


@dataclass(frozen=True)
class UnifiedFixtureIntelligenceResult:
    """Phase 22B — lookup then fixture-by-ID enrichment; cache-first, no duplicate fetches."""

    success: bool
    fixture: dict[str, Any] | None
    sportmonks_fixture_id: int | None
    source_chain: tuple[str, ...]
    endpoint_primary: str
    lookup_endpoint: str | None
    enrichment_endpoint: str | None
    api_calls_made: int
    includes: tuple[str, ...]
    keys_present: tuple[str, ...]
    message: str
    configured: bool


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _include_params_string() -> str:
    return ";".join(WORLD_CUP_FIXTURE_INCLUDES)


def _cache_includes_complete(row: dict[str, Any]) -> bool:
    params = str(row.get("include_params") or "")
    return all(token in params for token in CACHE_REQUIRED_INCLUDES)


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


def _fixture_data_from_cache_row(row: dict[str, Any]) -> dict[str, Any] | None:
    raw_json = row.get("raw_json") or ""
    try:
        payload = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return None
    data = payload.get("data") if isinstance(payload, dict) else None
    return data if isinstance(data, dict) else None


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
    fixture = _fixture_data_from_cache_row(row)
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
        fixture=fixture,
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

    Used by the Phase 22B unified intelligence path after fixture ID resolution.
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
        if cached and _cache_includes_complete(cached):
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

    try:
        from pathlib import Path

        from worldcup_predictor.intelligence.sportmonks_xg_intelligence_engine import (
            save_xg_plan_probe,
            verify_xg_plan_access,
        )

        plan_probe = verify_xg_plan_access(data)
        plan_probe["last_checked_utc"] = fetched_at.isoformat()
        plan_probe["sportmonks_fixture_id"] = sportmonks_fixture_id
        cache_root = Path(settings.api_cache_dir) / "sportmonks"
        save_xg_plan_probe(cache_root, plan_probe)
    except Exception:
        logger.debug("Sportmonks xG plan probe save skipped", exc_info=True)

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
        fixture=data,
    )


def resolve_unified_worldcup_fixture_intelligence(
    *,
    api_fixture_id: int,
    home_team: str,
    away_team: str,
    kickoff_date: str | None = None,
    competition_key: str | None = None,
    settings: Settings | None = None,
    repo: FootballIntelligenceRepository | None = None,
    force_refresh: bool = False,
) -> UnifiedFixtureIntelligenceResult:
    """
    Phase 22B unified path: resolve Sportmonks fixture ID, then load full fixture payload.

    Order (cache-first, min API calls):
      1. SQLite by API-Football fixture ID (skip lookup + fetch)
      2. Date lookup → Sportmonks fixture ID (file cache)
      3. SQLite by Sportmonks fixture ID
      4. GET /fixtures/{id} (single enrichment call, then cache)

    Falls back to lookup partial payload only if enrichment fetch fails.
    """
    settings = settings or get_settings()
    includes = WORLD_CUP_FIXTURE_INCLUDES
    provider = SportmonksProvider(settings)

    if not provider.is_configured:
        return UnifiedFixtureIntelligenceResult(
            success=False,
            fixture=None,
            sportmonks_fixture_id=None,
            source_chain=(),
            endpoint_primary="fixtures/unified",
            lookup_endpoint=None,
            enrichment_endpoint=None,
            api_calls_made=0,
            includes=includes,
            keys_present=(),
            message="Set SPORTMONKS_API_TOKEN in .env to enable Sportmonks enrichment.",
            configured=False,
        )

    if competition_key and competition_key != WORLD_CUP_2026_COMPETITION_KEY:
        return UnifiedFixtureIntelligenceResult(
            success=False,
            fixture=None,
            sportmonks_fixture_id=None,
            source_chain=("competition_skipped",),
            endpoint_primary="fixtures/unified",
            lookup_endpoint=None,
            enrichment_endpoint=None,
            api_calls_made=0,
            includes=includes,
            keys_present=(),
            message=f"Sportmonks enrichment limited to {WORLD_CUP_2026_COMPETITION_KEY}.",
            configured=True,
        )

    repository = repo or FootballIntelligenceRepository(settings.sqlite_path or None)
    api_calls = 0

    if not force_refresh:
        row = repository.get_sportmonks_fixture_enrichment_by_api_fixture_id(int(api_fixture_id))
        if row:
            fixture = _fixture_data_from_cache_row(row)
            sm_id = int(row.get("sportmonks_fixture_id") or 0) or None
            if fixture and sm_id and _cache_includes_complete(row):
                try:
                    payload = json.loads(row["raw_json"])
                except (json.JSONDecodeError, TypeError, KeyError):
                    payload = None
                return UnifiedFixtureIntelligenceResult(
                    success=True,
                    fixture=fixture,
                    sportmonks_fixture_id=sm_id,
                    source_chain=("sqlite_by_api_fixture_id",),
                    endpoint_primary=str(row.get("endpoint") or f"/fixtures/{sm_id}"),
                    lookup_endpoint=None,
                    enrichment_endpoint=str(row.get("endpoint") or f"/fixtures/{sm_id}"),
                    api_calls_made=0,
                    includes=tuple(str(row.get("include_params") or "").split(";")),
                    keys_present=_payload_keys_present(payload),
                    message="Unified path: SQLite hit by API-Football fixture ID.",
                    configured=True,
                )

    lookup = lookup_world_cup_fixture(
        api_fixture_id=int(api_fixture_id),
        home_team=home_team,
        away_team=away_team,
        kickoff_date=kickoff_date,
        settings=settings,
    )
    if not lookup.found or lookup.sportmonks_fixture_id is None:
        return UnifiedFixtureIntelligenceResult(
            success=False,
            fixture=None,
            sportmonks_fixture_id=lookup.sportmonks_fixture_id,
            source_chain=("lookup_not_found",),
            endpoint_primary=lookup.endpoint,
            lookup_endpoint=lookup.endpoint,
            enrichment_endpoint=None,
            api_calls_made=0 if lookup.from_cache else 1,
            includes=includes,
            keys_present=(),
            message=lookup.reason or "Sportmonks fixture not found.",
            configured=True,
        )

    if not lookup.from_cache:
        api_calls += 1

    sm_id = int(lookup.sportmonks_fixture_id)
    enrichment = fetch_worldcup_fixture_enrichment(
        sm_id,
        fixture_id_api_football=int(api_fixture_id),
        settings=settings,
        repo=repository,
        force_refresh=force_refresh,
    )
    if enrichment.source == "api" and enrichment.success:
        api_calls += 1

    if enrichment.success and enrichment.fixture:
        return UnifiedFixtureIntelligenceResult(
            success=True,
            fixture=enrichment.fixture,
            sportmonks_fixture_id=sm_id,
            source_chain=(
                "lookup_cache" if lookup.from_cache else "lookup_api",
                f"enrichment_{enrichment.source}",
            ),
            endpoint_primary=enrichment.endpoint_path,
            lookup_endpoint=lookup.endpoint,
            enrichment_endpoint=enrichment.endpoint_path,
            api_calls_made=api_calls,
            includes=enrichment.includes,
            keys_present=enrichment.keys_present,
            message=enrichment.message,
            configured=True,
        )

    if lookup.fixture:
        logger.warning(
            "Sportmonks enrichment failed for fixture %s — using lookup fallback payload",
            sm_id,
        )
        return UnifiedFixtureIntelligenceResult(
            success=True,
            fixture=lookup.fixture,
            sportmonks_fixture_id=sm_id,
            source_chain=(
                "lookup_cache" if lookup.from_cache else "lookup_api",
                "enrichment_failed_lookup_fallback",
            ),
            endpoint_primary=lookup.endpoint,
            lookup_endpoint=lookup.endpoint,
            enrichment_endpoint=enrichment.endpoint_path,
            api_calls_made=api_calls,
            includes=includes,
            keys_present=tuple(sorted(k for k in lookup.fixture if lookup.fixture.get(k))),
            message=f"Enrichment failed ({enrichment.message}); using date-lookup payload.",
            configured=True,
        )

    return UnifiedFixtureIntelligenceResult(
        success=False,
        fixture=None,
        sportmonks_fixture_id=sm_id,
        source_chain=("lookup_ok", "enrichment_failed"),
        endpoint_primary=enrichment.endpoint_path,
        lookup_endpoint=lookup.endpoint,
        enrichment_endpoint=enrichment.endpoint_path,
        api_calls_made=api_calls,
        includes=includes,
        keys_present=(),
        message=enrichment.message,
        configured=True,
    )
