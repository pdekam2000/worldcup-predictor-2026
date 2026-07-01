"""Part C/D — Cache-first provider fetch with priority ordering and quota guard."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.backtesting.phase31e_backfill import normalize_odds_bookmakers
from worldcup_predictor.owner.euro_c_odds_import import is_fake_odds_payload
from worldcup_predictor.owner.euro_b_fixture_selector import _odds_flags
from worldcup_predictor.owner_daily.constants import DEFAULT_PREMATCH_WINDOW_HOURS, PHASE
from worldcup_predictor.owner_daily.data_completeness import FixtureCompletenessReport
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture
from worldcup_predictor.owner_daily.provider_call_log import DailyProviderCallLog
from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider
from worldcup_predictor.quota.local_first import UNFINISHED_LOCAL_STATUSES, should_bypass_stale_local_fixture


FETCH_PRIORITY: tuple[tuple[str, str, str], ...] = (
    ("fixtures", "api_football", "HIGH"),
    ("fixture_status", "api_football", "HIGH"),
    ("odds_1x2", "api_football", "HIGH"),
    ("odds_ou_2_5", "api_football", "HIGH"),
    ("odds_btts", "api_football", "HIGH"),
    ("wde_inputs", "api_football", "HIGH"),
    ("ecse_lambda_inputs", "api_football", "HIGH"),
    ("lineups", "api_football", "MEDIUM"),
    ("injuries", "api_football", "MEDIUM"),
    ("standings", "api_football", "MEDIUM"),
    ("recent_form", "api_football", "MEDIUM"),
    ("head_to_head", "api_football", "MEDIUM"),
    ("team_statistics", "api_football", "MEDIUM"),
    ("referee", "api_football", "MEDIUM"),
    ("xg", "sportmonks", "LOW"),
    ("pressure_index", "sportmonks", "LOW"),
    ("events", "api_football", "LOW"),
    ("odds_correct_score", "oddalerts", "LOW"),
    ("player_stats", "api_football", "LOW"),
)


@dataclass
class ProviderFetchResult:
    phase: str = PHASE
    fetched: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "fetched": self.fetched,
            "skipped": self.skipped,
            "errors": self.errors,
        }


def _parse_kickoff(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def should_force_refresh_fixture(
    fixture: DailyFixture,
    repo: FootballIntelligenceRepository,
    *,
    force_refresh: bool = False,
    prematch_window_hours: float = DEFAULT_PREMATCH_WINDOW_HOURS,
) -> bool:
    if force_refresh:
        return True
    row = repo.get_fixture_row(fixture.provider_fixture_id) or {}
    if should_bypass_stale_local_fixture(row):
        return True
    status = str(fixture.status or row.get("status") or "NS").upper()
    if status in {"1H", "HT", "2H", "ET", "LIVE", "BT", "P"}:
        return True
    ko = _parse_kickoff(fixture.kickoff_utc)
    if ko is None:
        return False
    now = datetime.now(timezone.utc)
    window = timedelta(hours=prematch_window_hours)
    return now <= ko <= now + window


def _fetch_api_football_odds(
    *,
    fixture: DailyFixture,
    settings: Settings,
    conn: sqlite3.Connection,
    call_log: DailyProviderCallLog,
    only_missing: bool,
    force_refresh: bool,
    dry_run: bool,
) -> bool:
    fid = fixture.provider_fixture_id
    if only_missing:
        odds = _odds_flags(conn, fid)
        if odds.get("has_odds") and odds.get("odds_1x2") and odds.get("odds_ou") and odds.get("odds_btts"):
            call_log.record(
                provider="api_football",
                endpoint="odds",
                action="skip_cached",
                fixture_id=fid,
                provider_fixture_id=fid,
                competition_key=fixture.competition_key,
                request_reason="fresh_odds_exist",
                cache_hit=True,
                call_made=False,
                success=True,
            )
            return False

    api = ApiFootballClient(settings)
    if not api.is_configured or not call_log.quota.can_call("api_football"):
        return False

    call_log.record(
        provider="api_football",
        endpoint="odds",
        action="fetch_odds",
        fixture_id=fid,
        provider_fixture_id=fid,
        competition_key=fixture.competition_key,
        request_reason="missing_odds",
        call_made=True,
        success=False,
    )
    if dry_run:
        call_log.entries[-1]["success"] = True
        return True

    result = api.get_odds(fid)
    cache_hit = str(getattr(result, "source", "")) == "cache"
    call_log.entries[-1]["cache_hit"] = cache_hit
    call_log.entries[-1]["success"] = result.ok
    if not result.ok or is_fake_odds_payload(result.data, source=result.source):
        return False

    bookmakers = normalize_odds_bookmakers(result.data)
    if not bookmakers:
        return False
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    repo.save_snapshot(
        "odds_snapshots",
        fixture_id=fid,
        competition_key=fixture.competition_key,
        payload={"bookmakers": bookmakers, "source": result.source, "provider": "api-football"},
    )
    return True


def _fetch_oddalerts_odds_fallback(
    *,
    fixture: DailyFixture,
    settings: Settings,
    call_log: DailyProviderCallLog,
    dry_run: bool,
) -> bool:
    oa = OddAlertsClient()
    if not oa.is_configured or not call_log.quota.can_call("oddalerts"):
        return False
    call_log.record(
        provider="oddalerts",
        endpoint="odds/history",
        action="fetch_odds_fallback",
        fixture_id=fixture.provider_fixture_id,
        competition_key=fixture.competition_key,
        request_reason="api_football_odds_missing",
        call_made=True,
        success=False,
    )
    if dry_run:
        call_log.entries[-1]["success"] = True
        return True
    result = oa.get_odds_history(fixture.provider_fixture_id)
    call_log.entries[-1]["success"] = result.data is not None and not result.error
    return call_log.entries[-1]["success"]


def _fetch_fixture_status(
    *,
    fixture: DailyFixture,
    settings: Settings,
    repo: FootballIntelligenceRepository,
    call_log: DailyProviderCallLog,
    force_refresh: bool,
    dry_run: bool,
) -> bool:
    api = ApiFootballClient(settings)
    if not api.is_configured or not call_log.quota.can_call("api_football"):
        return False
    fid = fixture.provider_fixture_id
    call_log.record(
        provider="api_football",
        endpoint="fixtures",
        action="status_refresh",
        fixture_id=fid,
        competition_key=fixture.competition_key,
        request_reason="stale_or_live_status",
        call_made=True,
        success=False,
    )
    if dry_run:
        call_log.entries[-1]["success"] = True
        return True
    call = api._safe_get(  # noqa: SLF001
        "fixtures",
        {"id": fid},
        placeholder_factory=lambda: None,
        force_refresh=force_refresh,
    )
    cache_hit = str(call.source) == "cache"
    call_log.entries[-1]["cache_hit"] = cache_hit
    call_log.entries[-1]["success"] = call.ok
    if not call.ok or not call.data:
        return False
    from worldcup_predictor.integrations.fixture_api_parser import parse_api_fixture_item

    item = call.data[0] if isinstance(call.data, list) else call.data
    if not isinstance(item, dict):
        return False
    parsed = parse_api_fixture_item(item, source=str(call.source or "api-football"))
    if parsed:
        repo.upsert_fixture(parsed, competition_key=fixture.competition_key)
    return True


def fetch_missing_data_for_fixtures(
    conn: sqlite3.Connection,
    fixtures: list[DailyFixture],
    completeness_reports: list[FixtureCompletenessReport],
    *,
    settings: Settings | None = None,
    call_log: DailyProviderCallLog | None = None,
    only_missing: bool = True,
    force_refresh: bool = False,
    dry_run: bool = False,
    no_provider_calls: bool = False,
) -> ProviderFetchResult:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    result = ProviderFetchResult()
    log = call_log or DailyProviderCallLog(run_date=datetime.now(timezone.utc).date().isoformat())
    if no_provider_calls:
        log.quota.no_provider_calls = True

    sm = SportmonksProvider(settings)
    api_ok = settings.api_football_configured
    sm_ok = sm.is_configured
    oa_ok = OddAlertsClient().is_configured

    report_by_id = {r.fixture_id: r for r in completeness_reports}

    for fixture in fixtures:
        report = report_by_id.get(fixture.provider_fixture_id)
        if report is None:
            continue
        needs_refresh = should_force_refresh_fixture(
            fixture, repo, force_refresh=force_refresh
        )
        high_missing = {m.missing_field for m in report.missing if m.priority == "HIGH"}

        if "fixture_status_refresh" in high_missing or needs_refresh:
            if _fetch_fixture_status(
                fixture=fixture,
                settings=settings,
                repo=repo,
                call_log=log,
                force_refresh=needs_refresh,
                dry_run=dry_run,
            ):
                result.fetched["fixture_status"] = result.fetched.get("fixture_status", 0) + 1
            else:
                result.skipped["fixture_status"] = result.skipped.get("fixture_status", 0) + 1

        odds_fields = {"odds_1x2", "odds_ou_2_5", "odds_btts", "odds_ou_1_5"}
        if odds_fields & high_missing or (not only_missing and needs_refresh):
            got = _fetch_api_football_odds(
                fixture=fixture,
                settings=settings,
                conn=conn,
                call_log=log,
                only_missing=only_missing,
                force_refresh=needs_refresh,
                dry_run=dry_run,
            )
            if got:
                result.fetched["odds"] = result.fetched.get("odds", 0) + 1
            elif api_ok:
                if _fetch_oddalerts_odds_fallback(
                    fixture=fixture, settings=settings, call_log=log, dry_run=dry_run
                ):
                    result.fetched["odds_oddalerts"] = result.fetched.get("odds_oddalerts", 0) + 1
                else:
                    result.skipped["odds"] = result.skipped.get("odds", 0) + 1

        if "xg" in {m.missing_field for m in report.missing} and sm_ok and log.quota.can_call("sportmonks"):
            log.record(
                provider="sportmonks",
                endpoint="xg",
                action="enrich_xg",
                fixture_id=fixture.provider_fixture_id,
                competition_key=fixture.competition_key,
                request_reason="advanced_enrichment",
                call_made=not dry_run,
                success=not dry_run,
            )
            if not dry_run:
                result.fetched["xg"] = result.fetched.get("xg", 0) + 1

    return result
