"""API-Football provider backfill for EGIE PL fixtures — cache-first, resumable."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.backtesting.phase31e_backfill import (
    backfill_odds_from_cache,
    collect_cached_odds_sources,
    normalize_odds_bookmakers,
)
from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.competitions import PREMIER_LEAGUE, get_competition
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.egie.config import PROVIDER_API_FOOTBALL
from worldcup_predictor.egie.storage.repository import EgieRawStoreRepository
from worldcup_predictor.cache.api_cache import ApiCache

logger = logging.getLogger(__name__)

_FINISHED = ("FT", "AET", "PEN", "FINISHED", "AWD", "WO")
_RESOURCE_ENDPOINTS: list[tuple[str, str, str]] = [
    ("events", "fixtures/events", "get_fixture_events"),
    ("lineups", "fixtures/lineups", "get_fixture_lineups"),
    ("fixture_statistics", "fixtures/statistics", "get_fixture_statistics"),
    ("injuries", "injuries", "get_injuries"),
]


def _pl_fixture_targets(
    repo: FootballIntelligenceRepository,
    *,
    fixture_ids: list[int] | None,
    limit: int | None,
    league_id: int | None = None,
    season: int | None = None,
) -> list[dict[str, Any]]:
    ph = ",".join("?" * len(_FINISHED))
    q = f"""
        SELECT fixture_id, home_team, away_team, kickoff_utc, season, league_id
        FROM fixtures
        WHERE competition_key = 'premier_league' AND is_placeholder = 0
          AND status IN ({ph})
    """
    params: list[Any] = list(_FINISHED)
    if league_id is not None:
        q += " AND league_id = ?"
        params.append(int(league_id))
    if season is not None:
        q += " AND season = ?"
        params.append(int(season))
    if fixture_ids:
        ids_ph = ",".join("?" * len(fixture_ids))
        q += f" AND fixture_id IN ({ids_ph})"
        params.extend(fixture_ids)
    q += " ORDER BY kickoff_utc ASC"
    if limit:
        q += " LIMIT ?"
        params.append(int(limit))
    return [dict(r) for r in repo._conn.execute(q, params).fetchall()]


def _has_pl_odds(repo: FootballIntelligenceRepository, fixture_id: int) -> bool:
    return bool(
        repo._conn.execute(
            "SELECT 1 FROM odds_snapshots WHERE fixture_id = ? LIMIT 1",
            (fixture_id,),
        ).fetchone()
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def backfill_pl_odds_from_cache(
    repo: FootballIntelligenceRepository,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Import cached odds only for premier_league fixture_ids."""
    settings = settings or get_settings()
    disk_cache = ApiCache(Path(settings.api_cache_dir)) if settings.api_cache_dir else None
    all_sources = collect_cached_odds_sources(repo, disk_cache=disk_cache)

    pl_ids = {
        int(r[0])
        for r in repo._conn.execute(
            "SELECT fixture_id FROM fixtures WHERE competition_key = 'premier_league' AND is_placeholder = 0"
        ).fetchall()
    }
    pl_sources = {fid: entry for fid, entry in all_sources.items() if fid in pl_ids}

    created = 0
    skipped = 0
    for fid, entry in pl_sources.items():
        if _has_pl_odds(repo, fid):
            skipped += 1
            continue
        bookmakers = entry["bookmakers"]
        payload = {
            "snapshot_at": entry.get("cached_at") or _utc_now(),
            "source": "api_f_pl_cache_backfill",
            "cache_source": entry["source"],
            "bookmakers": bookmakers,
            "api_sports": {"bookmakers": bookmakers},
        }
        repo.save_snapshot(
            "odds_snapshots",
            fixture_id=fid,
            competition_key="premier_league",
            payload=payload,
        )
        created += 1

    return {
        "pl_fixtures_with_cached_odds": len(pl_sources),
        "odds_snapshots_created": created,
        "odds_snapshots_skipped_existing": skipped,
    }


def _count_pl_odds_fixtures(repo: FootballIntelligenceRepository) -> int:
    row = repo._conn.execute(
        """
        SELECT COUNT(DISTINCT o.fixture_id)
        FROM odds_snapshots o
        JOIN fixtures f ON f.fixture_id = o.fixture_id
        WHERE f.competition_key = 'premier_league' AND f.is_placeholder = 0
        """
    ).fetchone()
    return int(row[0] or 0)


