"""PHASE DAILY-OWNER-2 — Daily odds readiness scan + cache-first import."""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone as dt_timezone
from pathlib import Path
from typing import Any, Literal

from worldcup_predictor.backtesting.phase31e_backfill import (
    collect_cached_odds_sources,
    normalize_odds_bookmakers,
)
from worldcup_predictor.cache.api_cache import get_api_cache
from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.clients.api_response import ApiCallResult
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.egie.provider_features.odds_snapshot_parser import (
    NormalizedOddsLine,
    normalize_snapshot_odds_lines,
    _implied_prob,
    _normalize_probs,
)
from worldcup_predictor.owner.euro_c_odds_import import (
    _build_storage_payload,
    _count_api_live,
    _existing_is_newer_than,
    _latest_odds_snapshot,
    _markets_complete,
    _parse_snapshot_time,
    _utc_now_iso,
    assess_ecse_readiness,
    is_fake_odds_payload,
    normalize_uefa_odds_snapshot,
    NormalizedOddsSnapshot,
)
from worldcup_predictor.owner_daily.constants import ARTIFACTS_DIR, PHASE
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture, discover_daily_fixtures
from worldcup_predictor.owner_daily.provider_call_log import DailyProviderCallLog, ProviderQuotaGuard
from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider
from worldcup_predictor.research.safe_bets.providers import (
    fetch_oddalerts_odds_history,
    fetch_sportmonks_odds_from_cache,
)

PHASE_ODDS = "DAILY-OWNER-2"
ODDS_STALE_HOURS = 6.0
RAW_DIR = Path("artifacts/daily_owner/raw_odds_payloads")

FreshnessStatus = Literal["fresh", "stale", "missing"]


def _parse_kickoff(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=dt_timezone.utc)
    return dt.astimezone(dt_timezone.utc)


def odds_freshness(snapshot_at: str | None, kickoff_utc: str | None) -> FreshnessStatus:
    if not snapshot_at:
        return "missing"
    snap = _parse_snapshot_time(snapshot_at)
    if snap is None:
        return "missing"
    now = datetime.now(dt_timezone.utc)
    age_hours = (now - snap).total_seconds() / 3600.0
    ko = _parse_kickoff(kickoff_utc)
    if ko and now > ko:
        return "stale" if age_hours > 24 else "fresh"
    if age_hours > ODDS_STALE_HOURS:
        return "stale"
    return "fresh"


def _parse_implied_double_chance(lines: list[NormalizedOddsLine]) -> dict[str, float]:
    per_bm: dict[str, dict[str, float]] = {}
    for line in lines:
        if "double chance" not in line.market_name.lower():
            continue
        key = line.selection.lower().strip()
        mapping = {
            "home/draw": "1x",
            "home or draw": "1x",
            "1x": "1x",
            "draw/away": "x2",
            "draw or away": "x2",
            "x2": "x2",
            "home/away": "12",
            "home or away": "12",
            "12": "12",
        }
        norm_key = mapping.get(key)
        if not norm_key:
            continue
        implied = _implied_prob(line.odd)
        if implied is None:
            continue
        per_bm.setdefault(line.bookmaker, {})[norm_key] = implied
    rows = [_normalize_probs(v) for v in per_bm.values() if v]
    if not rows:
        return {}
    keys = ("1x", "12", "x2")
    totals = {k: 0.0 for k in keys}
    counts = {k: 0 for k in keys}
    for row in rows:
        for k in keys:
            if k in row:
                totals[k] += row[k]
                counts[k] += 1
    return _normalize_probs({k: totals[k] / counts[k] for k in keys if counts[k] > 0})


def flattened_probabilities(normalized: NormalizedOddsSnapshot) -> dict[str, Any]:
    """Part C — flat probability fields for WDE/ECSE consumers."""
    mw = normalized.match_winner or {}
    ou15 = normalized.over_under_1_5 or {}
    ou25 = normalized.over_under_2_5 or {}
    ou35 = normalized.over_under_3_5 or {}
    btts = normalized.btts or {}

    return {
        "ph": mw.get("home"),
        "pd": mw.get("draw"),
        "pa": mw.get("away"),
        "p_o15": ou15.get("over_1_5"),
        "p_u15": ou15.get("under_1_5"),
        "p_o25": ou25.get("over_2_5"),
        "p_u25": ou25.get("under_2_5"),
        "p_o35": ou35.get("over_3_5"),
        "p_u35": ou35.get("under_3_5"),
        "p_btts_yes": btts.get("yes"),
        "p_btts_no": btts.get("no"),
        "p_dc_1x": None,
        "p_dc_12": None,
        "p_dc_x2": None,
        "has_correct_score": normalized.has_correct_score,
        "bookmaker_count": normalized.bookmaker_count,
        "consensus_method": normalized.consensus_method,
        "overround_1x2": normalized.overround_1x2,
    }


