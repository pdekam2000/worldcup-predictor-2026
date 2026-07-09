"""Orchestrator for the full daily owner prediction cycle."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.owner_daily.constants import (
    ARTIFACTS_DIR,
    DAILY_SUPPORTED_COMPETITIONS,
    DEFAULT_MAX_API_FOOTBALL_CALLS,
    DEFAULT_MAX_ODDALERTS_CALLS,
    DEFAULT_MAX_SPORTMONKS_CALLS,
    PHASE,
)
from worldcup_predictor.owner_daily.data_completeness import (
    check_all_fixtures_completeness,
    summarize_completeness,
)
from worldcup_predictor.owner_daily.fixture_discovery import discover_daily_fixtures, resolve_target_date
from worldcup_predictor.owner_daily.predictions import run_daily_predictions
from worldcup_predictor.owner_daily.provider_call_log import DailyProviderCallLog, ProviderQuotaGuard
from worldcup_predictor.owner_daily.odds_import import import_daily_odds, scan_daily_odds_readiness
from worldcup_predictor.owner_daily.report import build_daily_report
from worldcup_predictor.owner_daily.result_sync import run_daily_result_sync_and_evaluation
from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider


@dataclass
class DailyCycleConfig:
    date_arg: str = "today"
    timezone: str = "Europe/Vienna"
    competition_keys: list[str] | None = None
    limit: int = 50
    max_api_football_calls: int = DEFAULT_MAX_API_FOOTBALL_CALLS
    max_sportmonks_calls: int = DEFAULT_MAX_SPORTMONKS_CALLS
    max_oddalerts_calls: int = DEFAULT_MAX_ODDALERTS_CALLS
    dry_run: bool = False
    only_missing: bool = True
    force_refresh: bool = False
    no_provider_calls: bool = False
    force_predictions: bool = False
    skip_result_sync: bool = False
    fetch_missing_odds: bool = False
    include_shadow: bool = False
    refresh_stale_odds: bool = False
    max_odds_provider_calls: int = 20
    strict_fresh_odds: bool = False
    fixture_id: int | None = None


@dataclass
class DailyCycleResult:
    phase: str = PHASE
    config: dict[str, Any] = field(default_factory=dict)
    discovery: dict[str, Any] = field(default_factory=dict)
    fetch: dict[str, Any] = field(default_factory=dict)
    predictions: dict[str, Any] = field(default_factory=dict)
    result_sync: dict[str, Any] = field(default_factory=dict)
    report_paths: dict[str, str] = field(default_factory=dict)
    completeness_artifact: str = ""

    odds_import: dict[str, Any] = field(default_factory=dict)
    odds_readiness_before: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "config": self.config,
            "discovery": self.discovery,
            "odds_readiness_before": self.odds_readiness_before,
            "odds_import": self.odds_import,
            "fetch": self.fetch,
            "predictions": self.predictions,
            "result_sync": self.result_sync,
            "report_paths": self.report_paths,
            "completeness_artifact": self.completeness_artifact,
        }


def run_daily_owner_cycle(
    config: DailyCycleConfig,
    *,
    settings: Settings | None = None,
) -> DailyCycleResult:
    settings = settings or get_settings()
    target = resolve_target_date(config.date_arg, config.timezone)
    keys = config.competition_keys or list(DAILY_SUPPORTED_COMPETITIONS)

    call_log = DailyProviderCallLog(
        run_date=target.isoformat(),
        quota=ProviderQuotaGuard(
            max_api_football=config.max_api_football_calls,
            max_sportmonks=config.max_sportmonks_calls,
            max_oddalerts=config.max_oddalerts_calls,
            no_provider_calls=config.no_provider_calls,
        ),
    )

    result = DailyCycleResult(
        config={
            "date": target.isoformat(),
            "timezone": config.timezone,
            "competitions": keys,
            "dry_run": config.dry_run,
            "only_missing": config.only_missing,
            "force_refresh": config.force_refresh,
            "no_provider_calls": config.no_provider_calls,
            "fetch_missing_odds": config.fetch_missing_odds,
            "include_shadow": config.include_shadow,
            "refresh_stale_odds": config.refresh_stale_odds,
            "max_odds_provider_calls": config.max_odds_provider_calls,
            "strict_fresh_odds": config.strict_fresh_odds,
            "fixture_id": config.fixture_id,
        }
    )

    if not config.skip_result_sync:
        pre_sync = run_daily_result_sync_and_evaluation(
            competition_keys=keys,
            settings=settings,
            dry_run=config.dry_run,
            force=config.force_refresh,
        )
        result.result_sync["pre"] = pre_sync.to_dict()

    discovery = discover_daily_fixtures(
        date_arg=config.date_arg,
        timezone=config.timezone,
        competition_keys=keys,
        limit=config.limit,
        settings=settings,
        fetch_if_missing=not config.no_provider_calls,
        call_log=call_log,
        dry_run=config.dry_run,
    )
    result.discovery = discovery.to_dict()

    if config.fixture_id is not None:
        fid = int(config.fixture_id)
        discovery.fixtures = [f for f in discovery.fixtures if int(f.provider_fixture_id) == fid]
        if not discovery.fixtures:
            conn_single = connect(settings.sqlite_path)
            row = conn_single.execute(
                """SELECT fixture_id, home_team, away_team, kickoff_utc, status, competition_key
                   FROM fixtures WHERE fixture_id=? AND is_placeholder=0 LIMIT 1""",
                (fid,),
            ).fetchone()
            conn_single.close()
            if row:
                from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture

                discovery.fixtures = [
                    DailyFixture(
                        fixture_id=int(row["fixture_id"]),
                        provider_fixture_id=int(row["fixture_id"]),
                        competition_key=str(row["competition_key"]),
                        home_team=str(row["home_team"]),
                        away_team=str(row["away_team"]),
                        kickoff_utc=str(row["kickoff_utc"] or ""),
                        status=str(row["status"] or "NS"),
                        season=None,
                        coverage_sources=["local_db"],
                    )
                ]
        result.discovery = discovery.to_dict()
        result.discovery["fixture_filter"] = fid

    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    conn = connect(settings.sqlite_path)
    sm = SportmonksProvider(settings)
    oa = OddAlertsClient()

    completeness = check_all_fixtures_completeness(
        conn,
        repo,
        discovery.fixtures,
        api_football_configured=settings.api_football_configured,
        sportmonks_configured=sm.is_configured,
        oddalerts_configured=oa.is_configured,
    )

    result.odds_readiness_before = scan_daily_odds_readiness(
        date_arg=config.date_arg,
        timezone=config.timezone,
        competition_keys=keys,
        limit=config.limit,
        settings=settings,
    )

    refreshed_for_prediction = False
    if config.refresh_stale_odds and not config.no_provider_calls:
        from worldcup_predictor.odds.freshness_refresh import run_odds_freshness_refresh

        refresh_out = run_odds_freshness_refresh(
            date_arg=config.date_arg,
            timezone=config.timezone,
            competition_keys=keys,
            fixture_id=config.fixture_id,
            mode="refresh",
            max_provider_calls=config.max_odds_provider_calls,
            dry_run=config.dry_run,
            settings=settings,
        )
        result.odds_import["freshness_refresh"] = refresh_out.to_dict()
        refreshed_for_prediction = bool(refresh_out.refreshed) and not config.dry_run

    if config.fetch_missing_odds and not config.no_provider_calls:
        odds_out = import_daily_odds(
            date_arg=config.date_arg,
            timezone=config.timezone,
            competition_keys=keys,
            limit=config.limit,
            settings=settings,
            dry_run=config.dry_run,
            only_missing=config.only_missing,
            force=config.force_refresh,
            call_log=call_log,
            max_api_football_calls=config.max_api_football_calls,
            max_oddalerts_calls=config.max_oddalerts_calls,
            max_sportmonks_calls=config.max_sportmonks_calls,
            no_provider_calls=config.no_provider_calls,
        )
        if "freshness_refresh" in result.odds_import:
            result.odds_import["daily_import"] = odds_out.to_dict()
        else:
            result.odds_import = odds_out.to_dict()
        completeness = check_all_fixtures_completeness(
            conn,
            repo,
            discovery.fixtures,
            api_football_configured=settings.api_football_configured,
            sportmonks_configured=sm.is_configured,
            oddalerts_configured=oa.is_configured,
        )
    elif not config.no_provider_calls:
        from worldcup_predictor.owner_daily.provider_fetch import fetch_missing_data_for_fixtures

        fetch_out = fetch_missing_data_for_fixtures(
            conn,
            discovery.fixtures,
            completeness,
            settings=settings,
            call_log=call_log,
            only_missing=config.only_missing,
            force_refresh=config.force_refresh,
            dry_run=config.dry_run,
            no_provider_calls=config.no_provider_calls,
        )
        result.fetch = fetch_out.to_dict()
        completeness = check_all_fixtures_completeness(
            conn,
            repo,
            discovery.fixtures,
            api_football_configured=settings.api_football_configured,
            sportmonks_configured=sm.is_configured,
            oddalerts_configured=oa.is_configured,
        )

    pred_out = run_daily_predictions(
        discovery.fixtures,
        dry_run=config.dry_run,
        force=config.force_predictions or refreshed_for_prediction,
        strict_fresh_odds=config.strict_fresh_odds,
        settings=settings,
    )
    result.predictions = pred_out.to_dict()

    if not config.skip_result_sync:
        post_sync = run_daily_result_sync_and_evaluation(
            competition_keys=keys,
            settings=settings,
            dry_run=config.dry_run,
            force=config.force_refresh,
            fixture_ids=[f.provider_fixture_id for f in discovery.fixtures],
        )
        result.result_sync["post"] = post_sync.to_dict()

    log_path = call_log.flush()

    report = build_daily_report(
        discovery.fixtures,
        completeness,
        target_date=target.isoformat(),
        timezone_name=config.timezone,
        provider_calls=call_log.quota.to_dict(),
        settings=settings,
        include_shadow=config.include_shadow,
    )
    result.report_paths = {
        "markdown": str(report.md_path),
        "json": str(report.json_path),
        "provider_log": str(log_path),
    }

    ymd = target.isoformat().replace("-", "")
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    completeness_path = ARTIFACTS_DIR / f"daily_data_completeness_{ymd}.json"
    fetched_counts = dict(result.fetch.get("fetched", {}))
    if result.odds_import:
        if "daily_import" in result.odds_import:
            fetched_counts["odds_imported"] = result.odds_import["daily_import"].get("imported_count", 0)
        else:
            fetched_counts["odds_imported"] = result.odds_import.get("imported_count", 0)
    completeness_summary = summarize_completeness(
        completeness,
        provider_calls=call_log.quota.to_dict(),
        fetched_counts=fetched_counts,
        skipped_reasons=result.fetch.get("skipped", {}),
        result_sync_count=result.result_sync.get("post", {}).get("result_synced", 0),
        evaluation_count=(
            result.result_sync.get("post", {}).get("wde_evaluated", 0)
            + result.result_sync.get("post", {}).get("ecse_evaluated", 0)
        ),
    )
    completeness_path.write_text(json.dumps(completeness_summary, indent=2, ensure_ascii=False), encoding="utf-8")
    result.completeness_artifact = str(completeness_path)

    summary_artifact = ARTIFACTS_DIR / f"daily_owner_cycle_{ymd}.json"
    summary_artifact.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    return result
