"""FIXTURE-SYNC-1 — WC fixture schedule audit, stale-NS repair, upcoming sync."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.competitions import get_competition
from worldcup_predictor.config.euro_feed_registry import EuroFeedSpec
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.data_import.european_fixture_feed import (
    _import_api_football_competition,
    _import_sportmonks_competition,
    ensure_euro_fixture_feed_tables,
)
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.database.sqlite_retry import run_with_sqlite_retry
from worldcup_predictor.integrations.fixture_api_parser import parse_api_fixture_item
from worldcup_predictor.owner_daily.provider_call_log import DailyProviderCallLog, ProviderQuotaGuard
from worldcup_predictor.quota.local_first import UNFINISHED_LOCAL_STATUSES
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly
from worldcup_predictor.results.match_results_store import MatchResultsStore, save_finished_fixtures
from worldcup_predictor.schedule.match_center import classify_status

PHASE = "FIXTURE-SYNC-1"
COMP_KEY = "world_cup_2026"
COMP_ALIASES = {"wc": COMP_KEY, "world_cup_2026": COMP_KEY, "world_cup": COMP_KEY}
UPCOMING_STATUSES = ("NS", "TBD", "TIMED", "SCHEDULED", "NOT_STARTED", "NOT STARTED")
FINISHED_STATUSES = ("FT", "AET", "PEN", "AWD", "WO", "CANC", "ABD", "PST", "POSTPONED", "CANCELLED")


def resolve_competition_key(raw: str) -> str:
    return COMP_ALIASES.get(raw.strip().lower(), raw.strip())


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _parse_date_arg(value: str, tz_name: str) -> date:
    tz = ZoneInfo(tz_name)
    today = datetime.now(tz).date()
    key = value.strip().lower()
    if key in ("today", "now"):
        return today
    return date.fromisoformat(value)


@dataclass
class WcScheduleAudit:
    phase: str = PHASE
    generated_at: str = ""
    competition_key: str = COMP_KEY
    now_utc: str = ""
    status_counts: dict[str, int] = field(default_factory=dict)
    time_counts: dict[str, int] = field(default_factory=dict)
    provider_id_counts: dict[str, int] = field(default_factory=dict)
    stale_ns_fixtures: list[dict[str, Any]] = field(default_factory=list)
    upcoming_fixtures: list[dict[str, Any]] = field(default_factory=list)
    duplicate_suspects: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "generated_at": self.generated_at,
            "competition_key": self.competition_key,
            "now_utc": self.now_utc,
            "status_counts": self.status_counts,
            "time_counts": self.time_counts,
            "provider_id_counts": self.provider_id_counts,
            "stale_ns_fixtures": self.stale_ns_fixtures,
            "upcoming_fixtures": self.upcoming_fixtures,
            "duplicate_suspects": self.duplicate_suspects,
        }


def run_wc_schedule_audit(
    *,
    db_path: str | None = None,
    competition_key: str = COMP_KEY,
    tz_name: str = "Europe/Vienna",
    upcoming_limit: int = 20,
) -> WcScheduleAudit:
    settings = get_settings()
    path = db_path or settings.sqlite_path
    conn = connect_readonly(path)
    now_iso = _utc_now_iso()
    audit = WcScheduleAudit(
        generated_at=datetime.now(timezone.utc).isoformat(),
        competition_key=competition_key,
        now_utc=now_iso,
    )

    status_rows = conn.execute(
        """
        SELECT UPPER(COALESCE(status, 'UNKNOWN')) AS status, COUNT(*) AS c
        FROM fixtures
        WHERE competition_key = ? AND is_placeholder = 0
        GROUP BY UPPER(COALESCE(status, 'UNKNOWN'))
        ORDER BY c DESC
        """,
        (competition_key,),
    ).fetchall()
    audit.status_counts = {str(r["status"]): int(r["c"]) for r in status_rows}

    unfinished = sorted(UNFINISHED_LOCAL_STATUSES)
    placeholders = ",".join("?" for _ in unfinished)
    time_row = conn.execute(
        f"""
        SELECT
          SUM(CASE WHEN kickoff_utc < ? AND UPPER(status) IN ({placeholders}) THEN 1 ELSE 0 END) AS past_ns,
          SUM(CASE WHEN kickoff_utc >= ? AND UPPER(status) IN ({placeholders}) THEN 1 ELSE 0 END) AS future_ns,
          SUM(CASE WHEN kickoff_utc >= ? THEN 1 ELSE 0 END) AS future_any,
          SUM(CASE WHEN UPPER(status) IN ('FT','AET','PEN') AND fixture_id NOT IN (
              SELECT fixture_id FROM fixture_results WHERE competition_key = ?
          ) THEN 1 ELSE 0 END) AS finished_missing_result,
          SUM(CASE WHEN fixture_id > 0 THEN 1 ELSE 0 END) AS with_provider_fixture_id,
          SUM(CASE WHEN fixture_id IS NULL OR fixture_id <= 0 THEN 1 ELSE 0 END) AS missing_provider_fixture_id
        FROM fixtures
        WHERE competition_key = ? AND is_placeholder = 0
        """,
        (now_iso, *unfinished, now_iso, *unfinished, now_iso, competition_key, competition_key),
    ).fetchone()
    audit.time_counts = {
        "past_kickoff_ns": int(time_row["past_ns"] or 0),
        "future_kickoff_ns": int(time_row["future_ns"] or 0),
        "future_kickoff_any_status": int(time_row["future_any"] or 0),
        "finished_missing_result": int(time_row["finished_missing_result"] or 0),
        "with_provider_fixture_id": int(time_row["with_provider_fixture_id"] or 0),
        "missing_provider_fixture_id": int(time_row["missing_provider_fixture_id"] or 0),
    }

    feed_count = conn.execute(
        "SELECT COUNT(*) AS c FROM euro_fixture_feed WHERE competition_key = ?",
        (competition_key,),
    ).fetchone()
    audit.provider_id_counts = {
        "euro_fixture_feed_rows": int(feed_count["c"] or 0),
        "fixtures_fixture_id_as_provider_id": audit.time_counts["with_provider_fixture_id"],
    }

    stale_rows = conn.execute(
        f"""
        SELECT f.fixture_id, f.kickoff_utc, f.round_name, f.home_team, f.away_team,
               f.status, f.source,
               r.final_score, r.home_goals, r.away_goals, r.match_outcome_type,
               ef.provider, ef.provider_fixture_id
        FROM fixtures f
        LEFT JOIN fixture_results r ON r.fixture_id = f.fixture_id
        LEFT JOIN euro_fixture_feed ef ON ef.fixture_id = f.fixture_id
        WHERE f.competition_key = ? AND f.is_placeholder = 0
          AND f.kickoff_utc < ?
          AND UPPER(f.status) IN ({placeholders})
        ORDER BY f.kickoff_utc ASC
        """,
        (competition_key, now_iso, *unfinished),
    ).fetchall()
    for row in stale_rows:
        r = dict(row)
        audit.stale_ns_fixtures.append(
            {
                "fixture_id": r["fixture_id"],
                "kickoff_utc": r["kickoff_utc"],
                "stage_round": r.get("round_name"),
                "home_team": r.get("home_team"),
                "away_team": r.get("away_team"),
                "status": r.get("status"),
                "source": r.get("source"),
                "provider": r.get("provider"),
                "provider_fixture_id": r.get("provider_fixture_id") or r["fixture_id"],
                "final_score": r.get("final_score"),
                "home_goals": r.get("home_goals"),
                "away_goals": r.get("away_goals"),
                "match_outcome_type": r.get("match_outcome_type"),
            }
        )

    upcoming_rows = conn.execute(
        """
        SELECT fixture_id, kickoff_utc, round_name, home_team, away_team, status
        FROM fixtures
        WHERE competition_key = ? AND is_placeholder = 0
          AND kickoff_utc >= ?
        ORDER BY kickoff_utc ASC
        LIMIT ?
        """,
        (competition_key, now_iso, upcoming_limit),
    ).fetchall()
    audit.upcoming_fixtures = [dict(r) for r in upcoming_rows]

    dup_rows = conn.execute(
        """
        SELECT LOWER(home_team) AS home, LOWER(away_team) AS away,
               substr(kickoff_utc, 1, 16) AS kickoff_min,
               COUNT(*) AS c,
               GROUP_CONCAT(fixture_id) AS fixture_ids
        FROM fixtures
        WHERE competition_key = ? AND is_placeholder = 0
        GROUP BY LOWER(home_team), LOWER(away_team), substr(kickoff_utc, 1, 16)
        HAVING COUNT(*) > 1
        ORDER BY c DESC
        LIMIT 20
        """,
        (competition_key,),
    ).fetchall()
    audit.duplicate_suspects = [dict(r) for r in dup_rows]

    conn.close()
    return audit


def render_audit_markdown(audit: WcScheduleAudit) -> str:
    lines = [
        "# FIXTURE-SYNC-1 — WC Fixture Schedule Audit",
        "",
        f"- **Generated:** {audit.generated_at}",
        f"- **Competition:** {audit.competition_key}",
        f"- **Now (UTC):** {audit.now_utc}",
        "",
        "## Status counts",
        "",
        "| status | count |",
        "|--------|------:|",
    ]
    for status, count in sorted(audit.status_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {status} | {count} |")

    lines.extend(["", "## Time / provider counts", ""])
    for key, val in audit.time_counts.items():
        lines.append(f"- **{key}:** {val}")
    for key, val in audit.provider_id_counts.items():
        lines.append(f"- **{key}:** {val}")

    lines.extend(
        [
            "",
            "## Stale NS fixtures (past kickoff, unfinished status)",
            "",
            "| fixture_id | kickoff_utc | round | match | status | score | provider_id |",
            "|-----------:|-------------|-------|-------|--------|-------|------------:|",
        ]
    )
    for f in audit.stale_ns_fixtures:
        match = f"{f['home_team']} vs {f['away_team']}"
        score = f.get("final_score") or "—"
        lines.append(
            f"| {f['fixture_id']} | {f['kickoff_utc']} | {f.get('stage_round') or '—'} | "
            f"{match} | {f['status']} | {score} | {f.get('provider_fixture_id')} |"
        )

    lines.extend(["", "## Upcoming fixtures", ""])
    if not audit.upcoming_fixtures:
        lines.append("_None with kickoff_utc >= now._")
    else:
        lines.extend(
            [
                "| fixture_id | kickoff_utc | round | match | status |",
                "|-----------:|-------------|-------|-------|--------|",
            ]
        )
        for f in audit.upcoming_fixtures:
            lines.append(
                f"| {f['fixture_id']} | {f['kickoff_utc']} | {f.get('round_name') or '—'} | "
                f"{f['home_team']} vs {f['away_team']} | {f['status']} |"
            )

    if audit.duplicate_suspects:
        lines.extend(["", "## Duplicate suspects", ""])
        for d in audit.duplicate_suspects:
            lines.append(f"- {d['home']} vs {d['away']} @ {d['kickoff_min']}: {d['fixture_ids']} ({d['c']})")

    return "\n".join(lines) + "\n"


@dataclass
class StaleNsRepairResult:
    scanned: int = 0
    updated: int = 0
    skipped: int = 0
    provider_calls: int = 0
    dry_run: bool = True
    errors: list[str] = field(default_factory=list)
    details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "updated": self.updated,
            "skipped": self.skipped,
            "provider_calls": self.provider_calls,
            "dry_run": self.dry_run,
            "errors": self.errors,
            "details": self.details,
        }


def repair_stale_ns_wc_fixtures(
    *,
    settings: Settings | None = None,
    competition_key: str = COMP_KEY,
    max_provider_calls: int = 20,
    dry_run: bool = True,
    fixture_ids: list[int] | None = None,
) -> StaleNsRepairResult:
    """Provider-backed repair for past-kickoff fixtures still marked NS locally."""
    settings = settings or get_settings()
    result = StaleNsRepairResult(dry_run=dry_run)
    api = ApiFootballClient(settings)
    if not api.is_configured:
        result.errors.append("API_FOOTBALL_KEY not configured")
        return result

    audit = run_wc_schedule_audit(db_path=settings.sqlite_path, competition_key=competition_key)
    targets = audit.stale_ns_fixtures
    if fixture_ids:
        wanted = {int(x) for x in fixture_ids}
        targets = [t for t in targets if int(t["fixture_id"]) in wanted]

    result.scanned = len(targets)
    finished_for_jsonl: list[Any] = []

    def _run() -> None:
        nonlocal finished_for_jsonl
        repo = FootballIntelligenceRepository(settings.sqlite_path or None)
        try:
            for entry in targets:
                if result.provider_calls >= max_provider_calls:
                    result.errors.append("max_provider_calls reached")
                    break
                fid = int(entry["fixture_id"])
                detail: dict[str, Any] = {"fixture_id": fid, "before_status": entry.get("status")}
                try:
                    fetch = api.get_fixture_by_id(fid)
                    result.provider_calls += 1
                    if not fetch.ok or not fetch.data:
                        result.skipped += 1
                        detail["status"] = "no_provider_data"
                        detail["error"] = fetch.error
                        result.details.append(detail)
                        continue

                    item = fetch.data[0] if isinstance(fetch.data, list) else fetch.data
                    fixture = parse_api_fixture_item(item, source=str(fetch.source or "api-football"))
                    if fixture is None:
                        result.skipped += 1
                        detail["status"] = "parse_failed"
                        result.details.append(detail)
                        continue

                    detail["provider_status"] = fixture.status
                    detail["would_score"] = (
                        f"{fixture.home_goals}-{fixture.away_goals}"
                        if fixture.home_goals is not None and fixture.away_goals is not None
                        else None
                    )

                    if dry_run:
                        if classify_status(fixture.status) == "finished":
                            detail["status"] = "dry_run_would_update"
                        else:
                            detail["status"] = "dry_run_still_unfinished"
                        result.details.append(detail)
                        continue

                    repo.upsert_fixture(fixture, competition_key=competition_key)
                    if classify_status(fixture.status) == "finished":
                        if repo.upsert_fixture_result(fixture, competition_key=competition_key):
                            result.updated += 1
                            finished_for_jsonl.append(fixture)
                            detail["status"] = "updated_to_finished"
                        else:
                            result.skipped += 1
                            detail["status"] = "result_upsert_failed"
                    else:
                        result.skipped += 1
                        detail["status"] = "provider_still_unfinished"
                    result.details.append(detail)
                except Exception as exc:
                    result.errors.append(f"{fid}: {exc}")
                    detail["status"] = "error"
                    detail["reason"] = str(exc)
                    result.details.append(detail)

            if finished_for_jsonl and not dry_run:
                save_finished_fixtures(finished_for_jsonl, MatchResultsStore())
            if not dry_run:
                repo._conn.commit()
        finally:
            repo.close()

    run_with_sqlite_retry(_run)
    return result


@dataclass
class UpcomingSyncResult:
    dry_run: bool = True
    from_date: str = ""
    to_date: str = ""
    source: str = "auto"
    provider_calls: dict[str, int] = field(default_factory=dict)
    imported: int = 0
    updated: int = 0
    duplicates_avoided: int = 0
    parse_skipped: int = 0
    future_fixtures_before: int = 0
    future_fixtures_after: int = 0
    errors: list[str] = field(default_factory=list)
    by_provider: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "from_date": self.from_date,
            "to_date": self.to_date,
            "source": self.source,
            "provider_calls": self.provider_calls,
            "imported": self.imported,
            "updated": self.updated,
            "duplicates_avoided": self.duplicates_avoided,
            "parse_skipped": self.parse_skipped,
            "future_fixtures_before": self.future_fixtures_before,
            "future_fixtures_after": self.future_fixtures_after,
            "errors": self.errors,
            "by_provider": self.by_provider,
        }


def sync_wc_upcoming_fixtures(
    *,
    from_date: date,
    to_date: date | None = None,
    source: Literal["auto", "api_football", "sportmonks"] = "auto",
    competition_key: str = COMP_KEY,
    max_provider_calls: int = 20,
    dry_run: bool = True,
    settings: Settings | None = None,
) -> UpcomingSyncResult:
    settings = settings or get_settings()
    end = to_date or (from_date + timedelta(days=90))
    result = UpcomingSyncResult(
        dry_run=dry_run,
        from_date=from_date.isoformat(),
        to_date=end.isoformat(),
        source=source,
    )

    before_audit = run_wc_schedule_audit(db_path=settings.sqlite_path, competition_key=competition_key)
    result.future_fixtures_before = before_audit.time_counts.get("future_kickoff_any_status", 0)

    comp = get_competition(competition_key)
    spec = EuroFeedSpec(
        competition_key=competition_key,
        provider="api-football",
        provider_league_id=comp.league_id,
        provider_season_id=comp.season,
        timezone_policy="utc_storage",
        supports_fixtures=True,
        supports_results=True,
        supports_odds=True,
        supports_ecse=True,
        supports_wde=True,
    )

    use_api = source in ("auto", "api_football")
    use_sm = source in ("auto", "sportmonks")

    def _run() -> None:
        repo = FootballIntelligenceRepository(settings.sqlite_path or None)
        conn = repo._conn
        ensure_euro_fixture_feed_tables(conn)
        try:
            if use_api:
                api = ApiFootballClient(settings)
                if not api.is_configured:
                    result.errors.append("API_FOOTBALL_KEY not configured")
                elif max_provider_calls < 1:
                    result.errors.append("max_provider_calls too low for api-football")
                else:
                    stats = _import_api_football_competition(
                        spec=spec,
                        season=comp.season,
                        from_date=from_date,
                        to_date=end,
                        conn=conn,
                        repo=repo,
                        api=api,
                        dry_run=dry_run,
                    )
                    result.provider_calls["api_football"] = 1
                    result.imported += stats.upcoming_imported
                    result.duplicates_avoided += stats.duplicates_avoided
                    result.parse_skipped += stats.parse_skipped
                    result.updated += stats.fixtures_synced
                    result.by_provider.append(stats.to_dict())
                    result.errors.extend(stats.errors)

            if use_sm and result.provider_calls.get("sportmonks", 0) + result.provider_calls.get("api_football", 0) < max_provider_calls:
                from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider

                sm = SportmonksProvider(settings)
                days = (end - from_date).days + 1
                sm_days = min(days, max(0, max_provider_calls - sum(result.provider_calls.values())))
                if sm_days > 0:
                    sm_end = from_date + timedelta(days=sm_days - 1)
                    sm_stats = _import_sportmonks_competition(
                        spec=spec,
                        season=comp.season,
                        from_date=from_date,
                        to_date=sm_end,
                        conn=conn,
                        provider=sm,
                        dry_run=dry_run,
                    )
                    result.provider_calls["sportmonks"] = sm_days
                    result.imported += sm_stats.upcoming_imported
                    result.duplicates_avoided += sm_stats.duplicates_avoided
                    result.parse_skipped += sm_stats.parse_skipped
                    result.by_provider.append(sm_stats.to_dict())
                    result.errors.extend(sm_stats.errors)

            if not dry_run:
                conn.commit()
        finally:
            repo.close()

    run_with_sqlite_retry(_run)

    after_audit = run_wc_schedule_audit(db_path=settings.sqlite_path, competition_key=competition_key)
    result.future_fixtures_after = after_audit.time_counts.get("future_kickoff_any_status", 0)
    return result
