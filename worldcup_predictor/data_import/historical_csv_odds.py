"""PHASE DATA-1B — Historical OddAlerts CSV odds catalog + import (no API)."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

PROVIDER = "oddalerts_csv"
DEFAULT_CSV_ROOTS: tuple[str, ...] = (
    "data/imports/oddalerts_probability_exports",
    "data/imports",
    "data/odds",
    "data/csv",
    "downloads",
    "artifacts",
)

DATA_1B_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS historical_csv_odds_imports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider TEXT NOT NULL,
        source_file TEXT NOT NULL,
        source_sha256 TEXT NOT NULL,
        oddalerts_row_id INTEGER,
        internal_fixture_id INTEGER,
        match_key TEXT NOT NULL,
        match_date TEXT,
        kickoff_utc TEXT,
        league TEXT,
        season TEXT,
        home_team TEXT NOT NULL,
        away_team TEXT NOT NULL,
        market TEXT NOT NULL,
        selection TEXT NOT NULL,
        bookmaker TEXT NOT NULL,
        opening_odds REAL,
        closing_odds REAL,
        peak_odds REAL,
        opening_unix INTEGER,
        closing_unix INTEGER,
        peak_unix INTEGER,
        probability_pct REAL,
        implied_odds REAL,
        match_status TEXT,
        home_goals INTEGER,
        away_goals INTEGER,
        match_outcome TEXT,
        competition_name TEXT,
        match_method TEXT,
        dedup_key TEXT NOT NULL UNIQUE,
        raw_json TEXT NOT NULL,
        imported_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_historical_csv_odds_fixture
    ON historical_csv_odds_imports(internal_fixture_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_historical_csv_odds_market
    ON historical_csv_odds_imports(market, selection)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_historical_csv_odds_match_date
    ON historical_csv_odds_imports(match_date)
    """,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _norm_team(value: str | None) -> str:
    text = (value or "").lower().strip()
    text = re.sub(r"\b(fc|cf|sc|afc|bsc|sv|vfb|tsg|ud)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def _parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def ensure_historical_csv_odds_table(conn: sqlite3.Connection) -> None:
    for ddl in DATA_1B_DDL:
        conn.execute(ddl)
    conn.commit()


def detect_market_from_path(path: Path) -> str:
    parts = {p.lower() for p in path.parts}
    name = path.stem.lower()
    if "fulltime_result" in parts or "ft_result" in name:
        return "ft_result"
    if "both_teams_to_score" in parts or "btts" in name:
        return "btts"
    if "double_chance" in parts:
        return "double_chance"
    if "first_half_winner" in parts:
        return "first_half_winner"
    if "corners_over_under" in name or any("corners_over_under" in p for p in parts):
        return "corners_over_under"
    if "home_over_under" in name or "away_over_under" in name:
        return "team_over_under"
    if "over_under" in name or any(p.startswith("over_under") for p in parts):
        return "over_under"
    return "unknown"


def detect_encoding(path: Path) -> tuple[str, str | None]:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return enc, raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return "unknown", None


def catalog_csv_file(path: Path, project_root: Path) -> dict[str, Any]:
    enc, text = detect_encoding(path)
    size = path.stat().st_size
    rel = str(path.resolve().relative_to(project_root.resolve())).replace("\\", "/")
    entry: dict[str, Any] = {
        "filename": path.name,
        "absolute_path": str(path.resolve()),
        "relative_path": rel,
        "size_bytes": size,
        "row_count": 0,
        "delimiter": ",",
        "encoding": enc,
        "columns": [],
        "sample_rows": [],
        "market_type": detect_market_from_path(path),
        "bookmaker": None,
        "date_min": None,
        "date_max": None,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "issues": [],
    }
    if text is None:
        entry["issues"].append("encoding_failure")
        return entry

    try:
        reader = csv.DictReader(text.splitlines())
        cols = list(reader.fieldnames or [])
        entry["columns"] = cols
        rows = list(reader)
        entry["row_count"] = len(rows)
        entry["sample_rows"] = rows[:3]
        if rows:
            bookmakers = {r.get("Bookmaker", "").strip() for r in rows if r.get("Bookmaker")}
            entry["bookmaker"] = sorted(bookmakers)[0] if len(bookmakers) == 1 else sorted(bookmakers)[:5]
            kickoffs = []
            for r in rows:
                k = (r.get("Kickoff") or "").strip()
                if k:
                    kickoffs.append(k[:10])
            if kickoffs:
                entry["date_min"] = min(kickoffs)
                entry["date_max"] = max(kickoffs)
        if entry["row_count"] == 0:
            entry["issues"].append("empty_or_header_only")
    except csv.Error as exc:
        entry["issues"].append(f"csv_error: {exc}")

    return entry


def discover_csv_files(project_root: Path, extra_roots: Iterable[str] = ()) -> list[Path]:
    roots = list(DEFAULT_CSV_ROOTS) + list(extra_roots)
    found: list[Path] = []
    seen: set[str] = set()
    for root_rel in roots:
        root = project_root / root_rel
        if not root.is_dir():
            continue
        for path in root.rglob("*.csv"):
            if path.name in ("manifest.csv", "manifest.dry_run.csv"):
                continue
            if path.name.startswith("backtest_"):
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            found.append(path)
    return sorted(found)


def build_fixture_index(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rows = conn.execute(
        """
        SELECT fixture_id, home_team, away_team, kickoff_utc, competition_key, status
        FROM fixtures
        WHERE kickoff_utc IS NOT NULL
        """
    ).fetchall()
    for row in rows:
        kickoff = (row["kickoff_utc"] or "")[:10]
        if not kickoff:
            continue
        key = f"{kickoff}|{_norm_team(row['home_team'])}|{_norm_team(row['away_team'])}"
        index[key].append(dict(row))
    return index


def match_fixture(
    *,
    kickoff: str,
    home_team: str,
    away_team: str,
    index: dict[str, list[dict[str, Any]]],
) -> tuple[int | None, str]:
    date_part = kickoff.strip()[:10]
    key = f"{date_part}|{_norm_team(home_team)}|{_norm_team(away_team)}"
    hits = index.get(key, [])
    if len(hits) == 1:
        return int(hits[0]["fixture_id"]), "exact_date_teams"
    if len(hits) > 1:
        return int(hits[0]["fixture_id"]), "exact_date_teams_ambiguous"
    return None, "unmatched"


def _season_from_date(date_str: str) -> str:
    try:
        dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
        return str(dt.year if dt.month >= 7 else dt.year - 1)
    except ValueError:
        return ""


def _dedup_key(
    *,
    provider: str,
    source_file: str,
    oddalerts_row_id: int | None,
    market: str,
    selection: str,
    bookmaker: str,
    match_key: str,
) -> str:
    raw = "|".join(
        [
            provider,
            source_file,
            str(oddalerts_row_id or ""),
            market,
            selection,
            bookmaker,
            match_key,
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def row_to_records(
    row: dict[str, str],
    *,
    source_file: str,
    source_sha256: str,
    market_type: str,
    fixture_index: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any] | None, str]:
    home = (row.get("Home Team") or "").strip()
    away = (row.get("Away Team") or "").strip()
    kickoff = (row.get("Kickoff") or "").strip()
    if not home or not away or not kickoff:
        return None, "missing_teams_or_kickoff"

    match_key = f"{kickoff[:10]}|{_norm_team(home)}|{_norm_team(away)}"
    fixture_id, match_method = match_fixture(
        kickoff=kickoff,
        home_team=home,
        away_team=away,
        index=fixture_index,
    )

    selection = (row.get("Outcome") or "").strip()
    bookmaker = (row.get("Bookmaker") or "unknown").strip()
    oddalerts_row_id = _parse_int(row.get("ID"))

    record = {
        "provider": PROVIDER,
        "source_file": source_file,
        "source_sha256": source_sha256,
        "oddalerts_row_id": oddalerts_row_id,
        "internal_fixture_id": fixture_id,
        "match_key": match_key,
        "match_date": kickoff[:10],
        "kickoff_utc": kickoff,
        "league": (row.get("Competition Name") or "").strip() or None,
        "season": _season_from_date(kickoff),
        "home_team": home,
        "away_team": away,
        "market": market_type,
        "selection": selection,
        "bookmaker": bookmaker,
        "opening_odds": _parse_float(row.get("Opening Odds")),
        "closing_odds": _parse_float(row.get("Closing Odds")),
        "peak_odds": _parse_float(row.get("Peak Odds")),
        "opening_unix": _parse_int(row.get("Opening Unix")),
        "closing_unix": _parse_int(row.get("Closing Unix")),
        "peak_unix": _parse_int(row.get("Peak Unix")),
        "probability_pct": _parse_float(row.get("Probability (%)")),
        "implied_odds": _parse_float(row.get("Implied Odds")),
        "match_status": (row.get("Status") or "").strip() or None,
        "home_goals": _parse_int(row.get("Home Goals")),
        "away_goals": _parse_int(row.get("Away Goals")),
        "match_outcome": selection,
        "competition_name": (row.get("Competition Name") or "").strip() or None,
        "match_method": match_method,
        "dedup_key": _dedup_key(
            provider=PROVIDER,
            source_file=source_file,
            oddalerts_row_id=oddalerts_row_id,
            market=market_type,
            selection=selection,
            bookmaker=bookmaker,
            match_key=match_key,
        ),
        "raw_json": json.dumps(row, ensure_ascii=False),
        "imported_at": _utc_now(),
    }
    return record, match_method


@dataclass
class ImportStats:
    files_discovered: int = 0
    files_cataloged: int = 0
    files_skipped_dup_sha: int = 0
    files_skipped_empty: int = 0
    rows_parsed: int = 0
    rows_inserted: int = 0
    rows_skipped_duplicate: int = 0
    rows_skipped_invalid: int = 0
    rows_unmatched: int = 0
    rows_matched: int = 0
    markets: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "files_discovered": self.files_discovered,
            "files_cataloged": self.files_cataloged,
            "files_skipped_dup_sha": self.files_skipped_dup_sha,
            "files_skipped_empty": self.files_skipped_empty,
            "rows_parsed": self.rows_parsed,
            "rows_inserted": self.rows_inserted,
            "rows_skipped_duplicate": self.rows_skipped_duplicate,
            "rows_skipped_invalid": self.rows_skipped_invalid,
            "rows_unmatched": self.rows_unmatched,
            "rows_matched": self.rows_matched,
            "markets": dict(self.markets),
            "errors": self.errors[:50],
        }


def catalog_all(project_root: Path) -> list[dict[str, Any]]:
    files = discover_csv_files(project_root)
    return [catalog_csv_file(p, project_root) for p in files]


ODDALERTS_EXPECTED_COLUMNS = frozenset(
    {
        "ID",
        "Fixture",
        "Kickoff",
        "Home Team",
        "Away Team",
        "Probability (%)",
        "Outcome",
        "Bookmaker",
        "Opening Odds",
        "Closing Odds",
        "Peak Odds",
    }
)

# Paths that are known non-odds CSVs — skip during discovery.
_DISCOVERY_EXCLUDE_GLOBS = (
    "**/backtest_*.csv",
    "**/manifest*.csv",
)


def is_oddalerts_export_entry(entry: dict[str, Any]) -> bool:
    cols = set(entry.get("columns") or [])
    if not cols:
        return False
    missing = ODDALERTS_EXPECTED_COLUMNS - cols
    return not missing


def oddalerts_import_entries(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in catalog if is_oddalerts_export_entry(e) and e.get("row_count", 0) > 0]


def is_schema_clear(catalog: list[dict[str, Any]]) -> tuple[bool, str]:
    importable = oddalerts_import_entries(catalog)
    if not importable:
        if not catalog:
            return False, "no_csv_files_found"
        return False, "no_oddalerts_probability_export_files_found"
    for entry in importable[:20]:
        if not is_oddalerts_export_entry(entry):
            return False, f"schema_mismatch in {entry['relative_path']}"
    return True, f"oddalerts_probability_export_schema ({len(importable)} files)"


def import_csv_odds(
    conn: sqlite3.Connection,
    project_root: Path,
    *,
    dry_run: bool = False,
    dedupe_files_by_sha: bool = True,
) -> tuple[list[dict[str, Any]], ImportStats, list[dict[str, Any]]]:
    ensure_historical_csv_odds_table(conn)
    stats = ImportStats()
    catalog = catalog_all(project_root)
    stats.files_discovered = len(catalog)
    stats.files_cataloged = len(catalog)

    clear, reason = is_schema_clear(catalog)
    if not clear:
        stats.errors.append(f"schema_unclear: {reason}")
        return catalog, stats, []

    import_entries = oddalerts_import_entries(catalog)
    stats.files_cataloged = len(import_entries)

    fixture_index = build_fixture_index(conn)
    seen_sha: set[str] = set()
    unmatched_log: list[dict[str, Any]] = []

    insert_sql = """
        INSERT OR IGNORE INTO historical_csv_odds_imports (
            provider, source_file, source_sha256, oddalerts_row_id, internal_fixture_id,
            match_key, match_date, kickoff_utc, league, season, home_team, away_team,
            market, selection, bookmaker, opening_odds, closing_odds, peak_odds,
            opening_unix, closing_unix, peak_unix, probability_pct, implied_odds,
            match_status, home_goals, away_goals, match_outcome, competition_name,
            match_method, dedup_key, raw_json, imported_at
        ) VALUES (
            :provider, :source_file, :source_sha256, :oddalerts_row_id, :internal_fixture_id,
            :match_key, :match_date, :kickoff_utc, :league, :season, :home_team, :away_team,
            :market, :selection, :bookmaker, :opening_odds, :closing_odds, :peak_odds,
            :opening_unix, :closing_unix, :peak_unix, :probability_pct, :implied_odds,
            :match_status, :home_goals, :away_goals, :match_outcome, :competition_name,
            :match_method, :dedup_key, :raw_json, :imported_at
        )
    """

    for entry in import_entries:
        if entry.get("issues") and "empty_or_header_only" in entry["issues"]:
            stats.files_skipped_empty += 1
            continue
        sha = entry["sha256"]
        if dedupe_files_by_sha and sha in seen_sha:
            stats.files_skipped_dup_sha += 1
            continue
        seen_sha.add(sha)

        path = Path(entry["absolute_path"])
        enc, text = detect_encoding(path)
        if not text:
            stats.errors.append(f"encoding_fail: {entry['relative_path']}")
            continue

        reader = csv.DictReader(text.splitlines())
        market_type = entry["market_type"]
        source_rel = entry["relative_path"]

        for row in reader:
            stats.rows_parsed += 1
            record, match_method = row_to_records(
                row,
                source_file=source_rel,
                source_sha256=sha,
                market_type=market_type,
                fixture_index=fixture_index,
            )
            if record is None:
                stats.rows_skipped_invalid += 1
                continue

            stats.markets[market_type] += 1
            if record["internal_fixture_id"]:
                stats.rows_matched += 1
            else:
                stats.rows_unmatched += 1
                unmatched_log.append(
                    {
                        "source_file": source_rel,
                        "match_key": record["match_key"],
                        "home_team": record["home_team"],
                        "away_team": record["away_team"],
                        "kickoff": record["kickoff_utc"],
                        "market": market_type,
                        "selection": record["selection"],
                    }
                )

            if dry_run:
                continue

            before = conn.total_changes
            conn.execute(insert_sql, record)
            if conn.total_changes > before:
                stats.rows_inserted += 1
            else:
                stats.rows_skipped_duplicate += 1

    if not dry_run:
        conn.commit()

    return catalog, stats, unmatched_log


def backup_database(db_path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"football_intelligence_pre_data1b_{stamp}.db"
    dest.write_bytes(db_path.read_bytes())
    return dest
