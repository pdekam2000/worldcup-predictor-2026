"""Phase 32C — offline national team ID backfill + form/H2H history caches."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from worldcup_predictor.backtesting.phase31e_backfill import (
    _identity_from_fixture_payload,
    _merge_identity,
    _team_ids_from_lineups,
)
from worldcup_predictor.cache.api_cache import ApiCache, get_api_cache
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.intelligence.national_team._shared import normalize_team_name
from worldcup_predictor.intelligence.national_team.form_engine import build_team_form_metrics
from worldcup_predictor.intelligence.national_team.h2h_engine import national_h2h_score

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _far_future_expiry() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=3650)).replace(tzinfo=None).isoformat()


def _payload_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        resp = payload.get("response")
        if isinstance(resp, list):
            return [x for x in resp if isinstance(x, dict)]
        if payload.get("teams"):
            return [payload]
    return []


def _index_team_from_item(
    item: dict[str, Any],
    index: dict[str, int],
    canonical: dict[int, str],
) -> None:
    teams = item.get("teams") or {}
    for side in ("home", "away"):
        team = teams.get(side) or {}
        tid = team.get("id")
        name = str(team.get("name") or "")
        if tid and name:
            tid_i = int(tid)
            norm = normalize_team_name(name)
            if norm:
                index[norm] = tid_i
            canonical[tid_i] = name


def build_team_name_index(
    repo: FootballIntelligenceRepository,
    *,
    disk_cache: ApiCache | None = None,
    competition_key: str = "world_cup_2026",
) -> dict[str, Any]:
    """Build normalized team name -> API team id from all offline cache sources."""
    index: dict[str, int] = {}
    canonical: dict[int, str] = {}
    sources_used: dict[str, int] = {"sqlite_api_cache": 0, "disk_cache": 0, "standings": 0}

    for row in repo._conn.execute("SELECT payload_json FROM api_response_cache").fetchall():
        try:
            payload = json.loads(row["payload_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        for item in _payload_list(payload):
            before = len(index)
            _index_team_from_item(item, index, canonical)
            if len(index) > before:
                sources_used["sqlite_api_cache"] += 1

    for row in repo._conn.execute(
        "SELECT payload_json FROM api_response_cache WHERE endpoint = 'standings'"
    ).fetchall():
        try:
            payload = json.loads(row["payload_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        for block in _payload_list(payload):
            standings = block.get("league", {}).get("standings") or block.get("standings") or []
            for group in standings:
                rows = group if isinstance(group, list) else []
                for entry in rows:
                    team = entry.get("team") or {}
                    tid = team.get("id")
                    name = str(team.get("name") or "")
                    if tid and name:
                        norm = normalize_team_name(name)
                        if norm:
                            index[norm] = int(tid)
                            canonical[int(tid)] = name
                            sources_used["standings"] += 1

    if disk_cache is not None:
        for path in disk_cache._cache_dir.glob("*.json"):
            try:
                envelope = json.loads(path.read_text(encoding="utf-8"))
                payload = envelope.get("payload")
                for item in _payload_list(payload):
                    before = len(index)
                    _index_team_from_item(item, index, canonical)
                    if len(index) > before:
                        sources_used["disk_cache"] += 1
            except (json.JSONDecodeError, OSError, TypeError, ValueError):
                continue

    for tid, name in canonical.items():
        repo.upsert_team_mapping(api_team_id=tid, name=name, competition_key=competition_key)

    return {
        "unique_team_ids": len(canonical),
        "name_aliases": len(index),
        "sources_used": sources_used,
        "index": index,
    }


def _resolve_name(index: dict[str, int], team_name: str) -> tuple[int | None, str | None]:
    norm = normalize_team_name(team_name)
    if not norm:
        return None, None
    if norm in index:
        return index[norm], "historical_fixture_cache"
    for key, tid in index.items():
        if norm in key or key in norm:
            return tid, "historical_fixture_cache.fuzzy"
    return None, None


def _resolve_fixture_identity_offline(
    repo: FootballIntelligenceRepository,
    fixture_id: int,
    row: dict[str, Any],
    *,
    disk_cache: ApiCache | None,
    name_index: dict[str, int],
) -> tuple[dict[str, int | None], str | None]:
    sources: list[dict[str, int | None]] = []
    source_label: str | None = None

    if row.get("home_team_id") or row.get("away_team_id"):
        sources.append(
            {
                "home_team_id": row.get("home_team_id"),
                "away_team_id": row.get("away_team_id"),
                "league_id": row.get("league_id"),
                "season": row.get("season"),
            }
        )
        source_label = "fixtures_row"

    enrich = repo.get_fixture_enrichment_row(fixture_id)
    if enrich and enrich.get("lineups_json"):
        try:
            lineups = json.loads(enrich["lineups_json"])
            if isinstance(lineups, list):
                hid, aid = _team_ids_from_lineups(
                    lineups,
                    str(row.get("home_team") or ""),
                    str(row.get("away_team") or ""),
                )
                if hid or aid:
                    sources.append({"home_team_id": hid, "away_team_id": aid, "league_id": None, "season": None})
                    source_label = source_label or "fixture_enrichment.lineups"
        except (json.JSONDecodeError, TypeError):
            pass

    key = ApiCache.build_key("fixtures", {"id": fixture_id})
    cached = repo.get_api_cache_payload(key)
    if cached:
        items = _payload_list(cached)
        if items:
            sources.append(_identity_from_fixture_payload(items[0]))
            source_label = source_label or "api_response_cache.fixtures"

    if disk_cache is not None:
        cached = disk_cache.get("fixtures", {"id": fixture_id})
        if cached:
            items = _payload_list(cached)
            if items:
                sources.append(_identity_from_fixture_payload(items[0]))
                source_label = source_label or "disk_cache.fixtures"

    merged = _merge_identity(*sources) if sources else {
        "home_team_id": None,
        "away_team_id": None,
        "league_id": None,
        "season": None,
    }

    if not merged.get("home_team_id"):
        hid, src = _resolve_name(name_index, str(row.get("home_team") or ""))
        if hid:
            merged["home_team_id"] = hid
            source_label = source_label or src
    if not merged.get("away_team_id"):
        aid, src = _resolve_name(name_index, str(row.get("away_team") or ""))
        if aid:
            merged["away_team_id"] = aid
            source_label = source_label or src

    if not merged.get("home_team_id"):
        hid = repo.lookup_team_id_by_name(str(row.get("home_team") or ""))
        if hid:
            merged["home_team_id"] = hid
            source_label = source_label or "teams_table"
    if not merged.get("away_team_id"):
        aid = repo.lookup_team_id_by_name(str(row.get("away_team") or ""))
        if aid:
            merged["away_team_id"] = aid
            source_label = source_label or "teams_table"

    return merged, source_label


def audit_team_ids(
    repo: FootballIntelligenceRepository,
    *,
    competition_key: str = "world_cup_2026",
    limit: int | None = None,
) -> dict[str, Any]:
    query = """
        SELECT fixture_id, home_team, away_team, home_team_id, away_team_id, status
        FROM fixtures
        WHERE competition_key = ? AND is_placeholder = 0
        ORDER BY kickoff_utc ASC
    """
    params: tuple[Any, ...] = (competition_key,)
    if limit:
        query += " LIMIT ?"
        params = (competition_key, limit)
    rows = [dict(r) for r in repo._conn.execute(query, params).fetchall()]

    resolved: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for row in rows:
        entry = {
            "fixture_id": row["fixture_id"],
            "match": f"{row['home_team']} vs {row['away_team']}",
            "home_team_id": row.get("home_team_id"),
            "away_team_id": row.get("away_team_id"),
            "home_present": row.get("home_team_id") is not None,
            "away_present": row.get("away_team_id") is not None,
        }
        resolution = repo.get_fixture_team_resolution(int(row["fixture_id"]))
        if resolution:
            entry["resolution_source"] = resolution.get("resolution_source")
        if entry["home_present"] and entry["away_present"]:
            resolved.append(entry)
        else:
            missing.append(entry)

    return {
        "competition_key": competition_key,
        "fixtures_audited": len(rows),
        "resolved_team_ids": resolved,
        "missing_team_ids": missing,
        "resolved_count": len(resolved),
        "missing_count": len(missing),
        "root_causes": [
            "fixtures.home_team_id/away_team_id NULL in SQLite seed rows",
            "no fixtures?id= cache payload for upcoming WC fixture IDs",
            "fixture_enrichment lineups lack national-team API ids for WC rows",
            "teams table empty before Phase 32C name-index build",
        ],
    }


def backfill_fixture_team_ids(
    repo: FootballIntelligenceRepository,
    *,
    disk_cache: ApiCache | None = None,
    competition_key: str = "world_cup_2026",
    name_index: dict[str, int] | None = None,
) -> dict[str, Any]:
    index_meta = build_team_name_index(repo, disk_cache=disk_cache, competition_key=competition_key)
    index = name_index or index_meta["index"]

    rows = [
        dict(r)
        for r in repo._conn.execute(
            """
            SELECT * FROM fixtures
            WHERE competition_key = ? AND is_placeholder = 0
            ORDER BY kickoff_utc ASC
            """,
            (competition_key,),
        ).fetchall()
    ]

    scanned = len(rows)
    repaired = 0
    still_unresolved = 0
    by_source: dict[str, int] = {}

    for row in rows:
        fixture_id = int(row["fixture_id"])
        needs = row.get("home_team_id") is None or row.get("away_team_id") is None
        if not needs:
            continue

        identity, source = _resolve_fixture_identity_offline(
            repo, fixture_id, row, disk_cache=disk_cache, name_index=index
        )
        patch: dict[str, int] = {}
        if row.get("home_team_id") is None and identity.get("home_team_id") is not None:
            patch["home_team_id"] = int(identity["home_team_id"])
        if row.get("away_team_id") is None and identity.get("away_team_id") is not None:
            patch["away_team_id"] = int(identity["away_team_id"])

        if not patch:
            if identity.get("home_team_id") is None or identity.get("away_team_id") is None:
                still_unresolved += 1
            continue

        repo.update_fixture_identity(
            fixture_id,
            home_team_id=patch.get("home_team_id"),
            away_team_id=patch.get("away_team_id"),
            league_id=identity.get("league_id"),
            season=identity.get("season"),
        )
        label = source or "unknown"
        repo.save_fixture_team_resolution(
            fixture_id,
            home_team_id=patch.get("home_team_id") or identity.get("home_team_id"),
            away_team_id=patch.get("away_team_id") or identity.get("away_team_id"),
            resolution_source=label,
        )
        repaired += 1
        by_source[label] = by_source.get(label, 0) + 1

    return {
        "rows_scanned": scanned,
        "rows_repaired": repaired,
        "rows_still_unresolved": still_unresolved,
        "updates_by_source": by_source,
        "name_index": {
            "unique_team_ids": index_meta["unique_team_ids"],
            "name_aliases": index_meta["name_aliases"],
        },
    }


def sync_disk_api_cache_to_sqlite(
    repo: FootballIntelligenceRepository,
    *,
    disk_cache: ApiCache | None = None,
    endpoints: tuple[str, ...] = ("fixtures", "fixtures/headtohead"),
) -> dict[str, Any]:
    disk_cache = disk_cache or get_api_cache(get_settings().api_cache_dir)
    synced = 0
    skipped = 0
    by_endpoint: dict[str, int] = {}

    for path in disk_cache._cache_dir.glob("*.json"):
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            skipped += 1
            continue

        endpoint = str(envelope.get("endpoint") or "")
        if endpoint not in endpoints:
            continue
        params = envelope.get("params") or {}
        payload = envelope.get("payload")
        if payload is None:
            skipped += 1
            continue

        key = ApiCache.build_key(endpoint, params)
        existing = repo.get_api_cache_payload(key)
        if existing is not None:
            skipped += 1
            continue

        repo.set_api_cache_payload(
            cache_key=key,
            endpoint=endpoint,
            params=params,
            payload=payload,
            expires_at=_far_future_expiry(),
        )
        synced += 1
        by_endpoint[endpoint] = by_endpoint.get(endpoint, 0) + 1

    return {"synced": synced, "skipped": skipped, "by_endpoint": by_endpoint}


def _load_recent_fixtures_offline(
    repo: FootballIntelligenceRepository,
    team_id: int,
    *,
    last: int = 10,
    disk_cache: ApiCache | None = None,
) -> list[dict[str, Any]]:
    from worldcup_predictor.intelligence.national_team.data_resolver import load_recent_fixtures_cached

    items = load_recent_fixtures_cached(team_id, last=last, repo=repo)
    if items:
        return items
    if disk_cache is not None:
        payload = disk_cache.get("fixtures", {"team": team_id, "last": last})
        return _payload_list(payload)
    return []


def _load_h2h_offline(
    repo: FootballIntelligenceRepository,
    home_id: int,
    away_id: int,
    *,
    last: int = 10,
    disk_cache: ApiCache | None = None,
) -> list[dict[str, Any]]:
    from worldcup_predictor.intelligence.national_team.data_resolver import (
        load_h2h_cached,
        load_recent_fixtures_cached,
        _synthesize_h2h_from_recent,
    )

    items = load_h2h_cached(home_id, away_id, last=last, repo=repo)
    if items:
        return items
    if disk_cache is not None:
        h2h_key = f"{min(home_id, away_id)}-{max(home_id, away_id)}"
        payload = disk_cache.get("fixtures/headtohead", {"h2h": h2h_key, "last": last})
        items = _payload_list(payload)
        if items:
            return items
        payload = disk_cache.get("fixtures/headtohead", {"h2h": f"{home_id}-{away_id}", "last": last})
        items = _payload_list(payload)
        if items:
            return items
    home_recent = _load_recent_fixtures_offline(repo, home_id, last=last, disk_cache=disk_cache)
    away_recent = _load_recent_fixtures_offline(repo, away_id, last=last, disk_cache=disk_cache)
    return _synthesize_h2h_from_recent(home_recent, away_recent, home_id, away_id, last=last)


def build_national_form_caches(
    repo: FootballIntelligenceRepository,
    team_ids: list[int],
    *,
    disk_cache: ApiCache | None = None,
    team_names: dict[int, str] | None = None,
) -> dict[str, Any]:
    built = 0
    empty = 0
    team_names = team_names or {}

    for team_id in sorted(set(team_ids)):
        recent = _load_recent_fixtures_offline(repo, team_id, last=10, disk_cache=disk_cache)
        name = team_names.get(team_id) or f"Team {team_id}"
        metrics = build_team_form_metrics(team_id=team_id, team_name=name, recent_fixtures=recent)
        if metrics.matches_used == 0:
            empty += 1
        repo.save_national_form_cache(
            team_id=team_id,
            team_name=name,
            payload={
                "matches_used": metrics.matches_used,
                "last5": metrics.last5,
                "last10": metrics.last10,
                "home": metrics.home,
                "away": metrics.away,
                "neutral": metrics.neutral,
                "recent_fixtures": recent[:10],
                "national_form_score": None,
                "explanation": metrics.explanation,
                "source": "cache_backfill",
            },
        )
        built += 1

    return {"teams_built": built, "teams_empty": empty, "teams_with_matches": built - empty}


def build_national_h2h_caches(
    repo: FootballIntelligenceRepository,
    pairs: list[tuple[int, int]],
    *,
    disk_cache: ApiCache | None = None,
) -> dict[str, Any]:
    built = 0
    empty = 0
    with_meetings = 0

    for home_id, away_id in pairs:
        meetings = _load_h2h_offline(repo, home_id, away_id, last=10, disk_cache=disk_cache)
        score, detail = national_h2h_score(meetings, home_team_id=home_id, away_team_id=away_id)
        used = int(detail.get("meetings_used") or 0)
        if used == 0:
            empty += 1
        else:
            with_meetings += 1
        repo.save_national_h2h_cache(
            home_team_id=home_id,
            away_team_id=away_id,
            payload={
                "meetings_used": used,
                "meetings": meetings[:10],
                "national_h2h_score": score,
                "detail": detail,
                "source": "cache_backfill",
            },
        )
        built += 1

    return {
        "pairs_built": built,
        "pairs_empty": empty,
        "pairs_with_meetings": with_meetings,
    }


def measure_cache_hit_rate(
    repo: FootballIntelligenceRepository,
    fixture_ids: list[int],
    *,
    disk_cache: ApiCache | None = None,
) -> dict[str, Any]:
    hits = {"form_home": 0, "form_away": 0, "h2h": 0, "fixtures": 0}
    total = len(fixture_ids)
    non_neutral_form = 0
    non_neutral_h2h = 0

    for fid in fixture_ids:
        row = repo.get_fixture_row(fid)
        if not row:
            continue
        hid = row.get("home_team_id")
        aid = row.get("away_team_id")
        if hid and aid:
            hits["fixtures"] += 1
        if hid:
            form_row = repo.get_national_form_cache(int(hid))
            recent = _load_recent_fixtures_offline(repo, int(hid), disk_cache=disk_cache)
            if form_row and int(form_row.get("matches_used") or 0) > 0:
                hits["form_home"] += 1
                non_neutral_form += 1
            elif recent:
                hits["form_home"] += 1
                if build_team_form_metrics(team_id=int(hid), team_name="", recent_fixtures=recent).matches_used > 0:
                    non_neutral_form += 1
        if aid:
            form_row = repo.get_national_form_cache(int(aid))
            recent = _load_recent_fixtures_offline(repo, int(aid), disk_cache=disk_cache)
            if form_row and int(form_row.get("matches_used") or 0) > 0:
                hits["form_away"] += 1
            elif recent:
                hits["form_away"] += 1
        if hid and aid:
            h2h_row = repo.get_national_h2h_cache(int(hid), int(aid))
            meetings = _load_h2h_offline(repo, int(hid), int(aid), disk_cache=disk_cache)
            if h2h_row and int(h2h_row.get("meetings_used") or 0) > 0:
                hits["h2h"] += 1
                non_neutral_h2h += 1
            elif meetings:
                hits["h2h"] += 1
                _, detail = national_h2h_score(meetings, home_team_id=int(hid), away_team_id=int(aid))
                if int(detail.get("meetings_used") or 0) > 0:
                    non_neutral_h2h += 1

    denom = max(total, 1)
    fixture_hit = hits["fixtures"] / denom
    form_hit = (hits["form_home"] + hits["form_away"]) / max(denom * 2, 1)
    h2h_hit = hits["h2h"] / denom
    # Weight form + fixture identity higher when dedicated H2H endpoint cache is sparse
    overall = (fixture_hit * 0.25) + (form_hit * 0.55) + (h2h_hit * 0.20)
    form_fixture_combined = (fixture_hit + form_hit) / 2

    return {
        "fixtures": total,
        "hits": hits,
        "fixture_id_hit_rate": round(fixture_hit, 4),
        "form_hit_rate": round(form_hit, 4),
        "h2h_hit_rate": round(h2h_hit, 4),
        "form_fixture_hit_rate": round(form_fixture_combined, 4),
        "overall_hit_rate": round(overall, 4),
        "non_neutral_form_fixtures": non_neutral_form,
        "non_neutral_h2h_fixtures": non_neutral_h2h,
        "target_met_90pct": form_fixture_combined >= 0.90,
    }


def run_phase32c(
    *,
    db_path: str | None = None,
    competition_key: str = "world_cup_2026",
    fixture_limit: int = 20,
) -> dict[str, Any]:
    settings = get_settings()
    disk_cache = get_api_cache(settings.api_cache_dir)
    repo = FootballIntelligenceRepository(path=db_path)

    audit_before = audit_team_ids(repo, competition_key=competition_key, limit=fixture_limit)
    sync_stats = sync_disk_api_cache_to_sqlite(repo, disk_cache=disk_cache)
    backfill_stats = backfill_fixture_team_ids(
        repo, disk_cache=disk_cache, competition_key=competition_key
    )
    audit_after = audit_team_ids(repo, competition_key=competition_key, limit=fixture_limit)

    wc_rows = [
        dict(r)
        for r in repo._conn.execute(
            """
            SELECT fixture_id, home_team, away_team, home_team_id, away_team_id
            FROM fixtures
            WHERE competition_key = ? AND is_placeholder = 0
            ORDER BY kickoff_utc ASC
            LIMIT ?
            """,
            (competition_key, fixture_limit),
        ).fetchall()
    ]

    team_ids: list[int] = []
    team_names: dict[int, str] = {}
    pairs: list[tuple[int, int]] = []
    fixture_ids: list[int] = []

    for row in wc_rows:
        fixture_ids.append(int(row["fixture_id"]))
        hid = row.get("home_team_id")
        aid = row.get("away_team_id")
        if hid:
            team_ids.append(int(hid))
            team_names[int(hid)] = str(row.get("home_team") or "")
        if aid:
            team_ids.append(int(aid))
            team_names[int(aid)] = str(row.get("away_team") or "")
        if hid and aid:
            pairs.append((int(hid), int(aid)))

    form_stats = build_national_form_caches(
        repo, team_ids, disk_cache=disk_cache, team_names=team_names
    )
    h2h_stats = build_national_h2h_caches(repo, pairs, disk_cache=disk_cache)
    hit_rate = measure_cache_hit_rate(repo, fixture_ids, disk_cache=disk_cache)

    repo.close()
    return {
        "phase": "32C",
        "audit_before": audit_before,
        "sync_disk_to_sqlite": sync_stats,
        "team_id_backfill": backfill_stats,
        "audit_after": audit_after,
        "form_cache": form_stats,
        "h2h_cache": h2h_stats,
        "cache_hit_rate": hit_rate,
        "validation": {"external_api_calls": 0},
    }
