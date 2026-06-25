"""OddAlerts historical odds ingest — research/backfill only (not production predictions)."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect, init_database
from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient

logger = logging.getLogger(__name__)

PROVIDER_NAME = "oddalerts"
CACHE_TTL_DAYS = 30

ODDALERTS_LEAGUE_MAP: dict[str, dict[str, Any]] = {
    "premier_league": {"competition_id": 423, "competition_name": "Premier League", "country": "England"},
    "champions_league": {"competition_id": 51, "competition_name": "Champions League", "country": "Europe"},
    "europa_league": {"competition_id": 32, "competition_name": "Europa League", "country": "Europe"},
    "bundesliga": {"competition_id": 477, "competition_name": "Bundesliga", "country": "Germany"},
    "la_liga": {"competition_id": 419, "competition_name": "La Liga", "country": "Spain"},
    "serie_a": {"competition_id": 499, "competition_name": "Serie A", "country": "Italy"},
    "world_cup": {"competition_id": 1690, "competition_name": "World Cup", "country": "International"},
}

_FINISHED = ("FT", "AET", "PEN", "FINISHED", "AWD", "WO")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm_name(value: str | None) -> str:
    text = (value or "").lower().strip()
    text = re.sub(r"\b(fc|cf|sc|afc|bsc|sv|vfb|tsg)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def season_aliases(calendar_season: int) -> set[str]:
    y = int(calendar_season)
    y1 = y + 1
    return {
        str(y),
        str(y1),
        f"{y}/{y1}",
        f"{y}-{y1}",
        f"{y}/{str(y1)[2:]}",
        f"{y - 1}/{y}",
        f"{y - 1}/{str(y)[2:]}",
    }


def _parse_decimal(value: Any) -> float | None:
    if value is None:
        return None
    try:
        num = float(value)
        return num if num > 1.0 else None
    except (TypeError, ValueError):
        return None


def _implied_prob(decimal_odds: float | None) -> float | None:
    if decimal_odds is None or decimal_odds <= 1.0:
        return None
    return round(1.0 / decimal_odds, 6)


PHASE_OA2_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS oddalerts_fixture_map (
        oddalerts_fixture_id INTEGER PRIMARY KEY,
        internal_fixture_id INTEGER,
        provider TEXT NOT NULL DEFAULT 'oddalerts',
        league TEXT NOT NULL,
        season INTEGER NOT NULL,
        home_team TEXT NOT NULL,
        away_team TEXT NOT NULL,
        kickoff TEXT,
        mapping_confidence TEXT NOT NULL DEFAULT 'unmatched',
        probability_json TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_oddalerts_fixture_map_internal
    ON oddalerts_fixture_map(internal_fixture_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_oddalerts_fixture_map_league_season
    ON oddalerts_fixture_map(league, season)
    """,
    """
    CREATE TABLE IF NOT EXISTS oddalerts_odds_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        oddalerts_fixture_id INTEGER NOT NULL,
        internal_fixture_id INTEGER,
        league TEXT NOT NULL,
        season INTEGER NOT NULL,
        bookmaker TEXT NOT NULL,
        market TEXT NOT NULL,
        selection TEXT NOT NULL,
        opening_odds REAL,
        closing_odds REAL,
        peak_odds REAL,
        odds_timestamp TEXT,
        implied_probability REAL,
        raw_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(oddalerts_fixture_id, bookmaker, market, selection),
        FOREIGN KEY (oddalerts_fixture_id) REFERENCES oddalerts_fixture_map(oddalerts_fixture_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_oddalerts_odds_history_fixture
    ON oddalerts_odds_history(oddalerts_fixture_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_oddalerts_odds_history_league_season
    ON oddalerts_odds_history(league, season)
    """,
    """
    CREATE TABLE IF NOT EXISTS oddalerts_ingest_state (
        league TEXT NOT NULL,
        season INTEGER NOT NULL,
        oddalerts_fixture_id INTEGER NOT NULL,
        stage TEXT NOT NULL DEFAULT 'discovered',
        odds_rows INTEGER NOT NULL DEFAULT 0,
        last_error TEXT,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (league, season, oddalerts_fixture_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS oddalerts_ingest_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        league TEXT NOT NULL,
        season INTEGER NOT NULL,
        dry_run INTEGER NOT NULL DEFAULT 0,
        api_calls_used INTEGER NOT NULL DEFAULT 0,
        fixtures_discovered INTEGER NOT NULL DEFAULT 0,
        fixtures_mapped INTEGER NOT NULL DEFAULT 0,
        odds_rows_stored INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL,
        message TEXT,
        started_at TEXT NOT NULL,
        finished_at TEXT
    )
    """,
)


