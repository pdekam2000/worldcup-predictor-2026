"""Resolve API-Football national team IDs and cached match history (Phase 32B)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from worldcup_predictor.cache.api_cache import ApiCache
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.intelligence.national_team._shared import (
    int_or_none,
    normalize_team_name,
    safe_list,
)
from worldcup_predictor.intelligence.national_team.history_filters import (
    apply_history_filters,
    history_filter_context,
)


@dataclass(frozen=True)
class ResolvedTeamIds:
    home_team_id: int | None
    away_team_id: int | None
    source: str


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


def _team_ids_from_item(item: dict[str, Any]) -> tuple[int | None, int | None]:
    teams = item.get("teams") or {}
    return int_or_none((teams.get("home") or {}).get("id")), int_or_none((teams.get("away") or {}).get("id"))


def _team_ids_from_lineups(lineups: list[Any], home_name: str, away_name: str) -> tuple[int | None, int | None]:
    home_id: int | None = None
    away_id: int | None = None
    home_n = normalize_team_name(home_name)
    away_n = normalize_team_name(away_name)
    for row in lineups:
        if not isinstance(row, dict):
            continue
        team = row.get("team") or {}
        tid = int_or_none(team.get("id"))
        tname = normalize_team_name(str(team.get("name") or ""))
        if tid is None:
            continue
        if home_n and (home_n in tname or tname in home_n):
            home_id = tid
        elif away_n and (away_n in tname or tname in away_n):
            away_id = tid
    if home_id is None and lineups and isinstance(lineups[0], dict):
        home_id = int_or_none((lineups[0].get("team") or {}).get("id"))
    if away_id is None and len(lineups) > 1 and isinstance(lineups[1], dict):
        away_id = int_or_none((lineups[1].get("team") or {}).get("id"))
    return home_id, away_id


def _cache_payload(repo: FootballIntelligenceRepository, endpoint: str, params: dict[str, Any]) -> Any | None:
    key = ApiCache.build_key(endpoint, params)
    return repo.get_api_cache_payload(key)


def resolve_api_team_ids(
    report: MatchIntelligenceReport,
    *,
    repo: FootballIntelligenceRepository | None = None,
) -> ResolvedTeamIds:
    repo = repo or FootballIntelligenceRepository()
    home_id = report.home_team.team_id
    away_id = report.away_team.team_id
    source = "report"

    if home_id and away_id:
        return ResolvedTeamIds(home_id, away_id, source)

    row = repo.get_fixture_row(report.fixture_id)
    if row:
        home_id = home_id or int_or_none(row.get("home_team_id"))
        away_id = away_id or int_or_none(row.get("away_team_id"))
        if home_id and away_id:
            return ResolvedTeamIds(home_id, away_id, "sqlite_fixture")

    cached = _cache_payload(repo, "fixtures", {"id": report.fixture_id})
    items = _payload_list(cached)
    if items:
        hid, aid = _team_ids_from_item(items[0])
        home_id = home_id or hid
        away_id = away_id or aid
        if home_id or away_id:
            source = "api_cache_fixture"

    enrich = repo.get_fixture_enrichment_row(report.fixture_id)
    if enrich and enrich.get("lineups_json"):
        try:
            lineups = json.loads(enrich["lineups_json"])
        except (json.JSONDecodeError, TypeError):
            lineups = []
        hid, aid = _team_ids_from_lineups(
            safe_list(lineups),
            report.home_team.team_name,
            report.away_team.team_name,
        )
        home_id = home_id or hid
        away_id = away_id or aid
        if hid or aid:
            source = "fixture_enrichment_lineups"

    if not home_id:
        home_id = repo.lookup_team_id_by_name(report.home_team.team_name)
        if home_id:
            source = "teams_table" if source == "report" else source
    if not away_id:
        away_id = repo.lookup_team_id_by_name(report.away_team.team_name)
        if away_id and source == "report":
            source = "teams_table"

    return ResolvedTeamIds(home_id, away_id, source)


def load_recent_fixtures_cached(
    team_id: int,
    *,
    last: int = 10,
    repo: FootballIntelligenceRepository | None = None,
) -> list[dict[str, Any]]:
    repo = repo or FootballIntelligenceRepository()
    form_row = repo.get_national_form_cache(team_id)
    if form_row and form_row.get("recent_fixtures"):
        return safe_list(form_row["recent_fixtures"])[:last]
    payload = _cache_payload(repo, "fixtures", {"team": team_id, "last": last})
    items = _payload_list(payload)
    if items:
        return items
    try:
        from worldcup_predictor.cache.api_cache import get_api_cache

        disk = get_api_cache(get_settings().api_cache_dir)
        return _payload_list(disk.get("fixtures", {"team": team_id, "last": last}))
    except Exception:
        return []


def _synthesize_h2h_from_recent(
    home_recent: list[dict[str, Any]],
    away_recent: list[dict[str, Any]],
    home_id: int,
    away_id: int,
    *,
    last: int = 10,
) -> list[dict[str, Any]]:
    """Derive mutual meetings from overlapping team recent-fixture caches (offline fallback)."""
    seen: set[int] = set()
    out: list[dict[str, Any]] = []
    for item in home_recent + away_recent:
        if not isinstance(item, dict):
            continue
        fid = int_or_none((item.get("fixture") or {}).get("id"))
        if fid is not None and fid in seen:
            continue
        teams = item.get("teams") or {}
        h = int_or_none((teams.get("home") or {}).get("id"))
        a = int_or_none((teams.get("away") or {}).get("id"))
        if h is None or a is None:
            continue
        if {h, a} == {home_id, away_id}:
            if fid is not None:
                seen.add(fid)
            out.append(item)
        if len(out) >= last:
            break
    return out[:last]


def load_h2h_cached(
    home_id: int,
    away_id: int,
    *,
    last: int = 10,
    repo: FootballIntelligenceRepository | None = None,
) -> list[dict[str, Any]]:
    repo = repo or FootballIntelligenceRepository()
    h2h_row = repo.get_national_h2h_cache(home_id, away_id)
    if h2h_row and h2h_row.get("meetings"):
        return safe_list(h2h_row["meetings"])[:last]
    h2h_key = f"{min(home_id, away_id)}-{max(home_id, away_id)}"
    payload = _cache_payload(repo, "fixtures/headtohead", {"h2h": h2h_key, "last": last})
    items = _payload_list(payload)
    if items:
        return items
    payload = _cache_payload(repo, "fixtures/headtohead", {"h2h": f"{home_id}-{away_id}", "last": last})
    items = _payload_list(payload)
    if items:
        return items
    try:
        from worldcup_predictor.cache.api_cache import get_api_cache

        disk = get_api_cache(get_settings().api_cache_dir)
        items = _payload_list(disk.get("fixtures/headtohead", {"h2h": h2h_key, "last": last}))
        if items:
            return items
        return _payload_list(disk.get("fixtures/headtohead", {"h2h": f"{home_id}-{away_id}", "last": last}))
    except Exception:
        return []


def warm_national_team_cache_for_fixture(
    fixture_id: int,
    *,
    settings: Settings | None = None,
    repo: FootballIntelligenceRepository | None = None,
) -> dict[str, Any]:
    """Cache-first warm: fixture identity, recent form, H2H (1–3 API calls if cache cold)."""
    settings = settings or get_settings()
    repo = repo or FootballIntelligenceRepository(settings.sqlite_path or None)
    from worldcup_predictor.clients.api_football import ApiFootballClient

    client = ApiFootballClient(settings)
    summary: dict[str, Any] = {"fixture_id": fixture_id, "api_calls": 0}

    fx = client.get_fixture_by_id(fixture_id)
    summary["api_calls"] += 1 if fx.source == "live" else 0
    items = _payload_list(fx.data)
    if not items:
        summary["message"] = fx.error or "fixture_not_found"
        return summary

    home_id, away_id = _team_ids_from_item(items[0])
    if home_id or away_id:
        repo.update_fixture_identity(
            fixture_id,
            home_team_id=home_id,
            away_team_id=away_id,
        )
    summary["home_team_id"] = home_id
    summary["away_team_id"] = away_id

    if home_id:
        r_home = client.get_team_recent_fixtures(home_id, last=10)
        summary["api_calls"] += 1 if r_home.source == "live" else 0
        summary["home_recent_count"] = len(_payload_list(r_home.data))
    if away_id:
        r_away = client.get_team_recent_fixtures(away_id, last=10)
        summary["api_calls"] += 1 if r_away.source == "live" else 0
        summary["away_recent_count"] = len(_payload_list(r_away.data))
    if home_id and away_id:
        h2h = client.get_head_to_head(home_id, away_id, last=10)
        summary["api_calls"] += 1 if h2h.source == "live" else 0
        summary["h2h_count"] = len(_payload_list(h2h.data))
    summary["success"] = bool(home_id and away_id)
    return summary


def resolve_match_history(
    report: MatchIntelligenceReport,
    *,
    repo: FootballIntelligenceRepository | None = None,
) -> dict[str, Any]:
    repo = repo or FootballIntelligenceRepository()
    ids = resolve_api_team_ids(report, repo=repo)
    home_recent = list(report.home_recent_fixtures or [])
    away_recent = list(report.away_recent_fixtures or [])
    h2h = safe_list((report.head_to_head or {}).get("meetings"))

    if ids.home_team_id and not home_recent:
        home_recent = load_recent_fixtures_cached(ids.home_team_id, last=10, repo=repo)
    if ids.away_team_id and not away_recent:
        away_recent = load_recent_fixtures_cached(ids.away_team_id, last=10, repo=repo)
    if ids.home_team_id and ids.away_team_id and not h2h:
        h2h = load_h2h_cached(ids.home_team_id, ids.away_team_id, last=10, repo=repo)
    if ids.home_team_id and ids.away_team_id and not h2h:
        if not home_recent:
            home_recent = load_recent_fixtures_cached(ids.home_team_id, last=10, repo=repo)
        if not away_recent:
            away_recent = load_recent_fixtures_cached(ids.away_team_id, last=10, repo=repo)
        h2h = _synthesize_h2h_from_recent(
            home_recent,
            away_recent,
            ids.home_team_id,
            ids.away_team_id,
            last=10,
        )

    before_kickoff, exclude_fid = history_filter_context(report, repo=repo)
    home_recent = apply_history_filters(
        home_recent,
        before_kickoff=before_kickoff,
        exclude_fixture_id=exclude_fid,
    )
    away_recent = apply_history_filters(
        away_recent,
        before_kickoff=before_kickoff,
        exclude_fixture_id=exclude_fid,
    )
    h2h = apply_history_filters(
        h2h,
        before_kickoff=before_kickoff,
        exclude_fixture_id=exclude_fid,
    )

    return {
        "home_team_id": ids.home_team_id,
        "away_team_id": ids.away_team_id,
        "id_source": ids.source,
        "home_recent_fixtures": home_recent,
        "away_recent_fixtures": away_recent,
        "h2h_meetings": h2h,
    }
