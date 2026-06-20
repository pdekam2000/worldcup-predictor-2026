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

# Phase 28B: base includes always requested; premium requested separately (403-safe).
BASE_WORLD_CUP_FIXTURE_INCLUDES: tuple[str, ...] = (
    "scores",
    "participants",
    "state",
    "statistics",
    "lineups",
    "events",
    "formations",
    "sidelined.sideline",
    "metadata",
)

PREMIUM_WORLD_CUP_FIXTURE_INCLUDES: tuple[str, ...] = (
    "odds",
    "predictions",
    "xGFixture",
)

# Full union — backward compatible export for audits/docs.
WORLD_CUP_FIXTURE_INCLUDES: tuple[str, ...] = (
    BASE_WORLD_CUP_FIXTURE_INCLUDES + PREMIUM_WORLD_CUP_FIXTURE_INCLUDES
)

PHASE_22C_REQUIRED_INCLUDES: tuple[str, ...] = ("odds", "predictions", "metadata")
PHASE_22D_REQUIRED_INCLUDES: tuple[str, ...] = ("xGFixture",)
CACHE_REQUIRED_INCLUDES: tuple[str, ...] = PHASE_22C_REQUIRED_INCLUDES + PHASE_22D_REQUIRED_INCLUDES
CACHE_BASE_REQUIRED_INCLUDES: tuple[str, ...] = BASE_WORLD_CUP_FIXTURE_INCLUDES

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
    premium_access: dict[str, bool] | None = None
    api_calls_made: int = 0


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
    premium_access: dict[str, bool] | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _include_params_string(*groups: tuple[str, ...]) -> str:
    if not groups:
        return ";".join(WORLD_CUP_FIXTURE_INCLUDES)
    merged: list[str] = []
    for group in groups:
        for token in group:
            if token not in merged:
                merged.append(token)
    return ";".join(merged)


def _cache_base_includes_complete(row: dict[str, Any]) -> bool:
    if int(row.get("base_enrichment_available") or 0):
        return True
    params = str(row.get("include_params") or "")
    return all(token in params for token in CACHE_BASE_REQUIRED_INCLUDES)


def _cache_includes_complete(row: dict[str, Any]) -> bool:
    """Legacy name — base cache sufficient for enrichment hit (Phase 28B)."""
    return _cache_base_includes_complete(row)


def _premium_access_from_row(row: dict[str, Any]) -> dict[str, bool]:
    return {
        "base_enrichment_available": bool(int(row.get("base_enrichment_available") or 0)),
        "premium_odds_available": bool(int(row.get("premium_odds_available") or 0)),
        "premium_predictions_available": bool(int(row.get("premium_predictions_available") or 0)),
        "premium_xg_available": bool(int(row.get("premium_xg_available") or 0)),
        "premium_odds_access_denied": bool(int(row.get("premium_odds_access_denied") or 0)),
        "premium_predictions_access_denied": bool(int(row.get("premium_predictions_access_denied") or 0)),
        "premium_xg_access_denied": bool(int(row.get("premium_xg_access_denied") or 0)),
    }


def _empty_premium_access(*, base: bool = False) -> dict[str, bool]:
    return {
        "base_enrichment_available": base,
        "premium_odds_available": False,
        "premium_predictions_available": False,
        "premium_xg_available": False,
        "premium_odds_access_denied": False,
        "premium_predictions_access_denied": False,
        "premium_xg_access_denied": False,
    }


def _is_access_denied(status_code: int | None, error: str | None) -> bool:
    if status_code == 403:
        return True
    if error and "403" in error:
        return True
    return False


def _denied_include_from_error(error: str | None) -> str | None:
    if not error:
        return None
    lowered = error.lower()
    for token in ("odds", "predictions", "xgfixture", "xGFixture".lower()):
        if f"'{token}'" in lowered or f'"{token}"' in lowered:
            return token
    return None


def _merge_premium_into_base(base: dict[str, Any], premium: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key in PREMIUM_WORLD_CUP_FIXTURE_INCLUDES:
        if key in premium and premium[key] not in (None, [], {}):
            merged[key] = premium[key]
    return merged


def _premium_flags_from_data(data: dict[str, Any], *, access_denied: bool) -> dict[str, bool]:
    from worldcup_predictor.providers.sportmonks_consumption import map_sportmonks_payload_fields

    fm = map_sportmonks_payload_fields(data)
    flags = _empty_premium_access(base=True)
    if access_denied:
        flags["premium_odds_access_denied"] = True
        flags["premium_predictions_access_denied"] = True
        flags["premium_xg_access_denied"] = True
        return flags
    flags["premium_odds_available"] = bool(fm.get("has_odds"))
    flags["premium_predictions_available"] = bool(fm.get("has_predictions"))
    flags["premium_xg_available"] = bool(fm.get("has_xg_fixture"))
    return flags


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
    premium_access = _premium_access_from_row(row)
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
        premium_access=premium_access,
        api_calls_made=0,
    )