def flattened_probabilities_from_snapshot(
    normalized: NormalizedOddsSnapshot,
    *,
    bookmakers: list[Any] | None = None,
) -> dict[str, Any]:
    flat = flattened_probabilities(normalized)
    if bookmakers:
        lines = normalize_snapshot_odds_lines({"bookmakers": bookmakers})
        dc = _parse_implied_double_chance(lines)
        flat["p_dc_1x"] = dc.get("1x")
        flat["p_dc_12"] = dc.get("12")
        flat["p_dc_x2"] = dc.get("x2")
    return flat


def _probabilities_valid(normalized: NormalizedOddsSnapshot) -> bool:
    for market_name, probs in (normalized.normalized_probabilities or {}).items():
        if not isinstance(probs, dict):
            continue
        for v in probs.values():
            if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v) or v < 0 or v > 1)):
                return False
    return True


def _wde_ready(conn: sqlite3.Connection, fixture_id: int, *, has_required_odds: bool) -> bool:
    row = conn.execute(
        "SELECT 1 FROM fixtures WHERE fixture_id = ? AND is_placeholder = 0 LIMIT 1",
        (int(fixture_id),),
    ).fetchone()
    if not row:
        return False
    if has_required_odds:
        return True
    stored = conn.execute(
        "SELECT 1 FROM worldcup_stored_predictions WHERE fixture_id = ? LIMIT 1",
        (int(fixture_id),),
    ).fetchone()
    return bool(stored)


def _can_fetch_sportmonks(conn: sqlite3.Connection, fixture_id: int, sm: SportmonksProvider) -> bool:
    if not sm.is_configured:
        return False
    try:
        row = conn.execute(
            """
            SELECT 1 FROM sportmonks_fixture_enrichment
            WHERE api_fixture_id = ? OR fixture_id_api_football = ?
            LIMIT 1
            """,
            (int(fixture_id), int(fixture_id)),
        ).fetchone()
        return row is not None
    except sqlite3.OperationalError:
        return sm.is_configured


def scan_fixture_odds_readiness(
    conn: sqlite3.Connection,
    fixture: DailyFixture,
    *,
    settings: Settings,
    sm: SportmonksProvider | None = None,
    oa: OddAlertsClient | None = None,
) -> dict[str, Any]:
    fid = fixture.provider_fixture_id
    snap = _latest_odds_snapshot(conn, fid)
    payload = snap["payload"] if snap else None
    source = None
    snapshot_time = snap["snapshot_at"] if snap else None
    if payload and isinstance(payload, dict):
        source = str(
            payload.get("provider")
            or payload.get("api_call_source")
            or payload.get("source")
            or "odds_snapshots"
        )
    if payload and is_fake_odds_payload(payload, source=source):
        payload = None
        source = None
        snapshot_time = None

    normalized = normalize_uefa_odds_snapshot(payload, fixture_id=fid) if payload else None
    readiness = assess_ecse_readiness(conn, fid, normalized=normalized)
    freshness = odds_freshness(snapshot_time, fixture.kickoff_utc)

    sm = sm or SportmonksProvider(settings)
    oa = oa or OddAlertsClient()

    missing = list(normalized.missing_markets) if normalized else [
        "match_winner",
        "over_under_2_5",
        "btts",
        "over_under_1_5",
        "over_under_3_5",
        "correct_score",
        "double_chance",
    ]
    required_missing = [m for m in missing if m in ("match_winner", "over_under_2_5", "btts")]

    has_required = readiness["has_1x2"] and readiness["has_ou25"] and readiness["has_btts"]
    flat = (
        flattened_probabilities_from_snapshot(
            normalized,
            bookmakers=(payload or {}).get("bookmakers") if isinstance(payload, dict) else None,
        )
        if normalized
        else {}
    )

    return {
        "fixture_id": fid,
        "competition_key": fixture.competition_key,
        "kickoff_time": fixture.kickoff_utc,
        "home_team": fixture.home_team,
        "away_team": fixture.away_team,
        "has_1x2": readiness["has_1x2"],
        "has_ou25": readiness["has_ou25"],
        "has_btts": readiness["has_btts"],
        "has_ou15": bool(normalized and normalized.over_under_1_5),
        "has_ou35": bool(normalized and normalized.over_under_3_5),
        "has_double_chance": bool(normalized and normalized.has_double_chance),
        "has_correct_score": bool(normalized and normalized.has_correct_score),
        "odds_source": source,
        "odds_snapshot_time": snapshot_time,
        "odds_freshness": freshness,
        "missing_markets": missing,
        "required_missing_markets": required_missing,
        "wde_ready": _wde_ready(conn, fid, has_required_odds=has_required),
        "ecse_ready": readiness["ecse_ready"],
        "lambda_inputs_available": readiness["lambda_inputs_available"],
        "normalized_probabilities": flat,
        "can_fetch_from_api_football": settings.api_football_configured,
        "can_fetch_from_oddalerts": oa.is_configured,
        "can_fetch_from_sportmonks": _can_fetch_sportmonks(conn, fid, sm),
    }


