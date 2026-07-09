"""Safe multi-provider odds freshness audit and refresh runner."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from typing import Any, Literal

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.odds.freshness_audit import _latest_odds
from worldcup_predictor.odds.freshness_policy import (
    PHASE,
    FreshnessStatus,
    classify_odds_freshness,
    explain_odds_freshness,
    is_knockout_match,
    is_low_priority_match,
    should_refresh_odds,
)
from worldcup_predictor.odds.strict_live_refresh import refresh_fixture_odds_live
from worldcup_predictor.owner_daily.fixture_discovery import discover_daily_fixtures

ARTIFACT_DIR = Path("artifacts/odds_freshness")
REPORT_JSON = ARTIFACT_DIR / "odds_freshness_refresh_report.json"
LAST_RUN_MD = Path("ODDS_FRESHNESS_1_LAST_RUN.md")


def _utc_now() -> str:
    return datetime.now(dt_timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


@dataclass
class RefreshRunResult:
    phase: str = PHASE
    mode: Literal["audit", "refresh"] = "audit"
    dry_run: bool = True
    date_arg: str = "today"
    fixtures_scanned: int = 0
    fresh_count: int = 0
    stale_count: int = 0
    missing_count: int = 0
    would_refresh: int = 0
    refreshed: int = 0
    provider_calls: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    fixtures: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "mode": self.mode,
            "dry_run": self.dry_run,
            "date_arg": self.date_arg,
            "fixtures_scanned": self.fixtures_scanned,
            "fresh_count": self.fresh_count,
            "stale_count": self.stale_count,
            "missing_count": self.missing_count,
            "would_refresh": self.would_refresh,
            "refreshed": self.refreshed,
            "provider_calls": self.provider_calls,
            "errors": self.errors,
            "fixtures_sample": self.fixtures[:50],
        }


def run_odds_freshness_refresh(
    *,
    date_arg: str = "today",
    timezone: str = "Europe/Vienna",
    competition_keys: list[str] | None = None,
    fixture_id: int | None = None,
    mode: Literal["audit", "refresh"] = "audit",
    max_provider_calls: int = 20,
    dry_run: bool = True,
    source: str = "auto",
    settings: Settings | None = None,
) -> RefreshRunResult:
    """Audit freshness and run the strict live provider fallback chain.

    In refresh mode each stale/missing fixture is tried against the configured
    provider chain. Only genuinely live, parseable odds are persisted.
    """
    del source  # preserved for backward-compatible call signatures

    settings = settings or get_settings()
    result = RefreshRunResult(mode=mode, dry_run=dry_run or mode == "audit", date_arg=date_arg)
    now = datetime.now(dt_timezone.utc)

    discovery = discover_daily_fixtures(
        date_arg=date_arg,
        timezone=timezone,
        competition_keys=competition_keys,
        limit=200 if fixture_id else 50,
        settings=settings,
        fetch_if_missing=False,
    )
    fixtures = discovery.fixtures
    if fixture_id is not None:
        fixtures = [f for f in fixtures if int(f.provider_fixture_id) == int(fixture_id)]
        if not fixtures:
            conn_lookup = connect(settings.sqlite_path)
            row = conn_lookup.execute(
                """SELECT fixture_id, home_team, away_team, kickoff_utc, status, competition_key, season
                   FROM fixtures WHERE fixture_id=? AND is_placeholder=0 LIMIT 1""",
                (int(fixture_id),),
            ).fetchone()
            conn_lookup.close()
            if row:
                from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture

                fixtures = [
                    DailyFixture(
                        fixture_id=int(row["fixture_id"]),
                        provider_fixture_id=int(row["fixture_id"]),
                        competition_key=str(row["competition_key"]),
                        home_team=str(row["home_team"]),
                        away_team=str(row["away_team"]),
                        kickoff_utc=str(row["kickoff_utc"] or ""),
                        status=str(row["status"] or "NS"),
                        season=int(row["season"]) if row["season"] is not None else None,
                        coverage_sources=["local_db"],
                    )
                ]

    conn = connect(settings.sqlite_path)
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)

    stale_ids: list[int] = []
    fixtures_by_id: dict[int, Any] = {}
    for fx in fixtures:
        fid = int(fx.provider_fixture_id)
        fixtures_by_id[fid] = fx
        fx_row = repo.get_fixture_row(fid) or {}
        round_name = fx_row.get("round_name")
        odds = _latest_odds(conn, fid)
        knockout = is_knockout_match(round_name=round_name, status=fx.status)
        low_pri = is_low_priority_match(kickoff_utc=fx.kickoff_utc, reference=now)
        cls = classify_odds_freshness(
            odds_snapshot_at=odds["snapshot_at"] if odds else None,
            reference_at=now.isoformat(),
            knockout=knockout,
            low_priority=low_pri,
            odds_source=odds.get("source") if odds else None,
            has_odds=bool(odds),
        )
        result.fixtures_scanned += 1
        if cls.status == FreshnessStatus.FRESH_ODDS:
            result.fresh_count += 1
        elif cls.status == FreshnessStatus.STALE_ODDS:
            result.stale_count += 1
        elif cls.status == FreshnessStatus.ODDS_MISSING:
            result.missing_count += 1

        needs = should_refresh_odds(cls)
        entry = {
            "fixture_id": fid,
            "match": f"{fx.home_team} vs {fx.away_team}",
            "freshness": cls.status.value,
            "odds_age_hours": cls.odds_age_hours,
            "would_refresh": needs,
            "explanation": explain_odds_freshness(cls),
        }
        result.fixtures.append(entry)
        if needs:
            result.would_refresh += 1
            stale_ids.append(fid)

    conn.close()

    if mode == "refresh" and not dry_run and stale_ids and max_provider_calls > 0:
        provider_call_budget_used = 0
        for fid in stale_ids:
            if provider_call_budget_used >= max_provider_calls:
                result.errors.append("provider call budget exhausted")
                break

            fx = fixtures_by_id.get(fid)
            if fx is None:
                result.errors.append(f"fixture {fid}: discovery row missing")
                continue

            refresh = refresh_fixture_odds_live(fx, settings=settings, dry_run=False)
            for attempt in refresh.get("attempts") or []:
                if attempt.get("call_made"):
                    provider = str(attempt.get("provider") or "unknown")
                    result.provider_calls[provider] = result.provider_calls.get(provider, 0) + 1
                    provider_call_budget_used += 1

            fixture_entry = next((e for e in result.fixtures if int(e["fixture_id"]) == fid), None)
            if fixture_entry is not None:
                fixture_entry["refresh_result"] = refresh

            if refresh.get("imported"):
                result.refreshed += 1
            else:
                result.errors.append(
                    f"fixture {fid}: {refresh.get('status', 'refresh_failed')}"
                    + (f" — {refresh.get('error')}" if refresh.get("error") else "")
                )
    elif mode == "refresh" and dry_run:
        result.dry_run = True

    return result


def write_refresh_artifacts(result: RefreshRunResult) -> dict[str, str]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    md = [
        "# ODDS-FRESHNESS-1 — Last Refresh Run",
        "",
        f"- Mode: **{result.mode}**",
        f"- Dry run: **{result.dry_run}**",
        f"- Date: **{result.date_arg}**",
        f"- Scanned: **{result.fixtures_scanned}**",
        f"- Fresh / stale / missing: {result.fresh_count} / {result.stale_count} / {result.missing_count}",
        f"- Would refresh: **{result.would_refresh}**",
        f"- Refreshed: **{result.refreshed}**",
        f"- Provider calls: `{json.dumps(result.provider_calls)}`",
        "",
    ]
    if result.errors:
        md.append("## Errors")
        md.extend(f"- {e}" for e in result.errors)
    LAST_RUN_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    return {"json": str(REPORT_JSON), "markdown": str(LAST_RUN_MD)}