def _fetch_fixture_include_group(
    provider: SportmonksProvider,
    endpoint_path: str,
    includes: tuple[str, ...],
) -> tuple[dict[str, Any] | None, int | None, str | None]:
    status_code, payload, error = provider.safe_get(
        endpoint_path,
        params={"include": _include_params_string(includes)},
    )
    if error or not isinstance(payload, dict):
        return None, status_code, error or "empty Sportmonks response"
    data = payload.get("data")
    if not isinstance(data, dict):
        return None, status_code, "Sportmonks response missing fixture data object."
    return data, status_code, None


def fetch_worldcup_fixture_enrichment(
    sportmonks_fixture_id: int,
    *,
    fixture_id_api_football: int | None = None,
    settings: Settings | None = None,
    repo: FootballIntelligenceRepository | None = None,
    force_refresh: bool = False,
) -> SportmonksFixtureEnrichmentResult:
    """
    Fetch World Cup fixture enrichment — cache-first, split base/premium includes.

    Phase 28B: base includes always fetched and cached; premium includes attempted
    separately. HTTP 403 on premium does not fail base enrichment.
    """
    settings = settings or get_settings()
    provider = SportmonksProvider(settings)
    endpoint_path = f"/fixtures/{int(sportmonks_fixture_id)}"
    all_includes = WORLD_CUP_FIXTURE_INCLUDES

    if not provider.is_configured:
        return SportmonksFixtureEnrichmentResult(
            success=False,
            source="none",
            sportmonks_fixture_id=sportmonks_fixture_id,
            status_code=None,
            endpoint_path=endpoint_path,
            includes=all_includes,
            keys_present=(),
            raw_json_size=0,
            message="Set SPORTMONKS_API_TOKEN in .env to enable Sportmonks enrichment.",
            configured=False,
        )

    repository = repo or FootballIntelligenceRepository(settings.sqlite_path or None)

    if not force_refresh:
        cached = repository.get_sportmonks_fixture_enrichment_cache(sportmonks_fixture_id)
        if cached and _cache_base_includes_complete(cached):
            return _result_from_cache_row(cached, sportmonks_fixture_id=sportmonks_fixture_id)

    base_data, base_status, base_error = _fetch_fixture_include_group(
        provider,
        endpoint_path,
        BASE_WORLD_CUP_FIXTURE_INCLUDES,
    )
    if base_data is None:
        return SportmonksFixtureEnrichmentResult(
            success=False,
            source="api",
            sportmonks_fixture_id=sportmonks_fixture_id,
            status_code=base_status,
            endpoint_path=endpoint_path,
            includes=all_includes,
            keys_present=(),
            raw_json_size=0,
            message=base_error or "base enrichment failed",
            configured=True,
        )

    if not _is_world_cup_fixture(base_data):
        league_id = _fixture_league_id(base_data)
        return SportmonksFixtureEnrichmentResult(
            success=False,
            source="api",
            sportmonks_fixture_id=sportmonks_fixture_id,
            status_code=base_status,
            endpoint_path=endpoint_path,
            includes=all_includes,
            keys_present=_payload_keys_present({"data": base_data}),
            raw_json_size=0,
            message=(
                f"Fixture league_id={league_id} is not World Cup 2026 "
                f"(expected {WORLD_CUP_2026_LEAGUE_ID}). Not cached."
            ),
            configured=True,
        )

    merged = dict(base_data)
    premium_access = _empty_premium_access(base=True)
    api_calls_made = 1

    premium_data, premium_status, premium_error = _fetch_fixture_include_group(
        provider,
        endpoint_path,
        PREMIUM_WORLD_CUP_FIXTURE_INCLUDES,
    )
    if premium_data is not None:
        merged = _merge_premium_into_base(merged, premium_data)
        premium_access = _premium_flags_from_data(merged, access_denied=False)
        api_calls_made = 2
    elif _is_access_denied(premium_status, premium_error):
        denied = _denied_include_from_error(premium_error)
        premium_access = _premium_flags_from_data(merged, access_denied=True)
        if denied == "odds":
            premium_access["premium_odds_access_denied"] = True
        elif denied == "predictions":
            premium_access["premium_predictions_access_denied"] = True
        elif denied in ("xgfixture", "xGFixture".lower()):
            premium_access["premium_xg_access_denied"] = True
        logger.info(
            "Sportmonks premium includes denied for fixture %s (403) — base enrichment cached.",
            sportmonks_fixture_id,
        )
        api_calls_made = 2
    else:
        logger.warning(
            "Sportmonks premium includes failed for fixture %s: %s",
            sportmonks_fixture_id,
            premium_error,
        )

    payload = {"data": merged}
    raw_json = json.dumps(payload, ensure_ascii=False)
    fetched_at = _utc_now()
    ttl = _cache_ttl_seconds(merged)
    expires_at = (fetched_at + timedelta(seconds=ttl)).isoformat()
    include_params = _include_params_string(BASE_WORLD_CUP_FIXTURE_INCLUDES, PREMIUM_WORLD_CUP_FIXTURE_INCLUDES)

    repository.save_sportmonks_fixture_enrichment(
        sportmonks_fixture_id=sportmonks_fixture_id,
        fixture_id_api_football=fixture_id_api_football,
        league_id=WORLD_CUP_2026_LEAGUE_ID,
        season_id=WORLD_CUP_2026_SEASON_ID,
        endpoint=endpoint_path,
        include_params=include_params,
        raw_json=raw_json,
        fetched_at_utc=fetched_at.isoformat(),
        expires_at_utc=expires_at,
        status="ok",
        base_enrichment_available=premium_access["base_enrichment_available"],
        premium_odds_available=premium_access["premium_odds_available"],
        premium_predictions_available=premium_access["premium_predictions_available"],
        premium_xg_available=premium_access["premium_xg_available"],
        premium_odds_access_denied=premium_access["premium_odds_access_denied"],
        premium_predictions_access_denied=premium_access["premium_predictions_access_denied"],
        premium_xg_access_denied=premium_access["premium_xg_access_denied"],
    )

    try:
        from pathlib import Path

        from worldcup_predictor.intelligence.sportmonks_xg_intelligence_engine import (
            save_xg_plan_probe,
            verify_xg_plan_access,
        )

        plan_probe = verify_xg_plan_access(merged)
        plan_probe["last_checked_utc"] = fetched_at.isoformat()
        plan_probe["sportmonks_fixture_id"] = sportmonks_fixture_id
        plan_probe["premium_access"] = premium_access
        cache_root = Path(settings.api_cache_dir) / "sportmonks"
        save_xg_plan_probe(cache_root, plan_probe)
    except Exception:
        logger.debug("Sportmonks xG plan probe save skipped", exc_info=True)

    msg = "Fetched and cached World Cup base enrichment."
    if premium_access.get("premium_odds_available") or premium_access.get("premium_predictions_available"):
        msg += " Premium odds/predictions included."
    elif premium_access.get("premium_odds_access_denied") or premium_access.get("premium_predictions_access_denied"):
        msg += " Premium odds/predictions blocked by plan (403)."
    if premium_access.get("premium_xg_available"):
        msg += " xGFixture included."
    elif premium_access.get("premium_xg_access_denied"):
        msg += " xGFixture blocked by plan (403)."

    return SportmonksFixtureEnrichmentResult(
        success=True,
        source="api",
        sportmonks_fixture_id=sportmonks_fixture_id,
        status_code=base_status,
        endpoint_path=endpoint_path,
        includes=all_includes,
        keys_present=_payload_keys_present(payload),
        raw_json_size=len(raw_json),
        message=msg,
        configured=True,
        fixture=merged,
        premium_access=premium_access,
        api_calls_made=api_calls_made,
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
    enrichment_force = force_refresh
    prefetch_sm_id: int | None = None

    if not force_refresh:
        row = repository.get_sportmonks_fixture_enrichment_by_api_fixture_id(int(api_fixture_id))
        if row:
            fixture = _fixture_data_from_cache_row(row)
            sm_id = int(row.get("sportmonks_fixture_id") or 0) or None
            if fixture and sm_id and _cache_base_includes_complete(row):
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
                    premium_access=_premium_access_from_row(row),
                )
            if sm_id and not _cache_base_includes_complete(row):
                prefetch_sm_id = sm_id
                enrichment_force = True

    if prefetch_sm_id is not None:
        enrichment = fetch_worldcup_fixture_enrichment(
            prefetch_sm_id,
            fixture_id_api_football=int(api_fixture_id),
            settings=settings,
            repo=repository,
            force_refresh=enrichment_force,
        )
        if enrichment.source == "api" and enrichment.success:
            api_calls += enrichment.api_calls_made or 1
        if enrichment.success and enrichment.fixture:
            return UnifiedFixtureIntelligenceResult(
                success=True,
                fixture=enrichment.fixture,
                sportmonks_fixture_id=prefetch_sm_id,
                source_chain=("sqlite_incomplete_refresh", f"enrichment_{enrichment.source}"),
                endpoint_primary=enrichment.endpoint_path,
                lookup_endpoint=None,
                enrichment_endpoint=enrichment.endpoint_path,
                api_calls_made=api_calls,
                includes=enrichment.includes,
                keys_present=enrichment.keys_present,
                message=enrichment.message,
                configured=True,
                premium_access=enrichment.premium_access,
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
        force_refresh=force_refresh or enrichment_force,
    )
    if enrichment.source == "api" and enrichment.success:
        api_calls += enrichment.api_calls_made or 1

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
            premium_access=enrichment.premium_access,
        )

    # Phase 28B: lookup fallback only when base enrichment failed — not premium 403.
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
            message=f"Base enrichment failed ({enrichment.message}); using date-lookup payload.",
            configured=True,
            premium_access=enrichment.premium_access,
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