def scan_daily_odds_readiness(
    *,
    date_arg: str = "today",
    tz_name: str = "Europe/Vienna",
    timezone: str | None = None,
    competition_keys: list[str] | None = None,
    limit: int = 50,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    tz_name = timezone or tz_name
    discovery = discover_daily_fixtures(
        date_arg=date_arg,
        timezone=tz_name,
        competition_keys=competition_keys,
        limit=limit,
        settings=settings,
        fetch_if_missing=False,
    )
    conn = connect(settings.sqlite_path)
    sm = SportmonksProvider(settings)
    oa = OddAlertsClient()
    rows = [
        scan_fixture_odds_readiness(conn, fx, settings=settings, sm=sm, oa=oa)
        for fx in discovery.fixtures
    ]
    return {
        "phase": PHASE_ODDS,
        "generated_at_utc": _utc_now_iso(),
        "target_date": discovery.target_date,
        "timezone": tz_name,
        "fixtures_scanned": len(rows),
        "wde_ready_count": sum(1 for r in rows if r["wde_ready"]),
        "ecse_ready_count": sum(1 for r in rows if r["ecse_ready"]),
        "fixtures_with_1x2": sum(1 for r in rows if r["has_1x2"]),
        "fixtures_with_ou25": sum(1 for r in rows if r["has_ou25"]),
        "fixtures_with_btts": sum(1 for r in rows if r["has_btts"]),
        "fixtures": rows,
    }


def _oddalerts_lines_to_bookmakers(lines: list[Any]) -> list[dict[str, Any]]:
    by_bm: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for line in lines:
        bm = str(getattr(line, "bookmaker", "oddalerts"))
        market = str(getattr(line, "market_name", "unknown"))
        by_bm.setdefault(bm, {}).setdefault(market, []).append(
            {
                "value": str(getattr(line, "selection", "")),
                "odd": str(getattr(line, "odd", "")),
            }
        )
    out: list[dict[str, Any]] = []
    for name, markets in by_bm.items():
        bets = [{"name": mname, "values": vals} for mname, vals in markets.items()]
        out.append({"name": name, "bets": bets})
    return out


def _sportmonks_lines_to_bookmakers(lines: list[Any]) -> list[dict[str, Any]]:
    return _oddalerts_lines_to_bookmakers(lines)


def _build_daily_storage_payload(
    *,
    bookmakers: list[Any],
    normalized: NormalizedOddsSnapshot,
    provider: str,
    provider_fixture_id: int,
    api_source: str,
    raw_path: str | None,
    freshness: FreshnessStatus,
) -> dict[str, Any]:
    flat = flattened_probabilities_from_snapshot(normalized, bookmakers=bookmakers)
    base = _build_storage_payload(
        bookmakers=bookmakers,
        normalized=normalized,
        provider=provider,
        provider_fixture_id=provider_fixture_id,
        api_source=api_source,
        raw_path=raw_path,
    )
    base["phase"] = PHASE_ODDS
    base["source"] = f"daily_owner_{provider}_import"
    base["freshness_status"] = freshness
    base["flat_probabilities"] = flat
    return base


@dataclass
class DailyOddsImportResult:
    phase: str = PHASE_ODDS
    dry_run: bool = False
    fixtures_scanned: int = 0
    fixtures_with_odds_before: int = 0
    fixtures_with_odds_after: int = 0
    imported_count: int = 0
    cache_hits: int = 0
    skipped: list[dict[str, Any]] = field(default_factory=list)
    imported: list[dict[str, Any]] = field(default_factory=list)
    provider_errors: list[dict[str, Any]] = field(default_factory=list)
    provider_calls: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "dry_run": self.dry_run,
            "fixtures_scanned": self.fixtures_scanned,
            "fixtures_with_odds_before": self.fixtures_with_odds_before,
            "fixtures_with_odds_after": self.fixtures_with_odds_after,
            "imported_count": self.imported_count,
            "cache_hits": self.cache_hits,
            "skipped": self.skipped[:100],
            "imported": self.imported[:100],
            "provider_errors": self.provider_errors[:50],
            "provider_calls": self.provider_calls,
        }