def _append_manifest_line(manifest_path: Path | None, entry: dict[str, Any]) -> None:
    if manifest_path is None:
        return
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def run_pl_odds_backfill(
    *,
    fixture_ids: list[int] | None = None,
    limit_fixtures: int | None = None,
    max_api_calls: int = 400,
    league_id: int | None = None,
    season: int | None = None,
    manifest_path: Path | str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Phase 54C-1 — odds-only PL backfill (cache-first, resumable, no other resources)."""
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    client = ApiFootballClient(settings)
    comp = get_competition("premier_league") or PREMIER_LEAGUE
    resolved_league_id = league_id
    resolved_season = season
    manifest = Path(manifest_path) if manifest_path else None
    if manifest and manifest.exists():
        manifest.unlink()

    pl_odds_before = _count_pl_odds_fixtures(repo)
    targets = _pl_fixture_targets(
        repo,
        fixture_ids=fixture_ids,
        limit=limit_fixtures,
        league_id=resolved_league_id,
        season=resolved_season,
    )

    api_calls_live = 0
    api_calls_cache = 0
    skipped_existing = 0
    skipped_cap = 0
    snapshots_created = 0
    snapshots_empty = 0
    snapshots_error = 0

    odds_cache = backfill_pl_odds_from_cache(repo, settings=settings)
    cache_created = int(odds_cache.get("odds_snapshots_created") or 0)
    snapshots_created += cache_created

    for row in targets:
        fid = int(row["fixture_id"])
        if _has_pl_odds(repo, fid):
            skipped_existing += 1
            _append_manifest_line(
                manifest,
                {
                    "fixture_id": fid,
                    "status": "skipped_existing",
                    "source": None,
                    "api_source": None,
                    "timestamp": _utc_now(),
                },
            )
            continue

        if api_calls_live >= max_api_calls:
            skipped_cap += 1
            _append_manifest_line(
                manifest,
                {
                    "fixture_id": fid,
                    "status": "skipped_cap",
                    "source": None,
                    "api_source": None,
                    "timestamp": _utc_now(),
                },
            )
            continue

        api = client._safe_get(
            "odds",
            {"fixture": fid},
            placeholder_factory=lambda: [],
            force_refresh=False,
        )
        api_source = str(getattr(api, "source", None) or "unknown")

        # Retry live when cache/local returned an empty odds list.
        if api_source in ("cache", "local") and not normalize_odds_bookmakers(api.data):
            api = client._safe_get(
                "odds",
                {"fixture": fid},
                placeholder_factory=lambda: [],
                force_refresh=True,
            )
            api_source = str(getattr(api, "source", None) or "unknown")

        if api_source == "live":
            api_calls_live += 1
        elif api_source in ("cache", "local"):
            api_calls_cache += 1

        if api.error:
            snapshots_error += 1
            _append_manifest_line(
                manifest,
                {
                    "fixture_id": fid,
                    "status": "error",
                    "source": None,
                    "api_source": api_source,
                    "error": api.error,
                    "timestamp": _utc_now(),
                },
            )
            continue

        bookmakers = normalize_odds_bookmakers(api.data)
        if not bookmakers:
            disk_cache = ApiCache(Path(settings.api_cache_dir)) if settings.api_cache_dir else None
            pl_cache = collect_cached_odds_sources(repo, disk_cache=disk_cache).get(fid)
            if pl_cache and pl_cache.get("bookmakers"):
                bookmakers = pl_cache["bookmakers"]
                api_source = "cache_fallback"
                source_tag = "api_f_pl_cache_backfill"
            else:
                snapshots_empty += 1
                _append_manifest_line(
                    manifest,
                    {
                        "fixture_id": fid,
                        "status": "empty",
                        "source": None,
                        "api_source": api_source,
                        "timestamp": _utc_now(),
                    },
                )
                continue
        else:
            source_tag = (
                "api_f_pl_cache_backfill"
                if api_source in ("cache", "local", "cache_fallback")
                else "api_football_live_backfill"
            )

        repo.save_snapshot(
            "odds_snapshots",
            fixture_id=fid,
            competition_key="premier_league",
            payload={
                "snapshot_at": _utc_now(),
                "source": source_tag,
                "bookmakers": bookmakers,
                "api_sports": {"bookmakers": bookmakers},
            },
        )
        snapshots_created += 1
        _append_manifest_line(
            manifest,
            {
                "fixture_id": fid,
                "status": "created",
                "source": source_tag,
                "api_source": api_source,
                "bookmaker_count": len(bookmakers),
                "timestamp": _utc_now(),
            },
        )

    pl_odds_after = _count_pl_odds_fixtures(repo)

    return {
        "phase": "54C-1",
        "mode": "odds_only",
        "competition_key": "premier_league",
        "league_id": resolved_league_id,
        "season": resolved_season,
        "targets": len(targets),
        "pl_odds_fixtures_before": pl_odds_before,
        "pl_odds_fixtures_after": pl_odds_after,
        "pl_odds_snapshot_fixtures": pl_odds_after,
        "odds_snapshots_created": snapshots_created,
        "odds_snapshots_skipped_existing": skipped_existing,
        "odds_snapshots_empty": snapshots_empty,
        "odds_snapshots_error": snapshots_error,
        "skipped_api_cap": skipped_cap,
        "api_calls_live": api_calls_live,
        "api_calls_cache": api_calls_cache,
        "pl_odds_cache_backfill": odds_cache,
        "manifest_path": str(manifest) if manifest else None,
        "finished_at": _utc_now(),
    }


def run_api_football_pl_backfill(
    *,
    fixture_ids: list[int] | None = None,
    limit_fixtures: int | None = None,
    max_api_calls: int = 80,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    store = EgieRawStoreRepository(settings)
    client = ApiFootballClient(settings)
    comp = get_competition("premier_league") or PREMIER_LEAGUE
    season = int(comp.season)
    targets = _pl_fixture_targets(repo, fixture_ids=fixture_ids, limit=limit_fixtures)

    api_calls = 0
    resource_saved: dict[str, int] = {}
    skipped_existing = 0
    skipped_cap = 0
    odds_live = 0
    odds_cache = backfill_pl_odds_from_cache(repo, settings=settings)

    for row in targets:
        fid = int(row["fixture_id"])
        league_id = comp.league_id

        for resource_type, endpoint, method_name in _RESOURCE_ENDPOINTS:
            if store.get_latest_raw(
                provider=PROVIDER_API_FOOTBALL,
                resource_type=resource_type,
                fixture_id=fid,
            ):
                skipped_existing += 1
                continue
            if api_calls >= max_api_calls:
                skipped_cap += 1
                continue

            if method_name == "get_injuries":
                api = client.get_injuries(fid, league_id=league_id, season=season)
            else:
                api = getattr(client, method_name)(fid)

            if getattr(api, "source", None) == "live":
                api_calls += 1
            if api.skip_reason or api.data is None:
                continue

            envelope = {
                "endpoint": endpoint,
                "params": {"fixture": fid},
                "response": api.data,
                "source": api.source,
                "error": api.error,
            }
            save = store.save_raw_response(
                provider=PROVIDER_API_FOOTBALL,
                resource_type=resource_type,
                request_endpoint=endpoint,
                request_params={"fixture": fid},
                payload_json=envelope,
                source=str(api.source),
                competition_key=comp.key,
                league_id=league_id,
                season=season,
                fixture_id=fid,
            )
            if save.saved or save.skipped_duplicate:
                resource_saved[resource_type] = resource_saved.get(resource_type, 0) + 1

        if not _has_pl_odds(repo, fid):
            if api_calls >= max_api_calls:
                skipped_cap += 1
                continue
            api = client.get_odds(fid)
            if getattr(api, "source", None) == "live":
                api_calls += 1
                odds_live += 1
            if api.data is not None:
                bookmakers = normalize_odds_bookmakers(api.data)
                if bookmakers:
                    repo.save_snapshot(
                        "odds_snapshots",
                        fixture_id=fid,
                        competition_key="premier_league",
                        payload={
                            "snapshot_at": _utc_now(),
                            "source": "api_football_live_backfill",
                            "bookmakers": bookmakers,
                        },
                    )

    # Also run global cache backfill (preserves WC data, adds any PL hits)
    disk_cache = ApiCache(Path(settings.api_cache_dir)) if settings.api_cache_dir else None
    phase31e_odds = backfill_odds_from_cache(repo, disk_cache=disk_cache)

    pl_odds_count = repo._conn.execute(
        """
        SELECT COUNT(DISTINCT o.fixture_id)
        FROM odds_snapshots o
        JOIN fixtures f ON f.fixture_id = o.fixture_id
        WHERE f.competition_key = 'premier_league'
        """
    ).fetchone()[0]

    return {
        "provider": PROVIDER_API_FOOTBALL,
        "targets": len(targets),
        "resource_saved": resource_saved,
        "skipped_existing_hits": skipped_existing,
        "skipped_api_cap": skipped_cap,
        "api_calls_live": api_calls,
        "odds_live_fetches": odds_live,
        "pl_odds_cache_backfill": odds_cache,
        "phase31e_odds_backfill": phase31e_odds,
        "pl_odds_snapshot_fixtures": int(pl_odds_count or 0),
    }