def ensure_oddalerts_tables(conn: sqlite3.Connection) -> None:
    for ddl in PHASE_OA2_DDL:
        conn.execute(ddl)
    conn.commit()


@dataclass
class DiscoveredFixture:
    oddalerts_fixture_id: int
    home_team: str
    away_team: str
    kickoff_unix: int | None
    kickoff_iso: str | None
    status: str | None
    competition_id: int | None
    competition_name: str | None
    season_label: str | None
    source: str


@dataclass
class IngestStats:
    league: str
    season: int
    dry_run: bool
    api_calls_used: int = 0
    cache_hits: int = 0
    fixtures_discovered: int = 0
    fixtures_processed: int = 0
    fixtures_skipped_resume: int = 0
    fixtures_skipped_cap: int = 0
    fixture_map_exact: int = 0
    fixture_map_fuzzy: int = 0
    fixture_map_unmatched: int = 0
    odds_rows_stored: int = 0
    odds_rows_skipped_duplicate: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "league": self.league,
            "season": self.season,
            "dry_run": self.dry_run,
            "api_calls_used": self.api_calls_used,
            "cache_hits": self.cache_hits,
            "fixtures_discovered": self.fixtures_discovered,
            "fixtures_processed": self.fixtures_processed,
            "fixtures_skipped_resume": self.fixtures_skipped_resume,
            "fixtures_skipped_cap": self.fixtures_skipped_cap,
            "fixture_mapping": {
                "exact": self.fixture_map_exact,
                "fuzzy": self.fixture_map_fuzzy,
                "unmatched": self.fixture_map_unmatched,
            },
            "odds_rows_stored": self.odds_rows_stored,
            "odds_rows_skipped_duplicate": self.odds_rows_skipped_duplicate,
            "errors": self.errors[:20],
        }


class OddAlertsHistoricalOddsStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        ensure_oddalerts_tables(conn)

    def is_odds_ingested(self, league: str, season: int, oddalerts_fixture_id: int) -> bool:
        row = self._conn.execute(
            """
            SELECT stage FROM oddalerts_ingest_state
            WHERE league = ? AND season = ? AND oddalerts_fixture_id = ? AND stage = 'odds_ingested'
            """,
            (league, season, oddalerts_fixture_id),
        ).fetchone()
        return row is not None

    def mark_stage(
        self,
        *,
        league: str,
        season: int,
        oddalerts_fixture_id: int,
        stage: str,
        odds_rows: int = 0,
        last_error: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO oddalerts_ingest_state (league, season, oddalerts_fixture_id, stage, odds_rows, last_error, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(league, season, oddalerts_fixture_id) DO UPDATE SET
                stage = excluded.stage,
                odds_rows = excluded.odds_rows,
                last_error = excluded.last_error,
                updated_at = excluded.updated_at
            """,
            (league, season, oddalerts_fixture_id, stage, odds_rows, last_error, _utc_now()),
        )

    def upsert_fixture_map(
        self,
        *,
        oddalerts_fixture_id: int,
        internal_fixture_id: int | None,
        league: str,
        season: int,
        home_team: str,
        away_team: str,
        kickoff: str | None,
        mapping_confidence: str,
        probability_json: str | None = None,
        dry_run: bool = False,
    ) -> None:
        if dry_run:
            return
        now = _utc_now()
        self._conn.execute(
            """
            INSERT INTO oddalerts_fixture_map (
                oddalerts_fixture_id, internal_fixture_id, provider, league, season,
                home_team, away_team, kickoff, mapping_confidence, probability_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(oddalerts_fixture_id) DO UPDATE SET
                internal_fixture_id = excluded.internal_fixture_id,
                league = excluded.league,
                season = excluded.season,
                home_team = excluded.home_team,
                away_team = excluded.away_team,
                kickoff = excluded.kickoff,
                mapping_confidence = excluded.mapping_confidence,
                probability_json = COALESCE(excluded.probability_json, oddalerts_fixture_map.probability_json),
                updated_at = excluded.updated_at
            """,
            (
                oddalerts_fixture_id,
                internal_fixture_id,
                PROVIDER_NAME,
                league,
                season,
                home_team,
                away_team,
                kickoff,
                mapping_confidence,
                probability_json,
                now,
                now,
            ),
        )

    def insert_odds_row(
        self,
        *,
        oddalerts_fixture_id: int,
        internal_fixture_id: int | None,
        league: str,
        season: int,
        bookmaker: str,
        market: str,
        selection: str,
        opening_odds: float | None,
        closing_odds: float | None,
        peak_odds: float | None,
        odds_timestamp: str | None,
        implied_probability: float | None,
        raw_json: dict[str, Any],
        dry_run: bool = False,
    ) -> bool:
        if dry_run:
            return True
        try:
            self._conn.execute(
                """
                INSERT INTO oddalerts_odds_history (
                    oddalerts_fixture_id, internal_fixture_id, league, season,
                    bookmaker, market, selection, opening_odds, closing_odds, peak_odds,
                    odds_timestamp, implied_probability, raw_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    oddalerts_fixture_id,
                    internal_fixture_id,
                    league,
                    season,
                    bookmaker,
                    market,
                    selection,
                    opening_odds,
                    closing_odds,
                    peak_odds,
                    odds_timestamp,
                    implied_probability,
                    json.dumps(raw_json, ensure_ascii=False),
                    _utc_now(),
                ),
            )
            return True
        except sqlite3.IntegrityError:
            return False

    def get_cache_payload(self, cache_key: str) -> Any | None:
        row = self._conn.execute(
            "SELECT payload_json, expires_at FROM api_response_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        if row is None:
            return None
        if str(row["expires_at"]) <= _utc_now():
            return None
        try:
            return json.loads(row["payload_json"])
        except (json.JSONDecodeError, TypeError):
            return None

    def set_cache_payload(self, *, cache_key: str, endpoint: str, params: dict[str, Any], payload: Any) -> None:
        expires = (datetime.now(timezone.utc) + timedelta(days=CACHE_TTL_DAYS)).isoformat()
        self._conn.execute(
            """
            INSERT INTO api_response_cache (cache_key, endpoint, params_json, payload_json, cached_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                payload_json = excluded.payload_json,
                cached_at = excluded.cached_at,
                expires_at = excluded.expires_at
            """,
            (
                cache_key,
                endpoint,
                json.dumps(params, sort_keys=True, default=str),
                json.dumps(payload, ensure_ascii=False),
                _utc_now(),
                expires,
            ),
        )

    def commit(self) -> None:
        self._conn.commit()

    def save_run(self, stats: IngestStats, *, status: str, message: str | None, started_at: str) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO oddalerts_ingest_runs (
                league, season, dry_run, api_calls_used, fixtures_discovered, fixtures_mapped,
                odds_rows_stored, status, message, started_at, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stats.league,
                stats.season,
                int(stats.dry_run),
                stats.api_calls_used,
                stats.fixtures_discovered,
                stats.fixture_map_exact + stats.fixture_map_fuzzy,
                stats.odds_rows_stored,
                status,
                message,
                started_at,
                _utc_now(),
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid or 0)


class OddAlertsHistoricalOddsIngester:
    """Cache-first, resume-safe OddAlerts odds history ingester."""

    def __init__(
        self,
        *,
        client: OddAlertsClient | None = None,
        settings: Settings | None = None,
        db_path: str | Path | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client or OddAlertsClient()
        path = db_path or self.settings.sqlite_path
        self._conn = connect(path)
        init_database(path)
        self.store = OddAlertsHistoricalOddsStore(self._conn)

    @property
    def is_configured(self) -> bool:
        return self.client.is_configured

    def _cache_key(self, endpoint: str, params: dict[str, Any]) -> str:
        raw = json.dumps({"endpoint": endpoint, "params": params}, sort_keys=True, default=str)
        return "oddalerts:" + hashlib.sha256(raw.encode()).hexdigest()

    def _cached_get(self, endpoint: str, params: dict[str, Any], stats: IngestStats) -> dict[str, Any] | None:
        key = self._cache_key(endpoint, params)
        cached = self.store.get_cache_payload(key)
        if cached is not None:
            stats.cache_hits += 1
            return cached
        result = self.client._get(endpoint, params=params)
        if result.data is None or result.error:
            stats.errors.append(f"{endpoint}: {result.error}")
            return None
        stats.api_calls_used += 1
        self.store.set_cache_payload(cache_key=key, endpoint=endpoint, params=params, payload=result.data)
        return result.data

    def load_internal_fixtures(self, league: str, season: int) -> list[dict[str, Any]]:
        ph = ",".join("?" * len(_FINISHED))
        if league == "champions_league":
            start = f"{season}-06-01T00:00:00"
            end = f"{season + 1}-08-01T00:00:00"
            q = f"""
                SELECT fixture_id, home_team, away_team, kickoff_utc, status, season
                FROM fixtures
                WHERE competition_key = ? AND is_placeholder = 0
                  AND status IN ({ph})
                  AND kickoff_utc >= ? AND kickoff_utc < ?
                ORDER BY kickoff_utc ASC
            """
            params: list[Any] = [league, *_FINISHED, start, end]
        else:
            q = f"""
                SELECT fixture_id, home_team, away_team, kickoff_utc, status, season
                FROM fixtures
                WHERE competition_key = ? AND is_placeholder = 0
                  AND status IN ({ph}) AND season = ?
                ORDER BY kickoff_utc ASC
            """
            params = [league, *_FINISHED, season]
        return [dict(r) for r in self._conn.execute(q, params).fetchall()]

    def discover_fixtures(
        self,
        *,
        league: str,
        season: int,
        stats: IngestStats,
        max_discovery_pages: int = 25,
    ) -> list[DiscoveredFixture]:
        cfg = ODDALERTS_LEAGUE_MAP.get(league)
        if not cfg:
            stats.errors.append(f"unknown_league:{league}")
            return []
        target_comp_id = int(cfg["competition_id"])
        aliases = season_aliases(season)
        discovered: dict[int, DiscoveredFixture] = {}

        for page in range(1, max_discovery_pages + 1):
            if stats.api_calls_used >= max_discovery_pages:
                break
            for endpoint in ("value/results", "value/upcoming"):
                payload = self._cached_get(endpoint, {"page": page, "per_page": 250}, stats)
                if not payload:
                    continue
                rows = payload.get("data") or []
                if not rows and page == 1:
                    continue
                for row in rows:
                    comp = row.get("competition") or {}
                    comp_id = comp.get("id")
                    season_label = str(comp.get("season") or "")
                    if comp_id != target_comp_id:
                        continue
                    fid = int(row.get("id") or 0)
                    if not fid:
                        continue
                    kickoff_unix = row.get("unix")
                    kickoff_iso = None
                    if kickoff_unix:
                        kickoff_iso = datetime.fromtimestamp(int(kickoff_unix), tz=timezone.utc).isoformat()
                    discovered[fid] = DiscoveredFixture(
                        oddalerts_fixture_id=fid,
                        home_team=str(row.get("home_name") or ""),
                        away_team=str(row.get("away_name") or ""),
                        kickoff_unix=int(kickoff_unix) if kickoff_unix else None,
                        kickoff_iso=kickoff_iso,
                        status=row.get("status"),
                        competition_id=comp_id,
                        competition_name=comp.get("name"),
                        season_label=season_label,
                        source=endpoint,
                    )
                info = payload.get("info") or {}
                if endpoint == "value/results" and not info.get("next_page_url"):
                    break
            info = (payload or {}).get("info") or {}
            if not info.get("next_page_url"):
                break

        # Secondary: fixtures/results endpoint
        payload = self._cached_get(
            "fixtures/results",
            {"competition_id": target_comp_id, "season": season},
            stats,
        )
        if payload:
            for row in payload.get("data") or []:
                fid = int(row.get("id") or row.get("fixture_id") or 0)
                if not fid:
                    continue
                comp = row.get("competition") or {}
                discovered[fid] = DiscoveredFixture(
                    oddalerts_fixture_id=fid,
                    home_team=str(row.get("home_name") or row.get("home") or ""),
                    away_team=str(row.get("away_name") or row.get("away") or ""),
                    kickoff_unix=row.get("unix"),
                    kickoff_iso=row.get("kickoff"),
                    status=row.get("status"),
                    competition_id=comp.get("id") or target_comp_id,
                    competition_name=comp.get("name"),
                    season_label=str(comp.get("season") or season),
                    source="fixtures/results",
                )

        stats.fixtures_discovered = len(discovered)
        return list(discovered.values())

    def discover_fixtures_from_pool(
        self,
        *,
        internal_fixtures: list[dict[str, Any]],
        stats: IngestStats,
        max_discovery_pages: int = 25,
        limit: int = 50,
    ) -> list[DiscoveredFixture]:
        """Fallback: scan value/results and match rows to internal fixtures by teams+date."""
        aliases: dict[int, DiscoveredFixture] = {}
        for page in range(1, max_discovery_pages + 1):
            payload = self._cached_get("value/results", {"page": page, "per_page": 250}, stats)
            if not payload:
                break
            rows = payload.get("data") or []
            if not rows:
                break
            for row in rows:
                fid = int(row.get("id") or 0)
                if not fid:
                    continue
                kickoff_unix = row.get("unix")
                kickoff_iso = None
                if kickoff_unix:
                    kickoff_iso = datetime.fromtimestamp(int(kickoff_unix), tz=timezone.utc).isoformat()
                candidate = DiscoveredFixture(
                    oddalerts_fixture_id=fid,
                    home_team=str(row.get("home_name") or ""),
                    away_team=str(row.get("away_name") or ""),
                    kickoff_unix=int(kickoff_unix) if kickoff_unix else None,
                    kickoff_iso=kickoff_iso,
                    status=row.get("status"),
                    competition_id=(row.get("competition") or {}).get("id"),
                    competition_name=(row.get("competition") or {}).get("name"),
                    season_label=str((row.get("competition") or {}).get("season") or ""),
                    source="value/results_pool_match",
                )
                internal_id, confidence = self.map_internal_fixture(candidate, internal_fixtures)
                if confidence in ("exact", "fuzzy") and internal_id is not None:
                    aliases[fid] = candidate
                    if len(aliases) >= limit:
                        break
            if len(aliases) >= limit:
                break
            info = payload.get("info") or {}
            if not info.get("next_page_url"):
                break
        return list(aliases.values())

    def map_internal_fixture(
        self,
        discovered: DiscoveredFixture,
        internal_fixtures: list[dict[str, Any]],
    ) -> tuple[int | None, str]:
        d_home = _norm_name(discovered.home_team)
        d_away = _norm_name(discovered.away_team)
        d_day = None
        if discovered.kickoff_iso:
            d_day = discovered.kickoff_iso[:10]

        best_id: int | None = None
        best_score = 0.0
        best_conf = "unmatched"

        for fx in internal_fixtures:
            i_home = _norm_name(fx.get("home_team"))
            i_away = _norm_name(fx.get("away_team"))
            kickoff = str(fx.get("kickoff_utc") or "")
            i_day = kickoff[:10] if kickoff else None

            if d_home == i_home and d_away == i_away:
                if d_day and i_day and d_day == i_day:
                    return int(fx["fixture_id"]), "exact"
                if d_day and i_day and d_day != i_day:
                    continue
                return int(fx["fixture_id"]), "exact"

            home_ratio = SequenceMatcher(None, d_home, i_home).ratio() if d_home and i_home else 0.0
            away_ratio = SequenceMatcher(None, d_away, i_away).ratio() if d_away and i_away else 0.0
            if home_ratio < 0.86 or away_ratio < 0.86:
                continue
            day_bonus = 0.05 if d_day and i_day and d_day == i_day else 0.0
            score = (home_ratio + away_ratio) / 2 + day_bonus
            if score > best_score:
                best_score = score
                best_id = int(fx["fixture_id"])
                best_conf = "fuzzy"

        if best_id is not None and best_score >= 0.9:
            return best_id, best_conf
        return None, "unmatched"

    def ingest_odds_history(
        self,
        *,
        discovered: DiscoveredFixture,
        league: str,
        season: int,
        internal_fixture_id: int | None,
        mapping_confidence: str,
        stats: IngestStats,
        max_api_calls: int,
        dry_run: bool,
        resume: bool,
    ) -> int:
        fid = discovered.oddalerts_fixture_id
        if resume and self.store.is_odds_ingested(league, season, fid):
            stats.fixtures_skipped_resume += 1
            return 0
        if stats.api_calls_used >= max_api_calls:
            stats.fixtures_skipped_cap += 1
            return 0

        probability_json = None
        if stats.api_calls_used < max_api_calls:
            detail = self._cached_get(
                f"fixtures/{fid}",
                {"include": "probability"},
                stats,
            )
            if detail and isinstance(detail.get("data"), list) and detail["data"]:
                probability_json = json.dumps(detail["data"][0].get("probability"))

        if stats.api_calls_used >= max_api_calls:
            stats.fixtures_skipped_cap += 1
            return 0

        payload = self._cached_get("odds/history", {"id": fid}, stats)
        rows = (payload or {}).get("data") or []
        stored = 0

        self.store.upsert_fixture_map(
            oddalerts_fixture_id=fid,
            internal_fixture_id=internal_fixture_id,
            league=league,
            season=season,
            home_team=discovered.home_team,
            away_team=discovered.away_team,
            kickoff=discovered.kickoff_iso,
            mapping_confidence=mapping_confidence,
            probability_json=probability_json,
            dry_run=dry_run,
        )

        for row in rows:
            bookmaker = str(row.get("bookmaker_name") or row.get("bookmaker") or "unknown")
            market = str(row.get("market_key") or row.get("market") or "unknown")
            selection = str(row.get("outcome") or row.get("selection") or "unknown")
            opening = _parse_decimal(row.get("opening"))
            closing = _parse_decimal(row.get("closing"))
            peak = _parse_decimal(row.get("peak"))
            implied = _implied_prob(closing or opening or peak)
            inserted = self.store.insert_odds_row(
                oddalerts_fixture_id=fid,
                internal_fixture_id=internal_fixture_id,
                league=league,
                season=season,
                bookmaker=bookmaker,
                market=market,
                selection=selection,
                opening_odds=opening,
                closing_odds=closing,
                peak_odds=peak,
                odds_timestamp=discovered.kickoff_iso,
                implied_probability=implied,
                raw_json=row,
                dry_run=dry_run,
            )
            if inserted:
                stored += 1
                stats.odds_rows_stored += 1
            else:
                stats.odds_rows_skipped_duplicate += 1

        if not dry_run:
            self.store.mark_stage(
                league=league,
                season=season,
                oddalerts_fixture_id=fid,
                stage="odds_ingested",
                odds_rows=stored,
            )
        stats.fixtures_processed += 1
        return stored

    def run_ingest(
        self,
        *,
        league: str,
        season: int,
        limit_fixtures: int | None = 50,
        max_api_calls: int = 100,
        dry_run: bool = False,
        resume: bool = True,
        max_discovery_pages: int = 25,
    ) -> dict[str, Any]:
        started_at = _utc_now()
        stats = IngestStats(league=league, season=season, dry_run=dry_run)
        if not self.is_configured:
            return {
                **stats.to_dict(),
                "status": "error",
                "message": "ODDALERTS_API_KEY not configured",
                "started_at": started_at,
                "finished_at": _utc_now(),
            }

        internal_fixtures = self.load_internal_fixtures(league, season)
        discovered = self.discover_fixtures(
            league=league,
            season=season,
            stats=stats,
            max_discovery_pages=min(max_discovery_pages, max(1, max_api_calls // 2)),
        )

        if not discovered and internal_fixtures:
            stats.errors.append(
                "no_oddalerts_fixtures_discovered_for_league_season — trying pool match against internal fixtures"
            )
            discovered = self.discover_fixtures_from_pool(
                internal_fixtures=internal_fixtures,
                stats=stats,
                max_discovery_pages=min(max_discovery_pages, max(1, max_api_calls // 3)),
                limit=limit_fixtures or 50,
            )
            stats.fixtures_discovered = len(discovered)
        if not discovered and internal_fixtures:
            stats.errors.append(
                "no_oddalerts_fixtures_discovered_for_league_season — trial API pool may not include this competition"
            )

        targets = discovered[: limit_fixtures or len(discovered)]
        for item in targets:
            if stats.api_calls_used >= max_api_calls and stats.fixtures_processed == 0:
                break
            internal_id, confidence = self.map_internal_fixture(item, internal_fixtures)
            if confidence == "exact":
                stats.fixture_map_exact += 1
            elif confidence == "fuzzy":
                stats.fixture_map_fuzzy += 1
            else:
                stats.fixture_map_unmatched += 1

            self.ingest_odds_history(
                discovered=item,
                league=league,
                season=season,
                internal_fixture_id=internal_id,
                mapping_confidence=confidence,
                stats=stats,
                max_api_calls=max_api_calls,
                dry_run=dry_run,
                resume=resume,
            )
            if stats.fixtures_processed >= (limit_fixtures or 999999):
                break

        self.store.commit()
        status = "ok" if not stats.errors else "partial"
        message = None
        if not discovered:
            message = "Zero OddAlerts fixtures discovered for requested league/season on trial token"
        run_id = 0 if dry_run else self.store.save_run(stats, status=status, message=message, started_at=started_at)
        return {
            **stats.to_dict(),
            "status": status,
            "message": message,
            "internal_fixtures_available": len(internal_fixtures),
            "run_id": run_id,
            "started_at": started_at,
            "finished_at": _utc_now(),
        }


def collect_ingest_summary(conn: sqlite3.Connection, *, league: str | None = None) -> dict[str, Any]:
    ensure_oddalerts_tables(conn)
    where = "WHERE league = ?" if league else ""
    params: list[Any] = [league] if league else []

    map_rows = conn.execute(
        f"SELECT mapping_confidence, COUNT(*) AS c FROM oddalerts_fixture_map {where} GROUP BY mapping_confidence",
        params,
    ).fetchall()
    odds_count = conn.execute(f"SELECT COUNT(*) FROM oddalerts_odds_history {where}", params).fetchone()[0]
    extra = " AND" if where else " WHERE"
    opening = conn.execute(
        f"SELECT COUNT(*) FROM oddalerts_odds_history {where}{extra} opening_odds IS NOT NULL",
        params,
    ).fetchone()[0]
    closing = conn.execute(
        f"SELECT COUNT(*) FROM oddalerts_odds_history {where}{extra} closing_odds IS NOT NULL",
        params,
    ).fetchone()[0]
    peak = conn.execute(
        f"SELECT COUNT(*) FROM oddalerts_odds_history {where}{extra} peak_odds IS NOT NULL",
        params,
    ).fetchone()[0]
    bookmakers = conn.execute(
        f"SELECT bookmaker, COUNT(*) AS c FROM oddalerts_odds_history {where} GROUP BY bookmaker ORDER BY c DESC LIMIT 20",
        params,
    ).fetchall()
    markets = conn.execute(
        f"SELECT market, COUNT(*) AS c FROM oddalerts_odds_history {where} GROUP BY market ORDER BY c DESC LIMIT 20",
        params,
    ).fetchall()
    dupes = conn.execute(
        """
        SELECT oddalerts_fixture_id, bookmaker, market, selection, COUNT(*) AS c
        FROM oddalerts_odds_history
        GROUP BY oddalerts_fixture_id, bookmaker, market, selection
        HAVING c > 1
        LIMIT 5
        """
    ).fetchall()

    return {
        "fixture_map_counts": {str(r[0]): int(r[1]) for r in map_rows},
        "odds_rows_total": int(odds_count),
        "opening_odds_rows": int(opening),
        "closing_odds_rows": int(closing),
        "peak_odds_rows": int(peak),
        "bookmaker_coverage": {str(r[0]): int(r[1]) for r in bookmakers},
        "market_coverage": {str(r[0]): int(r[1]) for r in markets},
        "duplicate_rows_sample": [dict(r) for r in dupes],
    }