def import_daily_odds(
    *,
    date_arg: str = "today",
    tz_name: str = "Europe/Vienna",
    timezone: str | None = None,
    competition_keys: list[str] | None = None,
    limit: int = 50,
    settings: Settings | None = None,
    dry_run: bool = False,
    only_missing: bool = True,
    force: bool = False,
    call_log: DailyProviderCallLog | None = None,
    max_api_football_calls: int = 100,
    max_oddalerts_calls: int = 100,
    max_sportmonks_calls: int = 100,
    no_provider_calls: bool = False,
) -> DailyOddsImportResult:
    settings = settings or get_settings()
    tz_name = timezone or tz_name
    from worldcup_predictor.owner_daily.fixture_discovery import resolve_target_date

    target = resolve_target_date(date_arg, tz_name)
    discovery = discover_daily_fixtures(
        date_arg=date_arg,
        timezone=tz_name,
        competition_keys=competition_keys,
        limit=limit,
        settings=settings,
        fetch_if_missing=False,
    )

    log = call_log or DailyProviderCallLog(
        run_date=target.isoformat(),
        quota=ProviderQuotaGuard(
            max_api_football=max_api_football_calls,
            max_sportmonks=max_sportmonks_calls,
            max_oddalerts=max_oddalerts_calls,
            no_provider_calls=no_provider_calls,
        ),
    )

    conn = connect(settings.sqlite_path)
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    api = ApiFootballClient(settings)
    sm = SportmonksProvider(settings)
    oa = OddAlertsClient()
    disk_cache = get_api_cache(settings.api_cache_dir, settings.api_cache_ttl_seconds)
    cached_sources = collect_cached_odds_sources(repo, disk_cache=disk_cache)

    result = DailyOddsImportResult(dry_run=dry_run, fixtures_scanned=len(discovery.fixtures))
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(dt_timezone.utc).strftime("%Y%m%d_%H%M%S")

    for fx in discovery.fixtures:
        fid = fx.provider_fixture_id
        comp = fx.competition_key
        entry_base = {
            "fixture_id": fid,
            "competition_key": comp,
            "home_team": fx.home_team,
            "away_team": fx.away_team,
        }

        before = scan_fixture_odds_readiness(conn, fx, settings=settings, sm=sm, oa=oa)
        if before["has_1x2"] and before["has_ou25"] and before["has_btts"]:
            result.fixtures_with_odds_before += 1
            if only_missing and before["odds_freshness"] == "fresh" and not force:
                result.skipped.append({**entry_base, "reason": "fresh_complete_odds"})
                log.record(
                    provider="local",
                    endpoint="odds_snapshots",
                    action="skip_cached",
                    fixture_id=fid,
                    provider_fixture_id=fid,
                    competition_key=comp,
                    market="all",
                    request_reason="fresh_complete_odds",
                    cache_hit=True,
                    call_made=False,
                    success=True,
                )
                continue

        existing = _latest_odds_snapshot(conn, fid)
        bookmakers: list[Any] = []
        provider = ""
        api_source = "none"
        raw_path: str | None = None
        cache_hit = False

        if cache_hit_entry := cached_sources.get(fid):
            bookmakers = list(cache_hit_entry.get("bookmakers") or [])
            api_source = str(cache_hit_entry.get("source") or "cache")
            provider = "api-football"
            cache_hit = True
            result.cache_hits += 1
            log.record(
                provider="api_football",
                endpoint="odds",
                action="disk_cache_hit",
                fixture_id=fid,
                provider_fixture_id=fid,
                competition_key=comp,
                market="all",
                request_reason="cache_first",
                cache_hit=True,
                call_made=False,
                success=bool(bookmakers),
            )

        if not bookmakers and not no_provider_calls and api.is_configured and log.quota.can_call("api_football"):
            log.record(
                provider="api_football",
                endpoint="odds",
                action="fetch_odds",
                fixture_id=fid,
                provider_fixture_id=fid,
                competition_key=comp,
                market="all",
                request_reason="missing_or_stale_odds",
                call_made=True,
                success=False,
            )
            if dry_run:
                log.entries[-1]["success"] = True
                result.skipped.append({**entry_base, "reason": "dry_run_would_fetch_api_football"})
                continue

            odds_result = api.get_odds(fid)
            live_cache = str(odds_result.source) == "cache"
            log.entries[-1]["cache_hit"] = live_cache
            log.entries[-1]["success"] = odds_result.ok
            result.provider_calls["api_football"] = result.provider_calls.get("api_football", 0) + (
                0 if live_cache else 1
            )

            if odds_result.ok and not is_fake_odds_payload(odds_result.data, source=odds_result.source):
                bookmakers = normalize_odds_bookmakers(odds_result.data)
                provider = "api-football"
                api_source = odds_result.source
                if bookmakers:
                    raw_path = str(RAW_DIR / f"{fid}_{stamp}_api-football.json")
                    Path(raw_path).write_text(
                        json.dumps(
                            {"fixture_id": fid, "fetched_at": _utc_now_iso(), "data": odds_result.data},
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )

        if not bookmakers and not no_provider_calls and oa.is_configured and log.quota.can_call("oddalerts"):
            log.record(
                provider="oddalerts",
                endpoint="odds/history",
                action="fetch_odds_fallback",
                fixture_id=fid,
                provider_fixture_id=fid,
                competition_key=comp,
                market="all",
                request_reason="api_football_missing",
                call_made=True,
                success=False,
            )
            if not dry_run:
                oa_res = fetch_oddalerts_odds_history(fid, conn=conn)
                result.provider_calls["oddalerts"] = result.provider_calls.get("oddalerts", 0) + oa_res.api_calls
                if oa_res.lines:
                    bookmakers = _oddalerts_lines_to_bookmakers(oa_res.lines)
                    provider = "oddalerts"
                    api_source = "oddalerts"
                    raw_path = str(RAW_DIR / f"{fid}_{stamp}_oddalerts.json")
                    Path(raw_path).write_text(
                        json.dumps({"fixture_id": fid, "lines": len(oa_res.lines)}, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    log.entries[-1]["success"] = True
            else:
                log.entries[-1]["success"] = True

        if not bookmakers and not no_provider_calls and log.quota.can_call("sportmonks"):
            sm_cached = fetch_sportmonks_odds_from_cache(conn, fid)
            if sm_cached.lines:
                bookmakers = _sportmonks_lines_to_bookmakers(sm_cached.lines)
                provider = "sportmonks"
                api_source = "sportmonks_cache"
                cache_hit = True
                result.cache_hits += 1
                log.record(
                    provider="sportmonks",
                    endpoint="enrichment_cache",
                    action="read_odds_cache",
                    fixture_id=fid,
                    provider_fixture_id=fid,
                    competition_key=comp,
                    market="all",
                    request_reason="sportmonks_crosswalk_cache",
                    cache_hit=True,
                    call_made=False,
                    success=True,
                )

        if not bookmakers:
            result.skipped.append({**entry_base, "reason": "no_odds_available"})
            result.provider_errors.append({**entry_base, "error": "no_odds_available"})
            continue

        normalized = normalize_uefa_odds_snapshot(bookmakers, fixture_id=fid, raw_odds_path=raw_path)
        if not _probabilities_valid(normalized):
            result.skipped.append({**entry_base, "reason": "invalid_probabilities"})
            continue

        if existing and only_missing and _markets_complete(normalized) and not force:
            if _existing_is_newer_than(existing.get("snapshot_at"), _utc_now_iso()):
                result.skipped.append({**entry_base, "reason": "newer_snapshot_exists"})
                continue

        freshness: FreshnessStatus = "fresh"
        payload = _build_daily_storage_payload(
            bookmakers=bookmakers,
            normalized=normalized,
            provider=provider,
            provider_fixture_id=fid,
            api_source=api_source,
            raw_path=raw_path,
            freshness=freshness,
        )

        if dry_run:
            result.imported.append({**entry_base, "provider": provider, "dry_run": True})
            continue

        repo.save_snapshot(
            "odds_snapshots",
            fixture_id=fid,
            competition_key=comp,
            payload=payload,
            snapshot_at=payload.get("snapshot_at"),
        )
        result.imported_count += 1
        result.imported.append({**entry_base, "provider": provider, "markets": normalized.missing_markets})

    for fx in discovery.fixtures:
        after = scan_fixture_odds_readiness(conn, fx, settings=settings, sm=sm, oa=oa)
        if after["has_1x2"] and after["has_ou25"] and after["has_btts"]:
            result.fixtures_with_odds_after += 1

    ymd = target.isoformat().replace("-", "")
    artifact = ARTIFACTS_DIR / f"daily_odds_import_{ymd}.json"
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    if log.entries:
        log.flush()

    return result
