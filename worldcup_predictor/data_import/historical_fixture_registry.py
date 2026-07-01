"""PHASE DATA-1C — Historical fixture registry from CSV odds (staging, no API).

Architecture notes (schema reuse audit):
- ``fixtures`` — production API-Football identities; never insert synthetic rows here.
- ``oddalerts_fixture_map`` — API OddAlerts fixture IDs; CSV exports use selection row IDs.
- ``historical_csv_odds_imports`` — DATA-1B odds staging (extended with registry links).
- ``historical_fixture_registry`` — NEW staging registry: one row per unique CSV match identity.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.data_import.historical_csv_odds import (
    _norm_team,
    backup_database,
    build_fixture_index,
    match_fixture,
)

PROVIDER = "oddalerts_csv"

DATA_1C_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS historical_fixture_registry (
        registry_fixture_id INTEGER PRIMARY KEY AUTOINCREMENT,
        registry_key TEXT NOT NULL UNIQUE,
        match_date TEXT NOT NULL,
        league TEXT,
        league_normalized TEXT,
        season TEXT,
        home_team TEXT NOT NULL,
        away_team TEXT NOT NULL,
        home_team_normalized TEXT NOT NULL,
        away_team_normalized TEXT NOT NULL,
        kickoff_utc TEXT,
        competition_name TEXT,
        internal_fixture_id INTEGER,
        production_match_method TEXT,
        mapping_status TEXT NOT NULL DEFAULT 'registry_only',
        home_goals INTEGER,
        away_goals INTEGER,
        match_status TEXT,
        odds_row_count INTEGER NOT NULL DEFAULT 0,
        source_providers TEXT,
        duplicate_team_flag INTEGER NOT NULL DEFAULT 0,
        ambiguous_production_match INTEGER NOT NULL DEFAULT 0,
        raw_team_variants_json TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_historical_fixture_registry_date
    ON historical_fixture_registry(match_date)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_historical_fixture_registry_league
    ON historical_fixture_registry(league_normalized, season)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_historical_fixture_registry_internal
    ON historical_fixture_registry(internal_fixture_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_historical_csv_odds_registry_key
    ON historical_csv_odds_imports(registry_key)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_historical_csv_odds_registry_fixture
    ON historical_csv_odds_imports(registry_fixture_id)
    """,
)

ODDS_COLUMN_ALTERATIONS: tuple[str, ...] = (
    "ALTER TABLE historical_csv_odds_imports ADD COLUMN registry_key TEXT",
    "ALTER TABLE historical_csv_odds_imports ADD COLUMN registry_fixture_id INTEGER",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _norm_league(value: str | None) -> str:
    text = (value or "unknown").lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text or "unknown"


def build_registry_key(
    *,
    match_date: str,
    league: str | None,
    competition_name: str | None,
    home_team: str,
    away_team: str,
) -> str:
    league_src = (league or "").strip() or (competition_name or "").strip() or "unknown"
    league_norm = _norm_league(league_src)
    home_norm = _norm_team(home_team)
    away_norm = _norm_team(away_team)
    date_part = (match_date or "")[:10]
    raw = "|".join([date_part, league_norm, home_norm, away_norm])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    return column in cols


def ensure_data_1c_schema(conn: sqlite3.Connection) -> None:
    for ddl in DATA_1C_DDL:
        try:
            conn.execute(ddl)
        except sqlite3.OperationalError:
            pass
    for alter in ODDS_COLUMN_ALTERATIONS:
        col = alter.split("ADD COLUMN ")[1].split()[0]
        if not _table_has_column(conn, "historical_csv_odds_imports", col):
            try:
                conn.execute(alter)
            except sqlite3.OperationalError:
                pass
    conn.commit()


@dataclass
class RegistryBuildStats:
    odds_rows_total: int = 0
    odds_rows_unlinked_before: int = 0
    registry_candidates: int = 0
    registry_inserted: int = 0
    registry_skipped_duplicate: int = 0
    odds_registry_keys_set: int = 0
    odds_linked_to_registry: int = 0
    production_linked: int = 0
    production_already_linked: int = 0
    ambiguous_production: int = 0
    duplicate_team_flags: int = 0
    team_name_variants: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "odds_rows_total": self.odds_rows_total,
            "odds_rows_unlinked_before": self.odds_rows_unlinked_before,
            "registry_candidates": self.registry_candidates,
            "registry_inserted": self.registry_inserted,
            "registry_skipped_duplicate": self.registry_skipped_duplicate,
            "odds_registry_keys_set": self.odds_registry_keys_set,
            "odds_linked_to_registry": self.odds_linked_to_registry,
            "production_linked": self.production_linked,
            "production_already_linked": self.production_already_linked,
            "ambiguous_production": self.ambiguous_production,
            "duplicate_team_flags": self.duplicate_team_flags,
            "team_name_variants": self.team_name_variants,
            "errors": self.errors[:50],
        }


