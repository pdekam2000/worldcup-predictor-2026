"""PHASE API-GAP-1 — Sportmonks targeted harvest (cache-first)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider
from worldcup_predictor.providers.sportmonks_xg_extraction import (
    XG_MATCH_FIXTURE_INCLUDES,
    parse_sportmonks_xg_match,
)
from worldcup_predictor.research.api_gap_audit import SPORTMONKS_XG_CACHE_DIRS
from worldcup_predictor.research.api_gap_staging import ensure_api_gap_tables, log_harvest, upsert_raw_payload

PROVIDER = "sportmonks"
DATA_TYPES = ("xg", "pressure", "lineups", "injuries", "events", "match_stats")


@dataclass
class SportmonksHarvestStats:
    cache_files_scanned: int = 0
    cache_hits: int = 0
    api_calls: int = 0
    xg_snapshots_created: int = 0
    xg_snapshots_skipped_existing: int = 0
    xg_unmapped_cache: int = 0
    raw_staged: int = 0
    skipped_quota: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": PROVIDER,
            "cache_files_scanned": self.cache_files_scanned,
            "cache_hits": self.cache_hits,
            "api_calls": self.api_calls,
            "xg_snapshots_created": self.xg_snapshots_created,
            "xg_snapshots_skipped_existing": self.xg_snapshots_skipped_existing,
            "xg_unmapped_cache": self.xg_unmapped_cache,
            "raw_staged": self.raw_staged,
            "skipped_quota": self.skipped_quota,
            "errors": self.errors[:25],
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _sm_to_api_fixture_map(conn: sqlite3.Connection) -> dict[int, tuple[int, str]]:
    """sportmonks_fixture_id -> (api_football_fixture_id, competition_key)."""
    mapping: dict[int, tuple[int, str]] = {}
    for row in conn.execute(
        """
        SELECT e.sportmonks_fixture_id, e.fixture_id_api_football, f.competition_key
        FROM sportmonks_fixture_enrichment e
        LEFT JOIN fixtures f ON f.fixture_id = e.fixture_id_api_football
        WHERE e.fixture_id_api_football IS NOT NULL
        """
    ):
        mapping[int(row["sportmonks_fixture_id"])] = (
            int(row["fixture_id_api_football"]),
            str(row["competition_key"] or "unknown"),
        )
    return mapping


def _load_cache_payload(path: Path) -> dict[str, Any] | None:
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if isinstance(blob, dict) and "payload" in blob:
        inner = blob["payload"]
        return inner.get("data") if isinstance(inner, dict) and "data" in inner else inner
    if isinstance(blob, dict) and "data" in blob:
        return blob["data"]
    return blob if isinstance(blob, dict) else None


def _xg_block_from_raw(raw: dict[str, Any], *, sm_id: int, source: str) -> dict[str, Any]:
    parsed = parse_sportmonks_xg_match(raw)
    team = parsed.get("team") or {}
    return {
        "home_xg": team.get("home_xg"),
        "away_xg": team.get("away_xg"),
        "home_xgot": team.get("home_xgot"),
        "away_xgot": team.get("away_xgot"),
        "home_npxg": team.get("home_npxg"),
        "away_npxg": team.get("away_npxg"),
        "player_xg_summary": parsed.get("player_xg_summary"),
        "xg_timeline": team.get("timeline"),
        "xg_source": parsed.get("source") or source,
        "xg_freshness": _utc_now(),
        "xg_available": bool(parsed.get("available")),
        "sportmonks_fixture_id": sm_id,
        "raw_preserved": True,
    }


def harvest_sportmonks_xg_from_cache(
    repo: FootballIntelligenceRepository,
    *,
    dry_run: bool = False,
    max_import: int | None = None,
) -> SportmonksHarvestStats:
    """Import xG from disk cache into xg_snapshots where fixture mapping exists."""
    conn = repo._conn
    ensure_api_gap_tables(conn)
    stats = SportmonksHarvestStats()
    sm_map = _sm_to_api_fixture_map(conn)
    seen_paths: set[Path] = set()

    for cache_dir in SPORTMONKS_XG_CACHE_DIRS:
        if not cache_dir.is_dir():
            continue
        for path in sorted(cache_dir.glob("*.json")):
            if path in seen_paths:
                continue
            seen_paths.add(path)
            stats.cache_files_scanned += 1
            if max_import is not None and stats.xg_snapshots_created >= max_import:
                break

            try:
                sm_id = int(path.stem)
            except ValueError:
                stats.xg_unmapped_cache += 1
                continue

            mapped = sm_map.get(sm_id)
            if not mapped:
                stats.xg_unmapped_cache += 1
                log_harvest(
                    conn,
                    provider=PROVIDER,
                    data_type="xg",
                    entity_key=str(sm_id),
                    action="skipped_unmapped",
                )
                continue

            fixture_id, competition_key = mapped
            if repo.has_xg_snapshot(fixture_id):
                stats.xg_snapshots_skipped_existing += 1
                log_harvest(
                    conn,
                    provider=PROVIDER,
                    data_type="xg",
                    entity_key=str(fixture_id),
                    action="skipped_existing",
                )
                continue

            raw = _load_cache_payload(path)
            if not raw:
                stats.errors.append(f"bad_cache:{path.name}")
                continue
            stats.cache_hits += 1
            xg_block = _xg_block_from_raw(raw, sm_id=sm_id, source="sportmonks_disk_cache")

            if upsert_raw_payload(
                conn,
                provider=PROVIDER,
                entity_key=f"sm:{sm_id}",
                data_type="xg",
                payload={"cache_path": str(path), "raw": raw, "parsed": xg_block},
                source=str(path),
                fixture_id=fixture_id,
                dry_run=dry_run,
            ):
                stats.raw_staged += 1

            if xg_block["xg_available"] and not dry_run:
                repo.save_snapshot(
                    "xg_snapshots",
                    fixture_id=fixture_id,
                    competition_key=competition_key,
                    payload=xg_block,
                )
                stats.xg_snapshots_created += 1
                log_harvest(
                    conn,
                    provider=PROVIDER,
                    data_type="xg",
                    entity_key=str(fixture_id),
                    action="imported_xg_snapshot",
                    details={"sportmonks_fixture_id": sm_id},
                )
            elif not xg_block["xg_available"]:
                log_harvest(
                    conn,
                    provider=PROVIDER,
                    data_type="xg",
                    entity_key=str(fixture_id),
                    action="skipped_no_xg_in_payload",
                )

    if not dry_run:
        conn.commit()
    return stats


def harvest_sportmonks_missing_api(
    repo: FootballIntelligenceRepository,
    provider: SportmonksProvider,
    *,
    dry_run: bool = False,
    max_api_calls: int = 20,
    near_quota_stop: bool = True,
) -> SportmonksHarvestStats:
    """Fetch missing enrichment only when no raw cache row exists."""
    conn = repo._conn
    ensure_api_gap_tables(conn)
    stats = SportmonksHarvestStats()
    if not provider.is_configured:
        stats.errors.append("sportmonks_not_configured")
        return stats

    includes = ";".join(XG_MATCH_FIXTURE_INCLUDES)
    for row in conn.execute(
        """
        SELECT sportmonks_fixture_id, fixture_id_api_football
        FROM sportmonks_fixture_enrichment
        WHERE fixture_id_api_football IS NOT NULL
        ORDER BY sportmonks_fixture_id
        """
    ):
        if stats.api_calls >= max_api_calls:
            stats.skipped_quota += 1
            break
        sm_id = int(row["sportmonks_fixture_id"])
        fixture_id = int(row["fixture_id_api_football"])
        entity = f"sm:{sm_id}"

        exists = conn.execute(
            "SELECT 1 FROM api_gap_raw_payload WHERE provider=? AND entity_key=? AND data_type='enrichment_full' LIMIT 1",
            (PROVIDER, entity),
        ).fetchone()
        if exists:
            log_harvest(conn, provider=PROVIDER, data_type="enrichment_full", entity_key=entity, action="skipped_cached")
            stats.cache_hits += 1
            continue

        if dry_run:
            log_harvest(conn, provider=PROVIDER, data_type="enrichment_full", entity_key=entity, action="dry_run_would_fetch")
            continue

        status, payload, err = provider.safe_get(
            f"fixtures/{sm_id}",
            params={"include": includes},
        )
        stats.api_calls += 1
        if err or not payload:
            stats.errors.append(f"{sm_id}:{err}")
            log_harvest(conn, provider=PROVIDER, data_type="enrichment_full", entity_key=entity, action="fetch_error", details={"error": err})
            continue

        data = payload.get("data") if isinstance(payload, dict) else payload
        if isinstance(data, dict) and upsert_raw_payload(
            conn,
            provider=PROVIDER,
            entity_key=entity,
            data_type="enrichment_full",
            payload=data,
            source="sportmonks_api",
            fixture_id=fixture_id,
        ):
            stats.raw_staged += 1
            log_harvest(conn, provider=PROVIDER, data_type="enrichment_full", entity_key=entity, action="fetched")

        if not repo.has_xg_snapshot(fixture_id) and isinstance(data, dict):
            xg_block = _xg_block_from_raw(data, sm_id=sm_id, source="sportmonks_api")
            if xg_block["xg_available"]:
                comp = conn.execute(
                    "SELECT competition_key FROM fixtures WHERE fixture_id = ?", (fixture_id,)
                ).fetchone()
                repo.save_snapshot(
                    "xg_snapshots",
                    fixture_id=fixture_id,
                    competition_key=str(comp["competition_key"] if comp else "unknown"),
                    payload=xg_block,
                )
                stats.xg_snapshots_created += 1

    if not dry_run:
        conn.commit()
    return stats


def run_sportmonks_harvest(
    *,
    settings,
    dry_run: bool = False,
    max_api_calls: int = 20,
    max_cache_import: int | None = None,
    use_api: bool = True,
) -> dict[str, Any]:
    repo = FootballIntelligenceRepository(settings.sqlite_path)
    provider = SportmonksProvider(settings)
    cache_stats = harvest_sportmonks_xg_from_cache(
        repo, dry_run=dry_run, max_import=max_cache_import
    )
    api_stats = SportmonksHarvestStats()
    if use_api:
        api_stats = harvest_sportmonks_missing_api(
            repo, provider, dry_run=dry_run, max_api_calls=max_api_calls
        )
    xg_after = repo._conn.execute("SELECT COUNT(1) FROM xg_snapshots").fetchone()[0]
    repo.close()
    return {
        "cache_import": cache_stats.to_dict(),
        "api_fetch": api_stats.to_dict(),
        "xg_snapshots_after": xg_after,
    }
