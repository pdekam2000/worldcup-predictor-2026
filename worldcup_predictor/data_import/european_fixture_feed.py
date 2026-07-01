"""PHASE EURO-A — Upcoming European fixture feed import (fixtures only, no WDE/ECSE)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.competitions import get_competition, normalize_competition_key
from worldcup_predictor.config.euro_feed_registry import (
    EURO_A_TARGET_KEYS,
    EuroFeedSpec,
    get_euro_feed_spec,
    resolve_provider_season,
)
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import get_db_path
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.integrations.fixture_api_parser import FINISHED_STATUSES, parse_api_fixture_item
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider

PHASE = "EURO-A"

FINISHED_SPORTMONKS_STATE_IDS = frozenset({5, 7, 8})
UPCOMING_API_STATUSES = frozenset({"NS", "TBD", "SCHEDULED", "TIMED", "1H", "HT", "2H", "LIVE", "PST"})

EURO_FIXTURE_FEED_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS euro_fixture_feed (
        fixture_id INTEGER NOT NULL,
        provider TEXT NOT NULL,
        provider_fixture_id INTEGER NOT NULL,
        competition_key TEXT NOT NULL,
        home_team TEXT NOT NULL,
        away_team TEXT NOT NULL,
        kickoff_utc TEXT NOT NULL,
        status TEXT NOT NULL,
        season INTEGER,
        raw_payload_ref TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (provider, provider_fixture_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_euro_fixture_feed_comp_kickoff
    ON euro_fixture_feed(competition_key, kickoff_utc)
    """,
    """
    CREATE TABLE IF NOT EXISTS euro_fixture_raw_payload (
        ref TEXT PRIMARY KEY,
        provider TEXT NOT NULL,
        entity_key TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def ensure_euro_fixture_feed_tables(conn: sqlite3.Connection) -> None:
    for ddl in EURO_FIXTURE_FEED_DDL:
        conn.execute(ddl)
    conn.commit()


def _raw_ref(provider: str, entity_key: str) -> str:
    return f"{provider}:{entity_key}"


@dataclass
class CompetitionImportStats:
    competition_key: str
    provider: str
    season: int
    fetched: int = 0
    upcoming_imported: int = 0
    duplicates_avoided: int = 0
    parse_skipped: int = 0
    fixtures_synced: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "competition_key": self.competition_key,
            "provider": self.provider,
            "season": self.season,
            "fetched": self.fetched,
            "upcoming_imported": self.upcoming_imported,
            "duplicates_avoided": self.duplicates_avoided,
            "parse_skipped": self.parse_skipped,
            "fixtures_synced": self.fixtures_synced,
            "errors": self.errors,
        }


@dataclass
class EuropeanFixtureImportReport:
    phase: str = PHASE
    dry_run: bool = False
    days_ahead: int = 30
    from_date: str = ""
    to_date: str = ""
    fixtures_before: dict[str, int] = field(default_factory=dict)
    fixtures_after: dict[str, int] = field(default_factory=dict)
    upcoming_imported: int = 0
    duplicates_avoided: int = 0
    skipped_competitions: list[dict[str, str]] = field(default_factory=list)
    provider_errors: list[str] = field(default_factory=list)
    by_competition: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "dry_run": self.dry_run,
            "days_ahead": self.days_ahead,
            "from_date": self.from_date,
            "to_date": self.to_date,
            "fixtures_before": self.fixtures_before,
            "fixtures_after": self.fixtures_after,
            "upcoming_imported": self.upcoming_imported,
            "duplicates_avoided": self.duplicates_avoided,
            "skipped_competitions": self.skipped_competitions,
            "provider_errors": self.provider_errors,
            "by_competition": self.by_competition,
        }


def _parse_kickoff(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = str(value).replace("Z", "+00:00")
    try:
        if "T" in raw:
            return datetime.fromisoformat(raw).astimezone(timezone.utc).replace(tzinfo=None)
        return datetime.strptime(raw[:10], "%Y-%m-%d").replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def _in_upcoming_window(kickoff: datetime, *, start: date, end: date) -> bool:
    day = kickoff.date()
    return start <= day <= end


def _sportmonks_participants(item: dict[str, Any]) -> tuple[str, str]:
    home = away = ""
    for participant in item.get("participants") or []:
        if not isinstance(participant, dict):
            continue
        loc = str((participant.get("meta") or {}).get("location") or "").lower()
        name = str(participant.get("name") or "")
        if loc == "home":
            home = name
        elif loc == "away":
            away = name
    if not home or not away:
        name_blob = str(item.get("name") or "")
        if " vs " in name_blob.lower():
            parts = name_blob.split(" vs ", 1)
            home, away = parts[0].strip(), parts[1].strip()
    return home or "TBD", away or "TBD"


def _sportmonks_status(item: dict[str, Any]) -> str:
    state = item.get("state") or {}
    if isinstance(state, dict):
        short = state.get("short_name") or state.get("state") or state.get("name")
        if short:
            return str(short).upper()
    try:
        state_id = int(item.get("state_id") or 0)
    except (TypeError, ValueError):
        state_id = 0
    if state_id in FINISHED_SPORTMONKS_STATE_IDS:
        return "FT"
    return "NS"


def _count_feed_rows(conn: sqlite3.Connection, competition_keys: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key in competition_keys:
        row = conn.execute(
            "SELECT COUNT(1) AS c FROM euro_fixture_feed WHERE competition_key = ?",
            (key,),
        ).fetchone()
        counts[key] = int(row["c"]) if row else 0
    return counts


def _feed_row_exists(
    conn: sqlite3.Connection,
    *,
    provider: str,
    provider_fixture_id: int,
    kickoff_utc: str,
    status: str,
) -> bool:
    row = conn.execute(
        """
        SELECT kickoff_utc, status FROM euro_fixture_feed
        WHERE provider = ? AND provider_fixture_id = ?
        """,
        (provider, provider_fixture_id),
    ).fetchone()
    if row is None:
        return False
    return str(row["kickoff_utc"]) == kickoff_utc and str(row["status"]) == status


def _store_raw_payload(
    conn: sqlite3.Connection,
    *,
    provider: str,
    entity_key: str,
    payload: dict[str, Any],
    dry_run: bool,
) -> str:
    ref = _raw_ref(provider, entity_key)
    if dry_run:
        return ref
    conn.execute(
        """
        INSERT INTO euro_fixture_raw_payload (ref, provider, entity_key, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(ref) DO UPDATE SET
            payload_json = excluded.payload_json,
            created_at = excluded.created_at
        """,
        (ref, provider, entity_key, json.dumps(payload, ensure_ascii=False, default=str), _utc_now()),
    )
    return ref


def _upsert_feed_row(
    conn: sqlite3.Connection,
    *,
    fixture_id: int,
    provider: str,
    provider_fixture_id: int,
    competition_key: str,
    home_team: str,
    away_team: str,
    kickoff_utc: str,
    status: str,
    season: int | None,
    raw_payload_ref: str,
    dry_run: bool,
) -> Literal["inserted", "updated", "duplicate"]:
    if _feed_row_exists(
        conn,
        provider=provider,
        provider_fixture_id=provider_fixture_id,
        kickoff_utc=kickoff_utc,
        status=status,
    ):
        return "duplicate"

    if dry_run:
        return "inserted"

    conn.execute(
        """
        INSERT INTO euro_fixture_feed (
            fixture_id, provider, provider_fixture_id, competition_key,
            home_team, away_team, kickoff_utc, status, season,
            raw_payload_ref, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(provider, provider_fixture_id) DO UPDATE SET
            fixture_id = excluded.fixture_id,
            competition_key = excluded.competition_key,
            home_team = excluded.home_team,
            away_team = excluded.away_team,
            kickoff_utc = excluded.kickoff_utc,
            status = excluded.status,
            season = excluded.season,
            raw_payload_ref = excluded.raw_payload_ref,
            updated_at = excluded.updated_at
        """,
        (
            fixture_id,
            provider,
            provider_fixture_id,
            competition_key,
            home_team,
            away_team,
            kickoff_utc,
            status,
            season,
            raw_payload_ref,
            _utc_now(),
        ),
    )
    if conn.total_changes == 0:
        return "duplicate"
    return "inserted"


def _import_api_football_competition(
    *,
    spec: EuroFeedSpec,
    season: int,
    from_date: date,
    to_date: date,
    conn: sqlite3.Connection,
    repo: FootballIntelligenceRepository,
    api: ApiFootballClient,
    dry_run: bool,
) -> CompetitionImportStats:
    stats = CompetitionImportStats(
        competition_key=spec.competition_key,
        provider="api-football",
        season=season,
    )
    if not spec.supports_fixtures or spec.provider_league_id <= 0:
        stats.errors.append("competition not configured for fixtures in registry")
        return stats

    if not api.is_configured:
        stats.errors.append("API_FOOTBALL_KEY not configured")
        return stats

    result = api.get_historical_fixtures(
        league_id=spec.provider_league_id,
        season=season,
        from_date=from_date.isoformat(),
        to_date=to_date.isoformat(),
    )
    if not result.ok or not isinstance(result.data, list):
        stats.errors.append(result.error or "API-Football fixtures request failed")
        return stats

    stats.fetched = len(result.data)
    comp = get_competition(spec.competition_key)
    if not dry_run:
        repo.upsert_competition(comp)

    for item in result.data:
        fixture_block = item.get("fixture") or {}
        status = str((fixture_block.get("status") or {}).get("short") or "").upper()
        if status in FINISHED_STATUSES:
            stats.parse_skipped += 1
            continue
        if status and status not in UPCOMING_API_STATUSES:
            stats.parse_skipped += 1
            continue

        parsed = parse_api_fixture_item(item, source="live")
        if parsed is None or parsed.kickoff_time is None:
            stats.parse_skipped += 1
            continue
        if not _in_upcoming_window(parsed.kickoff_time, start=from_date, end=to_date):
            stats.parse_skipped += 1
            continue

        entity_key = f"fixtures:{parsed.fixture_id}"
        raw_ref = _store_raw_payload(
            conn,
            provider="api-football",
            entity_key=entity_key,
            payload=item,
            dry_run=dry_run,
        )
        outcome = _upsert_feed_row(
            conn,
            fixture_id=parsed.fixture_id,
            provider="api-football",
            provider_fixture_id=parsed.fixture_id,
            competition_key=spec.competition_key,
            home_team=parsed.home_team,
            away_team=parsed.away_team,
            kickoff_utc=parsed.kickoff_time.isoformat(),
            status=parsed.status,
            season=season,
            raw_payload_ref=raw_ref,
            dry_run=dry_run,
        )
        if outcome == "duplicate":
            stats.duplicates_avoided += 1
            continue
        stats.upcoming_imported += 1

        if not dry_run:
            saved = repo.upsert_fixture(
                parsed,
                competition_key=spec.competition_key,
                league_id=spec.provider_league_id,
                season=season,
            )
            if saved:
                stats.fixtures_synced += 1

    if not dry_run:
        conn.commit()
    return stats


def _import_sportmonks_competition(
    *,
    spec: EuroFeedSpec,
    season: int,
    from_date: date,
    to_date: date,
    conn: sqlite3.Connection,
    provider: SportmonksProvider,
    dry_run: bool,
) -> CompetitionImportStats:
    stats = CompetitionImportStats(
        competition_key=spec.competition_key,
        provider="sportmonks",
        season=season,
    )
    sm_league_id = spec.sportmonks_league_id
    if sm_league_id is None or sm_league_id <= 0:
        stats.errors.append("sportmonks_league_id not configured in registry")
        return stats
    if not provider.is_configured:
        stats.errors.append("SPORTMONKS_API_TOKEN not configured")
        return stats

    seen: set[int] = set()
    day = from_date
    while day <= to_date:
        endpoint = f"/fixtures/date/{day.isoformat()}"
        status_code, payload, error = provider.safe_get(
            endpoint,
            params={
                "include": "participants;state",
                "filters": f"fixtureLeagues:{sm_league_id}",
                "per_page": 50,
            },
        )
        if error:
            if status_code in (401, 403):
                stats.errors.append(f"subscription denied for league {sm_league_id}: {error}")
                break
            stats.errors.append(f"{day.isoformat()}: {error}")
            day += timedelta(days=1)
            continue

        data = payload.get("data") if isinstance(payload, dict) else None
        rows = [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []
        stats.fetched += len(rows)

        for item in rows:
            try:
                sm_id = int(item.get("id") or 0)
            except (TypeError, ValueError):
                stats.parse_skipped += 1
                continue
            if sm_id <= 0 or sm_id in seen:
                continue
            seen.add(sm_id)

            try:
                state_id = int(item.get("state_id") or 0)
            except (TypeError, ValueError):
                state_id = 0
            if state_id in FINISHED_SPORTMONKS_STATE_IDS:
                stats.parse_skipped += 1
                continue

            kickoff = _parse_kickoff(item.get("starting_at"))
            if kickoff is None or not _in_upcoming_window(kickoff, start=from_date, end=to_date):
                stats.parse_skipped += 1
                continue

            home_team, away_team = _sportmonks_participants(item)
            status = _sportmonks_status(item)
            entity_key = f"fixtures:{sm_id}"
            raw_ref = _store_raw_payload(
                conn,
                provider="sportmonks",
                entity_key=entity_key,
                payload=item,
                dry_run=dry_run,
            )
            outcome = _upsert_feed_row(
                conn,
                fixture_id=sm_id,
                provider="sportmonks",
                provider_fixture_id=sm_id,
                competition_key=spec.competition_key,
                home_team=home_team,
                away_team=away_team,
                kickoff_utc=kickoff.isoformat(),
                status=status,
                season=season,
                raw_payload_ref=raw_ref,
                dry_run=dry_run,
            )
            if outcome == "duplicate":
                stats.duplicates_avoided += 1
                continue
            stats.upcoming_imported += 1

        day += timedelta(days=1)

    if not dry_run:
        conn.commit()
    return stats


def import_european_fixtures(
    *,
    competition_keys: list[str] | None = None,
    days_ahead: int = 30,
    dry_run: bool = False,
    settings: Settings | None = None,
    include_sportmonks: bool = True,
    repository: FootballIntelligenceRepository | None = None,
) -> EuropeanFixtureImportReport:
    settings = settings or get_settings()
    requested = competition_keys or list(EURO_A_TARGET_KEYS)
    normalized = [normalize_competition_key(k) for k in requested]

    today = datetime.now(timezone.utc).date()
    from_date = today
    to_date = today + timedelta(days=max(1, days_ahead))

    report = EuropeanFixtureImportReport(
        dry_run=dry_run,
        days_ahead=days_ahead,
        from_date=from_date.isoformat(),
        to_date=to_date.isoformat(),
    )

    db_path = get_db_path(settings.sqlite_path)
    own_repo = repository is None
    repo = repository or FootballIntelligenceRepository(path=str(db_path))
    conn = repo._conn
    ensure_euro_fixture_feed_tables(conn)
    api = ApiFootballClient(settings)
    sm_provider = SportmonksProvider(settings)

    valid_keys = [k for k in normalized if k in EURO_A_TARGET_KEYS]
    report.fixtures_before = _count_feed_rows(conn, valid_keys)

    for key in normalized:
        if key not in EURO_A_TARGET_KEYS:
            report.skipped_competitions.append(
                {"competition_key": key, "reason": "not in EURO-A target registry"}
            )
            continue

        comp = get_competition(key)
        if not comp.enabled:
            report.skipped_competitions.append(
                {"competition_key": key, "reason": "competition disabled in registry"}
            )
            continue

        spec = get_euro_feed_spec(key)
        if not spec.supports_fixtures:
            report.skipped_competitions.append(
                {"competition_key": key, "reason": "fixtures not supported for registry entry"}
            )
            continue

        season = resolve_provider_season(key, settings=settings)

        af_stats = _import_api_football_competition(
            spec=spec,
            season=season,
            from_date=from_date,
            to_date=to_date,
            conn=conn,
            repo=repo,
            api=api,
            dry_run=dry_run,
        )
        report.by_competition.append(af_stats.to_dict())
        report.upcoming_imported += af_stats.upcoming_imported
        report.duplicates_avoided += af_stats.duplicates_avoided
        report.provider_errors.extend(
            f"api-football/{key}: {err}" for err in af_stats.errors
        )

        if include_sportmonks:
            sm_stats = _import_sportmonks_competition(
                spec=spec,
                season=season,
                from_date=from_date,
                to_date=to_date,
                conn=conn,
                provider=sm_provider,
                dry_run=dry_run,
            )
            report.by_competition.append(sm_stats.to_dict())
            report.upcoming_imported += sm_stats.upcoming_imported
            report.duplicates_avoided += sm_stats.duplicates_avoided
            report.provider_errors.extend(
                f"sportmonks/{key}: {err}" for err in sm_stats.errors
            )

    report.fixtures_after = _count_feed_rows(conn, valid_keys)
    if own_repo:
        repo.close()
    return report


def verify_domestic_results(
    competition_key: str,
    *,
    settings: Settings | None = None,
    sample_size: int = 20,
) -> dict:
    """Verify PL/Bundesliga historical fixture_results consistency (read-only sample)."""
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    rows = repo._conn.execute(
        """
        SELECT f.fixture_id, f.competition_key, f.status,
               r.final_score, r.home_goals, r.away_goals
        FROM fixtures f
        INNER JOIN fixture_results r ON r.fixture_id = f.fixture_id
        WHERE f.competition_key = ?
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (competition_key, int(sample_size)),
    ).fetchall()

    issues: list[dict] = []
    ok = 0
    for row in rows:
        key = str(row["competition_key"])
        if key != competition_key:
            issues.append({"fixture_id": row["fixture_id"], "issue": "wrong_competition_key", "value": key})
            continue
        if not row["final_score"]:
            issues.append({"fixture_id": row["fixture_id"], "issue": "missing_final_score"})
            continue
        if row["home_goals"] is None or row["away_goals"] is None:
            issues.append({"fixture_id": row["fixture_id"], "issue": "missing_goal_columns"})
            continue
        ok += 1

    total_results = repo._conn.execute(
        "SELECT COUNT(*) AS c FROM fixture_results WHERE competition_key = ?",
        (competition_key,),
    ).fetchone()["c"]

    return {
        "competition_key": competition_key,
        "sample_size": len(rows),
        "sample_ok": ok,
        "sample_issues": issues,
        "total_fixture_results": int(total_results),
        "passed": len(issues) == 0 and ok == len(rows),
    }