def _aggregate_match_groups(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            match_date,
            COALESCE(NULLIF(TRIM(league), ''), NULLIF(TRIM(competition_name), ''), 'unknown') AS league,
            home_team,
            away_team,
            MIN(kickoff_utc) AS kickoff_utc,
            MAX(season) AS season,
            MAX(competition_name) AS competition_name,
            MAX(internal_fixture_id) AS internal_fixture_id,
            MAX(home_goals) AS home_goals,
            MAX(away_goals) AS away_goals,
            MAX(match_status) AS match_status,
            COUNT(*) AS odds_row_count,
            GROUP_CONCAT(DISTINCT provider) AS source_providers
        FROM historical_csv_odds_imports
        WHERE match_date IS NOT NULL
          AND home_team IS NOT NULL
          AND away_team IS NOT NULL
        GROUP BY
            match_date,
            COALESCE(NULLIF(TRIM(league), ''), NULLIF(TRIM(competition_name), ''), 'unknown'),
            home_team,
            away_team
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _collapse_registry_candidates(groups: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Merge raw groups into one registry row per normalized registry_key."""
    merged: dict[str, dict[str, Any]] = {}
    ambiguous_log: list[dict[str, Any]] = []

    for g in groups:
        registry_key = build_registry_key(
            match_date=g["match_date"],
            league=g["league"],
            competition_name=g.get("competition_name"),
            home_team=g["home_team"],
            away_team=g["away_team"],
        )
        home_norm = _norm_team(g["home_team"])
        away_norm = _norm_team(g["away_team"])
        league_norm = _norm_league(g["league"])

        if registry_key not in merged:
            merged[registry_key] = {
                "registry_key": registry_key,
                "match_date": g["match_date"][:10],
                "league": g["league"],
                "league_normalized": league_norm,
                "season": g.get("season") or "",
                "home_team": g["home_team"],
                "away_team": g["away_team"],
                "home_team_normalized": home_norm,
                "away_team_normalized": away_norm,
                "kickoff_utc": g.get("kickoff_utc"),
                "competition_name": g.get("competition_name"),
                "internal_fixture_id": g.get("internal_fixture_id"),
                "home_goals": g.get("home_goals"),
                "away_goals": g.get("away_goals"),
                "match_status": g.get("match_status"),
                "odds_row_count": int(g["odds_row_count"]),
                "source_providers": g.get("source_providers") or PROVIDER,
                "home_variants": Counter([g["home_team"]]),
                "away_variants": Counter([g["away_team"]]),
                "league_variants": Counter([g["league"]]),
            }
        else:
            entry = merged[registry_key]
            entry["odds_row_count"] += int(g["odds_row_count"])
            entry["home_variants"][g["home_team"]] += 1
            entry["away_variants"][g["away_team"]] += 1
            entry["league_variants"][g["league"]] += 1
            if g.get("internal_fixture_id") and not entry.get("internal_fixture_id"):
                entry["internal_fixture_id"] = g["internal_fixture_id"]
            if not entry.get("kickoff_utc") and g.get("kickoff_utc"):
                entry["kickoff_utc"] = g["kickoff_utc"]

    for entry in merged.values():
        if entry["home_team_normalized"] == entry["away_team_normalized"]:
            entry["duplicate_team_flag"] = 1
        else:
            entry["duplicate_team_flag"] = 0

        if len(entry["home_variants"]) > 1 or len(entry["away_variants"]) > 1:
            ambiguous_log.append(
                {
                    "registry_key": entry["registry_key"],
                    "match_date": entry["match_date"],
                    "league": entry["league"],
                    "home_variants": dict(entry["home_variants"]),
                    "away_variants": dict(entry["away_variants"]),
                }
            )
            entry["home_team"] = entry["home_variants"].most_common(1)[0][0]
            entry["away_team"] = entry["away_variants"].most_common(1)[0][0]
            entry["league"] = entry["league_variants"].most_common(1)[0][0]

        entry["raw_team_variants_json"] = json.dumps(
            {
                "home": dict(entry["home_variants"]),
                "away": dict(entry["away_variants"]),
                "league": dict(entry["league_variants"]),
            },
            ensure_ascii=False,
        )
        del entry["home_variants"]
        del entry["away_variants"]
        del entry["league_variants"]

    return merged, ambiguous_log


def _resolve_production_links(
    registry_rows: dict[str, dict[str, Any]],
    fixture_index: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    ambiguous_log: list[dict[str, Any]] = []
    for entry in registry_rows.values():
        if entry.get("internal_fixture_id"):
            entry["mapping_status"] = "production_prelinked"
            entry["production_match_method"] = "csv_internal_fixture_id"
            continue

        kickoff = entry.get("kickoff_utc") or entry["match_date"]
        fixture_id, method = match_fixture(
            kickoff=kickoff,
            home_team=entry["home_team"],
            away_team=entry["away_team"],
            index=fixture_index,
        )
        if fixture_id and method == "exact_date_teams":
            entry["internal_fixture_id"] = fixture_id
            entry["production_match_method"] = method
            entry["mapping_status"] = "production_linked"
            entry["ambiguous_production_match"] = 0
        elif fixture_id and method == "exact_date_teams_ambiguous":
            entry["internal_fixture_id"] = None
            entry["production_match_method"] = method
            entry["mapping_status"] = "ambiguous_production"
            entry["ambiguous_production_match"] = 1
            ambiguous_log.append(
                {
                    "registry_key": entry["registry_key"],
                    "match_date": entry["match_date"],
                    "home_team": entry["home_team"],
                    "away_team": entry["away_team"],
                    "reason": "multiple_production_fixtures_same_date_teams",
                }
            )
        else:
            entry["internal_fixture_id"] = None
            entry["production_match_method"] = None
            entry["mapping_status"] = "registry_only"
            entry["ambiguous_production_match"] = 0
    return ambiguous_log


def _insert_registry_rows(
    conn: sqlite3.Connection,
    registry_rows: dict[str, dict[str, Any]],
    *,
    dry_run: bool,
) -> tuple[int, int]:
    inserted = 0
    skipped = 0
    now = _utc_now()
    sql = """
        INSERT OR IGNORE INTO historical_fixture_registry (
            registry_key, match_date, league, league_normalized, season,
            home_team, away_team, home_team_normalized, away_team_normalized,
            kickoff_utc, competition_name, internal_fixture_id,
            production_match_method, mapping_status,
            home_goals, away_goals, match_status, odds_row_count,
            source_providers, duplicate_team_flag, ambiguous_production_match,
            raw_team_variants_json, created_at, updated_at
        ) VALUES (
            :registry_key, :match_date, :league, :league_normalized, :season,
            :home_team, :away_team, :home_team_normalized, :away_team_normalized,
            :kickoff_utc, :competition_name, :internal_fixture_id,
            :production_match_method, :mapping_status,
            :home_goals, :away_goals, :match_status, :odds_row_count,
            :source_providers, :duplicate_team_flag, :ambiguous_production_match,
            :raw_team_variants_json, :created_at, :updated_at
        )
    """
    for entry in registry_rows.values():
        payload = {
            **entry,
            "ambiguous_production_match": int(entry.get("ambiguous_production_match") or 0),
            "duplicate_team_flag": int(entry.get("duplicate_team_flag") or 0),
            "created_at": now,
            "updated_at": now,
        }
        if dry_run:
            inserted += 1
            continue
        before = conn.total_changes
        conn.execute(sql, payload)
        if conn.total_changes > before:
            inserted += 1
        else:
            skipped += 1
    return inserted, skipped


def _set_odds_registry_keys(conn: sqlite3.Connection, *, dry_run: bool, batch_size: int = 20000) -> int:
    updated = 0
    while True:
        rows = conn.execute(
            """
            SELECT id, match_date, league, competition_name, home_team, away_team
            FROM historical_csv_odds_imports
            WHERE registry_key IS NULL
            LIMIT ?
            """,
            (batch_size,),
        ).fetchall()
        if not rows:
            break
        if dry_run:
            updated += len(rows)
            break
        for row in rows:
            rk = build_registry_key(
                match_date=row["match_date"] or "",
                league=row["league"],
                competition_name=row["competition_name"],
                home_team=row["home_team"],
                away_team=row["away_team"],
            )
            conn.execute(
                "UPDATE historical_csv_odds_imports SET registry_key = ? WHERE id = ?",
                (rk, row["id"]),
            )
            updated += 1
        conn.commit()
    return updated


def _link_odds_to_registry(conn: sqlite3.Connection, *, dry_run: bool) -> int:
    if dry_run:
        row = conn.execute(
            """
            SELECT COUNT(*) AS c FROM historical_csv_odds_imports o
            WHERE o.registry_key IS NOT NULL
              AND EXISTS (
                SELECT 1 FROM historical_fixture_registry r
                WHERE r.registry_key = o.registry_key
              )
            """
        ).fetchone()
        return int(row["c"]) if row else 0

    conn.execute(
        """
        UPDATE historical_csv_odds_imports
        SET registry_fixture_id = (
            SELECT r.registry_fixture_id
            FROM historical_fixture_registry r
            WHERE r.registry_key = historical_csv_odds_imports.registry_key
        )
        WHERE registry_key IS NOT NULL
          AND registry_fixture_id IS NULL
        """
    )
    conn.commit()
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM historical_csv_odds_imports WHERE registry_fixture_id IS NOT NULL"
    ).fetchone()
    return int(row["c"]) if row else 0


def build_registry_and_link_odds(
    conn: sqlite3.Connection,
    *,
    dry_run: bool = False,
) -> tuple[RegistryBuildStats, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    ensure_data_1c_schema(conn)
    stats = RegistryBuildStats()

    total_row = conn.execute("SELECT COUNT(*) AS c FROM historical_csv_odds_imports").fetchone()
    stats.odds_rows_total = int(total_row["c"]) if total_row else 0

    unlinked_row = conn.execute(
        "SELECT COUNT(*) AS c FROM historical_csv_odds_imports WHERE registry_fixture_id IS NULL"
    ).fetchone()
    stats.odds_rows_unlinked_before = int(unlinked_row["c"]) if unlinked_row else 0

    groups = _aggregate_match_groups(conn)
    registry_rows, team_variant_log = _collapse_registry_candidates(groups)
    stats.registry_candidates = len(registry_rows)
    stats.team_name_variants = len(team_variant_log)
    stats.duplicate_team_flags = sum(1 for r in registry_rows.values() if r.get("duplicate_team_flag"))

    fixture_index = build_fixture_index(conn)
    production_ambiguous = _resolve_production_links(registry_rows, fixture_index)
    stats.production_linked = sum(
        1 for r in registry_rows.values() if r.get("mapping_status") == "production_linked"
    )
    stats.production_already_linked = sum(
        1 for r in registry_rows.values() if r.get("mapping_status") == "production_prelinked"
    )
    stats.ambiguous_production = sum(
        1 for r in registry_rows.values() if r.get("mapping_status") == "ambiguous_production"
    )

    inserted, skipped = _insert_registry_rows(conn, registry_rows, dry_run=dry_run)
    stats.registry_inserted = inserted
    stats.registry_skipped_duplicate = skipped

    stats.odds_registry_keys_set = _set_odds_registry_keys(conn, dry_run=dry_run)
    stats.odds_linked_to_registry = _link_odds_to_registry(conn, dry_run=dry_run)

    if not dry_run:
        conn.commit()

    coverage = query_coverage(conn)
    ambiguous_combined = team_variant_log + production_ambiguous
    return stats, ambiguous_combined, team_variant_log, coverage


def query_coverage(conn: sqlite3.Connection) -> dict[str, Any]:
    by_league = [
        dict(r)
        for r in conn.execute(
            """
            SELECT league, COUNT(*) AS fixtures, SUM(odds_row_count) AS odds_rows
            FROM historical_fixture_registry
            GROUP BY league
            ORDER BY fixtures DESC
            LIMIT 30
            """
        ).fetchall()
    ]
    by_season = [
        dict(r)
        for r in conn.execute(
            """
            SELECT season, COUNT(*) AS fixtures, SUM(odds_row_count) AS odds_rows
            FROM historical_fixture_registry
            WHERE season IS NOT NULL AND season != ''
            GROUP BY season
            ORDER BY season
            """
        ).fetchall()
    ]
    by_market = [
        dict(r)
        for r in conn.execute(
            """
            SELECT o.market, COUNT(*) AS odds_rows,
                   COUNT(DISTINCT o.registry_fixture_id) AS registry_fixtures
            FROM historical_csv_odds_imports o
            WHERE o.registry_fixture_id IS NOT NULL
            GROUP BY o.market
            ORDER BY odds_rows DESC
            """
        ).fetchall()
    ]
    registry_total = conn.execute("SELECT COUNT(*) AS c FROM historical_fixture_registry").fetchone()
    linked_odds = conn.execute(
        "SELECT COUNT(*) AS c FROM historical_csv_odds_imports WHERE registry_fixture_id IS NOT NULL"
    ).fetchone()
    production_fixtures_before = conn.execute("SELECT COUNT(*) AS c FROM fixtures").fetchone()
    return {
        "registry_fixtures_total": int(registry_total["c"]) if registry_total else 0,
        "odds_rows_linked": int(linked_odds["c"]) if linked_odds else 0,
        "production_fixtures_count_unchanged": int(production_fixtures_before["c"]) if production_fixtures_before else 0,
        "by_league_top30": by_league,
        "by_season": by_season,
        "by_market": by_market,
    }


def backup_database_data1c(db_path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"football_intelligence_pre_data1c_{stamp}.db"
    dest.write_bytes(db_path.read_bytes())
    return dest


__all__ = [
    "backup_database",
    "backup_database_data1c",
    "build_registry_and_link_odds",
    "build_registry_key",
    "ensure_data_1c_schema",
    "query_coverage",
]
