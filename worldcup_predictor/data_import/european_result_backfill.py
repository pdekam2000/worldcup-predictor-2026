"""PHASE EURO-A / EURO-A2 — UEFA historical fixture_results backfill (data only)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.competitions import get_competition
from worldcup_predictor.config.euro_feed_registry import UEFA_CUP_KEYS, competition_type_for
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.data_import.european_fixture_feed import ensure_euro_fixture_feed_tables
from worldcup_predictor.data_import.uefa_result_matching import (
    FeedIndex,
    MIN_PERSIST_CONFIDENCE,
    ProviderMatch,
    api_item_fixture_id,
    infer_provider_source,
    item_has_goals,
    list_missing_uefa_fixtures,
    load_file_payload,
    load_raw_payload,
    lookup_feed_api_id,
    normalize_team_name,
    outcome_source_tag,
    parse_kickoff,
    pick_best_match,
    score_api_candidates,
    sportmonks_has_scores,
    sportmonks_to_api_shape,
    teams_exact,
    utc_now_iso,
)
from worldcup_predictor.integrations.fixture_api_parser import parse_api_fixture_item
from worldcup_predictor.outcomes.outcome_persistence import normalize_match_outcome_type
from worldcup_predictor.schedule.match_center import classify_status

logger = logging.getLogger(__name__)

PHASE = "EURO-A2"
_RAW_DIR = Path("artifacts/euro_a2/raw_payloads")


def _load_cached_payload(fixture_id: int, competition_key: str) -> dict[str, Any] | None:
    for base in (Path("artifacts/euro_a2/raw_payloads"), Path("artifacts/euro_a/raw_payloads")):
        path = base / competition_key / f"{fixture_id}.json"
        if not path.exists():
            continue
        data = load_file_payload(str(path))
        if isinstance(data, dict) and isinstance(data.get("payload"), dict):
            return data["payload"]
        return data
    return None


def _api_football_season(row: dict[str, Any]) -> int | None:
    raw = row.get("season")
    if raw is not None:
        try:
            year = int(raw)
            if 1990 <= year <= 2100:
                return year
        except (TypeError, ValueError):
            pass
    kickoff = str(row.get("kickoff_utc") or "")
    dt = parse_kickoff(kickoff)
    if not dt:
        return None
    return dt.year if dt.month >= 6 else dt.year - 1


def _penalty_score_from_item(item: dict[str, Any]) -> str | None:
    score = item.get("score") or {}
    pen = score.get("penalty") or {}
    home = pen.get("home")
    away = pen.get("away")
    if home is None or away is None:
        return None
    return f"{home}-{away}"


@dataclass
class BackfillResult:
    competition_key: str
    scanned: int = 0
    backfilled: int = 0
    skipped_existing: int = 0
    skipped_not_finished: int = 0
    missing_provider: int = 0
    skipped_low_confidence: int = 0
    skipped_ambiguous: int = 0
    errors: int = 0
    dry_run: int = 0
    api_calls: int = 0
    confidence_buckets: dict[str, int] = field(default_factory=dict)
    details: list[dict[str, Any]] = field(default_factory=list)
    missing_mapping: list[dict[str, Any]] = field(default_factory=list)
    explain_rows: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": PHASE,
            "competition_key": self.competition_key,
            "scanned": self.scanned,
            "backfilled": self.backfilled,
            "skipped_existing": self.skipped_existing,
            "skipped_not_finished": self.skipped_not_finished,
            "missing_provider": self.missing_provider,
            "skipped_low_confidence": self.skipped_low_confidence,
            "skipped_ambiguous": self.skipped_ambiguous,
            "errors": self.errors,
            "dry_run": self.dry_run,
            "api_calls": self.api_calls,
            "confidence_buckets": self.confidence_buckets,
            "details": self.details[:100],
            "missing_mapping": self.missing_mapping[:100],
            "explain_rows": self.explain_rows[:100],
        }


def list_missing_result_fixtures(
    repo: FootballIntelligenceRepository,
    competition_key: str,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    return list_missing_uefa_fixtures(repo._conn, competition_key, limit=limit)


class _DateApiCache:
    def __init__(self) -> None:
        self._cache: dict[tuple[int, str], list[dict[str, Any]]] = {}

    def get(
        self,
        client: ApiFootballClient,
        *,
        league_id: int,
        date_part: str,
    ) -> tuple[list[dict[str, Any]], int]:
        key = (league_id, date_part)
        if key in self._cache:
            return self._cache[key], 0
        api = client.get_historical_fixtures(
            league_id=league_id,
            from_date=date_part,
            to_date=date_part,
        )
        calls = 1 if getattr(api, "source", None) == "live" else 0
        items = api.data if api.ok and isinstance(api.data, list) else []
        self._cache[key] = items
        return items, calls


def resolve_provider_match(
    client: ApiFootballClient | None,
    row: dict[str, Any],
    *,
    competition_key: str,
    league_id: int,
    feed_index: FeedIndex,
    conn,
    date_cache: _DateApiCache,
    force_refresh: bool = False,
) -> tuple[ProviderMatch | None, int, str]:
    """Resolve best provider match for a missing-result fixture row."""
    fid = int(row["fixture_id"])
    calls = 0
    candidates: list[ProviderMatch] = []

    cached = _load_cached_payload(fid, competition_key)
    if cached and item_has_goals(cached):
        pid = api_item_fixture_id(cached) or fid
        return (
            ProviderMatch(
                provider="cache",
                provider_fixture_id=pid,
                method="raw_payload_cache",
                confidence=1.0,
                item=cached,
            ),
            0,
            "raw_payload_cache",
        )

    api_fid = lookup_feed_api_id(row, feed_index)
    if api_fid and client is not None:
        api = client._safe_get(  # noqa: SLF001
            "fixtures",
            {"id": api_fid},
            placeholder_factory=lambda: [],
            force_refresh=force_refresh,
        )
        if getattr(api, "source", None) == "live":
            calls += 1
        if api.ok and isinstance(api.data, list) and api.data:
            item = api.data[0]
            if item_has_goals(item):
                return (
                    ProviderMatch(
                        provider="api-football",
                        provider_fixture_id=api_fid,
                        method="feed_crosswalk_api_id",
                        confidence=0.99,
                        item=item,
                        api_calls=calls,
                    ),
                    calls,
                    "feed_crosswalk_api_id",
                )

    if client is not None:
        api = client._safe_get(  # noqa: SLF001
            "fixtures",
            {"id": fid},
            placeholder_factory=lambda: [],
            force_refresh=force_refresh,
        )
        if getattr(api, "source", None) == "live":
            calls += 1
        if api.ok and isinstance(api.data, list) and api.data:
            item = api.data[0]
            if item_has_goals(item):
                pid = api_item_fixture_id(item) or fid
                return (
                    ProviderMatch(
                        provider="api-football",
                        provider_fixture_id=pid,
                        method="exact_provider_fixture_id",
                        confidence=1.0,
                        item=item,
                        api_calls=calls,
                    ),
                    calls,
                    "exact_provider_fixture_id",
                )

        kickoff = str(row.get("kickoff_utc") or "")
        date_part = kickoff[:10]
        if date_part:
            items, date_calls = date_cache.get(client, league_id=league_id, date_part=date_part)
            calls += date_calls
            candidates.extend(
                score_api_candidates(row, items, method_prefix="league_date", require_goals=True)
            )

            prev = (parse_kickoff(kickoff) or datetime.utcnow()) - timedelta(days=1)
            nxt = (parse_kickoff(kickoff) or datetime.utcnow()) + timedelta(days=1)
            for extra_date in {prev.date().isoformat(), nxt.date().isoformat()}:
                if extra_date == date_part:
                    continue
                extra_items, extra_calls = date_cache.get(
                    client, league_id=league_id, date_part=extra_date
                )
                calls += extra_calls
                candidates.extend(
                    score_api_candidates(
                        row, extra_items, method_prefix="league_adjacent_date", require_goals=True
                    )
                )

        season = _api_football_season(row)
        if season is not None and not candidates:
            api = client.get_historical_fixtures(league_id=league_id, season=int(season))
            if getattr(api, "source", None) == "live":
                calls += 1
            if api.ok and isinstance(api.data, list):
                date_part = str(row.get("kickoff_utc") or "")[:10]
                filtered = [
                    it
                    for it in api.data
                    if str((it.get("fixture") or {}).get("date") or "")[:10] == date_part
                ]
                candidates.extend(
                    score_api_candidates(
                        row, filtered, method_prefix="league_season", require_goals=True
                    )
                )

    comp = str(row["competition_key"])
    kick = str(row.get("kickoff_utc") or "")[:10]
    ht = normalize_team_name(str(row.get("home_team")))
    at = normalize_team_name(str(row.get("away_team")))
    sm_feed = feed_index.sportmonks_by_date_teams.get((comp, kick, ht, at)) or []
    if not sm_feed:
        for key, rows in feed_index.sportmonks_by_date_teams.items():
            if key[0] != comp:
                continue
            for feed_row in rows:
                if teams_exact(
                    str(row.get("home_team")),
                    str(row.get("away_team")),
                    str(feed_row.get("home_team")),
                    str(feed_row.get("away_team")),
                ):
                    sm_feed.append(feed_row)
                    break

    for feed_row in sm_feed[:3]:
        ref = feed_row.get("raw_payload_ref")
        payload = load_raw_payload(conn, str(ref) if ref else None)
        if not payload:
            continue
        sm_item = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        if not isinstance(sm_item, dict) or not sportmonks_has_scores(sm_item):
            continue
        pid = int(feed_row["provider_fixture_id"])
        shaped = sportmonks_to_api_shape(sm_item, provider_fixture_id=pid)
        if shaped:
            candidates.append(
                ProviderMatch(
                    provider="sportmonks",
                    provider_fixture_id=pid,
                    method="sportmonks_feed_payload",
                    confidence=0.94,
                    item=shaped,
                )
            )

    best = pick_best_match(candidates)
    if best is None:
        return None, calls, "unresolved"
    best.api_calls = calls
    return best, calls, best.method


def _fixture_from_provider_item(
    item: dict[str, Any],
    *,
    expected_competition_key: str,
) -> tuple[Any | None, str | None]:
    fixture = parse_api_fixture_item(item, source="historical")
    if fixture is None:
        return None, "parse_failed"
    if classify_status(fixture.status) != "finished":
        return None, "not_finished"
    if fixture.home_goals is None or fixture.away_goals is None:
        return None, "missing_goals"
    _ = expected_competition_key
    return fixture, None


def _bucket_confidence(confidence: float) -> str:
    if confidence >= 0.99:
        return "exact_0.99+"
    if confidence >= 0.95:
        return "high_0.95_0.98"
    if confidence >= 0.88:
        return "medium_0.88_0.94"
    return "low_below_0.88"


def backfill_single_fixture(
    repo: FootballIntelligenceRepository,
    client: ApiFootballClient | None,
    row: dict[str, Any],
    *,
    competition_key: str,
    league_id: int,
    feed_index: FeedIndex,
    conn,
    date_cache: _DateApiCache,
    force: bool = False,
    dry_run: bool = False,
    explain: bool = False,
    force_refresh: bool = False,
) -> tuple[str, int, dict[str, Any]]:
    """Returns (outcome, api_calls_used, detail)."""
    fid = int(row["fixture_id"])
    detail: dict[str, Any] = {
        "fixture_id": fid,
        "competition_key": competition_key,
        "home_team": row.get("home_team"),
        "away_team": row.get("away_team"),
        "kickoff_utc": row.get("kickoff_utc"),
        "provider_source": infer_provider_source(row, feed_index),
    }

    if not force and repo.get_fixture_result_row(fid):
        detail["outcome"] = "skipped_existing"
        return "skipped_existing", 0, detail

    match, api_calls, method = resolve_provider_match(
        client,
        row,
        competition_key=competition_key,
        league_id=league_id,
        feed_index=feed_index,
        conn=conn,
        date_cache=date_cache,
        force_refresh=force_refresh,
    )
    detail["resolve_method"] = method
    detail["api_calls"] = api_calls

    if match is None:
        detail["outcome"] = "missing_provider"
        detail["reason"] = "no_provider_payload_or_goals"
        return "missing_provider", api_calls, detail

    detail["match_confidence"] = match.confidence
    detail["provider_fixture_id"] = match.provider_fixture_id
    detail["match_provider"] = match.provider

    if match.ambiguous:
        detail["outcome"] = "skipped_ambiguous"
        detail["candidates"] = match.candidates
        return "skipped_ambiguous", api_calls, detail

    if not match.persistable:
        detail["outcome"] = "skipped_low_confidence"
        detail["reason"] = f"confidence_{match.confidence:.3f}_below_{MIN_PERSIST_CONFIDENCE}"
        return "skipped_low_confidence", api_calls, detail

    fixture, err = _fixture_from_provider_item(match.item, expected_competition_key=competition_key)
    if fixture is None:
        detail["outcome"] = err or "error"
        if err == "missing_goals":
            return "missing_provider", api_calls, detail
        return err or "error", api_calls, detail

    detail["expected_score"] = f"{fixture.home_goals}-{fixture.away_goals}"
    detail["status"] = fixture.status

    if dry_run:
        detail["outcome"] = "dry_run_would_backfill"
        return "dry_run_would_backfill", api_calls, detail

    penalty = _penalty_score_from_item(match.item)
    outcome_type = normalize_match_outcome_type(fixture.status)
    api_fid = int(fixture.fixture_id)
    outcome_src = outcome_source_tag(
        provider=match.provider,
        provider_fixture_id=match.provider_fixture_id,
        confidence=match.confidence,
        method=match.method,
    )

    repo.upsert_fixture(
        fixture,
        competition_key=competition_key,
        league_id=row.get("league_id") or league_id,
        season=row.get("season") or fixture.season,
    )
    repo.update_fixture_competition_type(api_fid, competition_type_for(get_competition(competition_key)))
    repo.upsert_fixture_result(
        fixture,
        competition_key=competition_key,
        match_outcome_type=outcome_type,
        penalty_score=penalty,
        outcome_source=outcome_src,
    )
    if api_fid != fid:
        legacy = replace(fixture, fixture_id=fid)
        repo.upsert_fixture_result(
            legacy,
            competition_key=competition_key,
            match_outcome_type=outcome_type,
            penalty_score=penalty,
            outcome_source=outcome_src + "|legacy_row",
        )
    _persist_backfill_payload(api_fid, competition_key, match.item, match.provider)
    detail["outcome"] = "backfilled"
    detail["stored_fixture_id"] = api_fid
    return "backfilled", api_calls, detail


def _persist_backfill_payload(
    fixture_id: int,
    competition_key: str,
    item: dict[str, Any],
    provider: str,
) -> None:
    dest = _RAW_DIR / competition_key / f"{fixture_id}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    wrapped = {"provider": provider, "payload": item, "saved_at_utc": utc_now_iso()}
    dest.write_text(json.dumps(wrapped, ensure_ascii=False, indent=2), encoding="utf-8")


def backfill_competition_results(
    competition_key: str,
    *,
    settings: Settings | None = None,
    force: bool = False,
    dry_run: bool = False,
    explain: bool = False,
    limit: int | None = None,
) -> BackfillResult:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    ensure_euro_fixture_feed_tables(repo._conn)
    get_competition(competition_key)

    result = BackfillResult(competition_key=competition_key)
    rows = list_missing_uefa_fixtures(repo._conn, competition_key, limit=limit)
    result.scanned = len(rows)

    feed_index = FeedIndex.build(repo._conn, (competition_key,))
    client = ApiFootballClient(settings) if settings.api_football_configured else None
    comp = get_competition(competition_key)
    league_id = comp.league_id
    date_cache = _DateApiCache()

    for row in rows:
        outcome, calls, detail = backfill_single_fixture(
            repo,
            client,
            row,
            competition_key=competition_key,
            league_id=league_id,
            feed_index=feed_index,
            conn=repo._conn,
            date_cache=date_cache,
            force=force,
            dry_run=dry_run,
            explain=explain,
            force_refresh=force,
        )
        result.api_calls += calls
        if explain and detail:
            result.explain_rows.append(detail)

        if outcome == "backfilled":
            result.backfilled += 1
            conf = float(detail.get("match_confidence", 0))
            bucket = _bucket_confidence(conf)
            result.confidence_buckets[bucket] = result.confidence_buckets.get(bucket, 0) + 1
            result.details.append({"fixture_id": row["fixture_id"], "status": "backfilled"})
        elif outcome == "dry_run_would_backfill":
            result.dry_run += 1
            conf = float(detail.get("match_confidence", 0))
            bucket = _bucket_confidence(conf)
            result.confidence_buckets[bucket] = result.confidence_buckets.get(bucket, 0) + 1
            result.details.append({"fixture_id": row["fixture_id"], "status": "would_backfill"})
        elif outcome == "skipped_existing":
            result.skipped_existing += 1
        elif outcome == "not_finished":
            result.skipped_not_finished += 1
        elif outcome == "missing_provider":
            result.missing_provider += 1
            result.missing_mapping.append(
                {
                    "fixture_id": row["fixture_id"],
                    "home_team": row.get("home_team"),
                    "away_team": row.get("away_team"),
                    "kickoff_utc": row.get("kickoff_utc"),
                    "reason": detail.get("reason", "no_provider_payload_or_goals"),
                }
            )
        elif outcome == "skipped_low_confidence":
            result.skipped_low_confidence += 1
        elif outcome == "skipped_ambiguous":
            result.skipped_ambiguous += 1
        else:
            result.errors += 1
            result.details.append({"fixture_id": row["fixture_id"], "status": outcome})

    return result


def audit_missing_uefa_results(
    *,
    competition_keys: list[str] | None = None,
    settings: Settings | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Part A — audit missing UEFA results with candidate matches (no writes)."""
    settings = settings or get_settings()
    keys = competition_keys or list(UEFA_CUP_KEYS)
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    ensure_euro_fixture_feed_tables(repo._conn)
    feed_index = FeedIndex.build(repo._conn, tuple(keys))
    client = ApiFootballClient(settings) if settings.api_football_configured else None
    date_cache = _DateApiCache()

    rows_out: list[dict[str, Any]] = []
    for key in keys:
        comp = get_competition(key)
        missing = list_missing_uefa_fixtures(repo._conn, key, limit=limit)
        for row in missing:
            entry: dict[str, Any] = {
                "fixture_id": row["fixture_id"],
                "competition_key": key,
                "kickoff_utc": row.get("kickoff_utc"),
                "home_team": row.get("home_team"),
                "away_team": row.get("away_team"),
                "provider_source": infer_provider_source(row, feed_index),
                "provider_fixture_id": row["fixture_id"],
                "stored_status": row.get("status"),
                "missing_reason": "no_fixture_results",
                "candidate_matches": [],
            }
            feed_api = lookup_feed_api_id(row, feed_index)
            if feed_api:
                entry["candidate_matches"].append(
                    {
                        "provider": "api-football",
                        "provider_fixture_id": feed_api,
                        "method": "feed_crosswalk",
                        "confidence": 0.99,
                    }
                )

            match, calls, method = resolve_provider_match(
                client,
                row,
                competition_key=key,
                league_id=comp.league_id,
                feed_index=feed_index,
                conn=repo._conn,
                date_cache=date_cache,
            )
            entry["resolve_method"] = method
            entry["api_calls"] = calls
            if match:
                entry["candidate_matches"].append(
                    {
                        "provider": match.provider,
                        "provider_fixture_id": match.provider_fixture_id,
                        "method": match.method,
                        "confidence": match.confidence,
                        "ambiguous": match.ambiguous,
                    }
                )
                if match.ambiguous:
                    entry["missing_reason"] = "ambiguous_provider_match"
                elif not match.persistable:
                    entry["missing_reason"] = "low_confidence_match"
                elif not item_has_goals(match.item):
                    entry["missing_reason"] = "provider_missing_goals"
            else:
                entry["missing_reason"] = "unresolved_provider_match"

            rows_out.append(entry)

    return {
        "phase": PHASE,
        "completed_at_utc": utc_now_iso(),
        "competition_keys": keys,
        "missing_count": len(rows_out),
        "rows": rows_out,
    }


def run_uefa_result_backfill(
    *,
    competition_keys: list[str] | None = None,
    force: bool = False,
    dry_run: bool = False,
    explain: bool = False,
    limit: int | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    keys = competition_keys or list(UEFA_CUP_KEYS)
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)

    before: dict[str, dict[str, int]] = {}
    after: dict[str, dict[str, int]] = {}
    results: list[BackfillResult] = []
    skipped: list[dict[str, str]] = []

    for raw in keys:
        try:
            key = get_competition(raw).key
        except KeyError:
            skipped.append({"competition": raw, "reason": "unknown_competition_key"})
            continue
        if key not in UEFA_CUP_KEYS:
            skipped.append({"competition": key, "reason": "not_uefa_cup_scope"})
            continue
        before[key] = repo.count_competition_coverage(key)
        br = backfill_competition_results(
            key,
            settings=settings,
            force=force,
            dry_run=dry_run,
            explain=explain,
            limit=limit,
        )
        results.append(br)
        after[key] = repo.count_competition_coverage(key)

    return {
        "phase": PHASE,
        "dry_run": dry_run,
        "force": force,
        "explain_matches": explain,
        "limit": limit,
        "before": before,
        "after": after,
        "competitions": [r.to_dict() for r in results],
        "skipped_competitions": skipped,
        "completed_at_utc": utc_now_iso(),
    }
