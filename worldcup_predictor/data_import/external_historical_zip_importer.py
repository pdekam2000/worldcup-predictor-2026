"""External historical football CSV ZIP inspector and staging importer."""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import re
import shutil
import sqlite3
import time
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from worldcup_predictor.data_import.external_historical_ddl import ensure_external_historical_tables
from worldcup_predictor.intelligence.national_team._shared import normalize_team_name

logger = logging.getLogger(__name__)

PHASE = "HISTORICAL-CSV-INGEST-1"
SCHEMA_PATH = Path("config/external_historical_csv_schema.json")
PROFILE_PATH = Path("artifacts/external_historical_zip_profile.json")
IMPORT_SUMMARY_PATH = Path("artifacts/external_historical_zip_import_summary.json")

INBOX_DIR = Path("data/external_historical_csv/inbox")
EXTRACTED_DIR = Path("data/external_historical_csv/extracted")
PROCESSED_DIR = Path("data/external_historical_csv/processed")
REJECTED_DIR = Path("data/external_historical_csv/rejected")
ARCHIVE_DIR = Path("data/external_historical_csv/archive")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def load_schema_config(path: Path | None = None) -> dict[str, Any]:
    p = path or SCHEMA_PATH
    return json.loads(p.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def row_hash(source_file: str, row_number: int, row: dict[str, Any]) -> str:
    payload = {"source_file": source_file, "row_number": row_number, "row": row}
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _safe_extract_path(base: Path, member_name: str) -> Path | None:
    name = member_name.replace("\\", "/")
    if name.startswith("/") or ".." in Path(name).parts:
        return None
    dest = (base / name).resolve()
    try:
        dest.relative_to(base.resolve())
    except ValueError:
        return None
    return dest


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _league_code(league: str | None, country: str | None) -> str:
    parts = [normalize_team_name(country or ""), normalize_team_name(league or "")]
    return "_".join(p for p in parts if p) or "unknown"


def _kickoff_utc(event_date: str | None, event_hour: str | None) -> str | None:
    if not event_date:
        return None
    date_part = str(event_date).strip()
    hour_part = (str(event_hour).strip() if event_hour else "") or "00:00"
    if "T" in date_part:
        return date_part
    try:
        if len(hour_part) == 5:
            return f"{date_part}T{hour_part}:00Z"
        return f"{date_part}T{hour_part}Z"
    except Exception:
        return date_part


def _odds_mappings(cfg: dict[str, Any]) -> list[tuple[str, dict[str, str]]]:
    out: list[tuple[str, dict[str, str]]] = []
    for col, meta in (cfg.get("ft_odds_mapping") or {}).items():
        out.append((col, meta))
    for col, meta in (cfg.get("ht_odds_mapping") or {}).items():
        out.append((col, meta))
    return out


def _detect_delimiter(text: str) -> str:
    first_line = text.splitlines()[0] if text else ""
    if ";" in first_line and first_line.count(";") >= first_line.count(","):
        return ";"
    if "\t" in first_line:
        return "\t"
    return ","


def _count_csv_rows(path: Path) -> int:
    raw = path.read_text(encoding="utf-8-sig")
    delim = _detect_delimiter(raw)
    count = 0
    import io

    reader = csv.reader(io.StringIO(raw), delimiter=delim)
    next(reader, None)
    for _ in reader:
        count += 1
    return count


def _read_csv_dicts(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    raw = path.read_text(encoding="utf-8-sig")
    delim = _detect_delimiter(raw)
    import io

    reader = csv.DictReader(io.StringIO(raw), delimiter=delim)
    if not reader.fieldnames:
        return [], []
    columns = [c.strip() for c in reader.fieldnames if c]
    rows = [{k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()} for row in reader]
    return columns, rows


@dataclass
class ZipProfile:
    zip_path: str
    csv_file_count: int = 0
    total_rows: int = 0
    countries: dict[str, int] = field(default_factory=dict)
    leagues: dict[str, int] = field(default_factory=dict)
    statuses: dict[str, int] = field(default_factory=dict)
    min_event_date: str | None = None
    max_event_date: str | None = None
    duplicate_file_groups: list[list[str]] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)
    schema_columns: list[str] = field(default_factory=list)
    schema_match: bool = True
    path_traversal_blocked: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": PHASE,
            "generated_at_utc": _utc_now(),
            "zip_path": self.zip_path,
            "csv_file_count": self.csv_file_count,
            "total_rows": self.total_rows,
            "country_count": len(self.countries),
            "league_count": len(self.leagues),
            "countries": dict(sorted(self.countries.items(), key=lambda x: -x[1])[:20]),
            "leagues_top": dict(sorted(self.leagues.items(), key=lambda x: -x[1])[:20]),
            "statuses": dict(sorted(self.statuses.items(), key=lambda x: -x[1])),
            "min_event_date": self.min_event_date,
            "max_event_date": self.max_event_date,
            "duplicate_file_groups": self.duplicate_file_groups,
            "duplicate_group_count": len(self.duplicate_file_groups),
            "schema_columns": self.schema_columns,
            "schema_match": self.schema_match,
            "path_traversal_blocked": self.path_traversal_blocked,
            "files": self.files,
        }


def inspect_zip(zip_path: Path, *, cfg: dict[str, Any] | None = None) -> ZipProfile:
    cfg = cfg or load_schema_config()
    expected = cfg.get("expected_columns") or []
    profile = ZipProfile(zip_path=str(zip_path.resolve()))

    hash_to_names: dict[str, list[str]] = defaultdict(list)

    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir() or not info.filename.lower().endswith(".csv"):
                continue
            safe = _safe_extract_path(Path("."), info.filename)
            if safe is None:
                profile.path_traversal_blocked.append(info.filename)
                continue

            profile.csv_file_count += 1
            with zf.open(info, "r") as raw:
                data = raw.read()
            digest = hashlib.sha256(data).hexdigest()
            hash_to_names[digest].append(info.filename)

            import io

            text = data.decode("utf-8-sig", errors="replace")
            delim = _detect_delimiter(text)
            reader = csv.DictReader(io.StringIO(text), delimiter=delim)
            columns = [c.strip() for c in (reader.fieldnames or []) if c]
            if not profile.schema_columns:
                profile.schema_columns = columns
            profile.schema_match = profile.schema_match and columns == expected

            row_count = 0
            file_countries: Counter[str] = Counter()
            file_leagues: Counter[str] = Counter()
            file_statuses: Counter[str] = Counter()
            file_min_date: str | None = None
            file_max_date: str | None = None

            for row in reader:
                row_count += 1
                country = (row.get("countryName") or "").strip()
                league = (row.get("league") or "").strip()
                status = (row.get("status") or "").strip() or "unknown"
                event_date = (row.get("eventDate") or "").strip()
                if country:
                    file_countries[country] += 1
                    profile.countries[country] = profile.countries.get(country, 0) + 1
                if league:
                    file_leagues[league] += 1
                    profile.leagues[league] = profile.leagues.get(league, 0) + 1
                file_statuses[status] += 1
                profile.statuses[status] = profile.statuses.get(status, 0) + 1
                if event_date:
                    if file_min_date is None or event_date < file_min_date:
                        file_min_date = event_date
                    if file_max_date is None or event_date > file_max_date:
                        file_max_date = event_date
                    if profile.min_event_date is None or event_date < profile.min_event_date:
                        profile.min_event_date = event_date
                    if profile.max_event_date is None or event_date > profile.max_event_date:
                        profile.max_event_date = event_date

            profile.total_rows += row_count
            profile.files.append(
                {
                    "source_file": info.filename,
                    "file_hash": digest,
                    "rows_count": row_count,
                    "country_name": file_countries.most_common(1)[0][0] if file_countries else None,
                    "league_code": _league_code(
                        file_leagues.most_common(1)[0][0] if file_leagues else None,
                        file_countries.most_common(1)[0][0] if file_countries else None,
                    ),
                    "min_event_date": file_min_date,
                    "max_event_date": file_max_date,
                    "status_counts": dict(file_statuses),
                }
            )

    profile.duplicate_file_groups = [names for names in hash_to_names.values() if len(names) > 1]
    return profile


def extract_zip_safely(zip_path: Path, extract_dir: Path) -> tuple[list[Path], list[str]]:
    extract_dir = extract_dir.resolve()
    extract_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    blocked: list[str] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir() or not info.filename.lower().endswith(".csv"):
                continue
            dest = _safe_extract_path(extract_dir, info.filename)
            if dest is None:
                blocked.append(info.filename)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, dest.open("wb") as out:
                shutil.copyfileobj(src, out)
            extracted.append(dest)
    return extracted, blocked


def _normalize_match_row(source_file: str, row: dict[str, str], rhash: str) -> dict[str, Any]:
    home_xg = _parse_float(row.get("expectedGoalsHome"))
    away_xg = _parse_float(row.get("expectedGoalsAway"))
    home_corners = _parse_int(row.get("cornerKicksHome"))
    away_corners = _parse_int(row.get("cornerKicksAway"))
    flags: dict[str, Any] = {}
    if home_xg == 0.0:
        flags["home_xg_provider_zero"] = True
    if away_xg == 0.0:
        flags["away_xg_provider_zero"] = True
    if home_corners == 0:
        flags["home_corners_provider_zero"] = True
    if away_corners == 0:
        flags["away_corners_provider_zero"] = True

    raw = dict(row)
    if flags:
        raw["_data_quality_flags"] = flags

    event_date = (row.get("eventDate") or "").strip() or None
    event_hour = (row.get("eventHour") or "").strip() or None

    return {
        "row_hash": rhash,
        "source_file": source_file,
        "sport": (row.get("sport") or "").strip() or None,
        "league": (row.get("league") or "").strip() or None,
        "country_name": (row.get("countryName") or "").strip() or None,
        "home_team": (row.get("homeTeam") or "").strip() or None,
        "away_team": (row.get("awayTeam") or "").strip() or None,
        "round": (row.get("round") or "").strip() or None,
        "status": (row.get("status") or "").strip() or None,
        "event_date": event_date,
        "event_hour": event_hour,
        "kickoff_utc": _kickoff_utc(event_date, event_hour),
        "home_ht_goals": _parse_int(row.get("goalsHomeHalfTime")),
        "away_ht_goals": _parse_int(row.get("goalsAwayHalfTime")),
        "home_ft_goals": _parse_int(row.get("goalsHomeFullTime")),
        "away_ft_goals": _parse_int(row.get("goalsAwayFullTime")),
        "home_xg": home_xg,
        "away_xg": away_xg,
        "home_penalties": _parse_int(row.get("penaltiesHome")),
        "away_penalties": _parse_int(row.get("penaltiesAway")),
        "home_corners": home_corners,
        "away_corners": away_corners,
        "raw_row_json": json.dumps(raw, ensure_ascii=False),
        "created_at": _utc_now(),
    }


def _normalize_odds_rows(
    source_file: str,
    row: dict[str, str],
    *,
    cfg: dict[str, Any],
    base_rhash: str,
) -> list[dict[str, Any]]:
    created = _utc_now()
    raw_json = json.dumps(row, ensure_ascii=False)
    event_date = (row.get("eventDate") or "").strip() or None
    event_hour = (row.get("eventHour") or "").strip() or None
    league = (row.get("league") or "").strip() or None
    country = (row.get("countryName") or "").strip() or None
    home = (row.get("homeTeam") or "").strip() or None
    away = (row.get("awayTeam") or "").strip() or None

    out: list[dict[str, Any]] = []
    for col, meta in _odds_mappings(cfg):
        odds = _parse_float(row.get(col))
        if odds is None or odds <= 1.0:
            continue
        implied = 1.0 / odds
        ohash = hashlib.sha256(f"{base_rhash}:{col}:{odds}".encode()).hexdigest()
        out.append(
            {
                "row_hash": ohash,
                "source_file": source_file,
                "league": league,
                "country_name": country,
                "home_team": home,
                "away_team": away,
                "event_date": event_date,
                "event_hour": event_hour,
                "market": meta["market"],
                "outcome": meta["outcome"],
                "odds": odds,
                "implied_probability": implied,
                "period": meta["period"],
                "raw_row_json": raw_json,
                "created_at": created,
            }
        )
    return out


@dataclass
class ImportBatch:
    zip_path: str
    dry_run: bool
    stage_only: bool
    files_total: int = 0
    files_staged: int = 0
    files_skipped_duplicate: int = 0
    files_rejected: int = 0
    path_traversal_blocked: list[str] = field(default_factory=list)
    raw_rows_staged: int = 0
    raw_rows_skipped_duplicate: int = 0
    match_rows_staged: int = 0
    match_rows_skipped_duplicate: int = 0
    odds_rows_staged: int = 0
    odds_rows_skipped_duplicate: int = 0
    odds_rows_invalid_skipped: int = 0
    errors: list[str] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": PHASE,
            "generated_at_utc": _utc_now(),
            "zip_path": self.zip_path,
            "dry_run": self.dry_run,
            "stage_only": self.stage_only,
            "promoted_to_production": False,
            "promoted_to_odds_snapshots": False,
            "files_total": self.files_total,
            "files_staged": self.files_staged,
            "files_skipped_duplicate": self.files_skipped_duplicate,
            "files_rejected": self.files_rejected,
            "path_traversal_blocked": self.path_traversal_blocked,
            "raw_rows_staged": self.raw_rows_staged,
            "raw_rows_skipped_duplicate": self.raw_rows_skipped_duplicate,
            "match_rows_staged": self.match_rows_staged,
            "match_rows_skipped_duplicate": self.match_rows_skipped_duplicate,
            "odds_rows_staged": self.odds_rows_staged,
            "odds_rows_skipped_duplicate": self.odds_rows_skipped_duplicate,
            "odds_rows_invalid_skipped": self.odds_rows_invalid_skipped,
            "errors": self.errors,
            "files": self.files,
        }


def _execute_with_backoff(conn: sqlite3.Connection, sql: str, params: tuple | list, *, retries: int = 5) -> None:
    for attempt in range(retries):
        try:
            conn.execute(sql, params)
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == retries - 1:
                raise
            time.sleep(0.2 * (attempt + 1))


def import_zip(
    conn: sqlite3.Connection,
    zip_path: Path,
    *,
    dry_run: bool = True,
    stage_only: bool = False,
    cfg: dict[str, Any] | None = None,
) -> ImportBatch:
    cfg = cfg or load_schema_config()
    expected = cfg.get("expected_columns") or []
    batch = ImportBatch(
        zip_path=str(zip_path.resolve()),
        dry_run=dry_run,
        stage_only=stage_only or (not dry_run),
    )

    if not zip_path.is_file():
        batch.errors.append(f"ZIP not found: {zip_path}")
        return batch

    ensure_external_historical_tables(conn)
    extract_root = (EXTRACTED_DIR / zip_path.stem).resolve()
    csv_paths, blocked = extract_zip_safely(zip_path, extract_root)
    batch.path_traversal_blocked = blocked
    batch.files_total = len(csv_paths)

    seen_hashes: set[str] = set()
    for path in sorted(csv_paths):
        rel_name = str(path.resolve().relative_to(extract_root)).replace("\\", "/")
        digest = file_sha256(path)
        entry: dict[str, Any] = {"source_file": rel_name, "file_hash": digest, "status": "pending"}

        if digest in seen_hashes:
            entry["status"] = "skipped_duplicate_in_zip"
            batch.files_skipped_duplicate += 1
            batch.files.append(entry)
            if not dry_run:
                shutil.move(str(path), str(REJECTED_DIR / path.name))
            continue
        seen_hashes.add(digest)

        existing = conn.execute(
            "SELECT id FROM external_historical_csv_files WHERE file_hash = ?",
            (digest,),
        ).fetchone()
        if existing:
            entry["status"] = "skipped_duplicate_db"
            batch.files_skipped_duplicate += 1
            batch.files.append(entry)
            continue

        columns, rows = _read_csv_dicts(path)
        if columns != expected:
            entry["status"] = "rejected_schema_mismatch"
            entry["error"] = f"columns={len(columns)} expected={len(expected)}"
            batch.files_rejected += 1
            batch.files.append(entry)
            if not dry_run:
                REJECTED_DIR.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(REJECTED_DIR / path.name))
            continue

        countries = Counter((r.get("countryName") or "").strip() for r in rows if (r.get("countryName") or "").strip())
        leagues = Counter((r.get("league") or "").strip() for r in rows if (r.get("league") or "").strip())
        dates = sorted((r.get("eventDate") or "").strip() for r in rows if (r.get("eventDate") or "").strip())
        min_date = dates[0] if dates else None
        max_date = dates[-1] if dates else None
        top_country = countries.most_common(1)[0][0] if countries else None
        top_league = leagues.most_common(1)[0][0] if leagues else None

        if dry_run:
            raw_n = len(rows)
            match_n = raw_n
            odds_n = sum(len(_normalize_odds_rows(rel_name, r, cfg=cfg, base_rhash=row_hash(rel_name, i, r))) for i, r in enumerate(rows, 1))
            entry.update({"status": "dry_run", "rows_count": raw_n, "match_rows": match_n, "odds_rows": odds_n})
            batch.raw_rows_staged += raw_n
            batch.match_rows_staged += match_n
            batch.odds_rows_staged += odds_n
            batch.files_staged += 1
            batch.files.append(entry)
            continue

        try:
            conn.execute("BEGIN IMMEDIATE")
            imported_at = _utc_now()
            _execute_with_backoff(
                conn,
                """
                INSERT INTO external_historical_csv_files (
                    source_zip, source_file, file_hash, rows_count, country_name,
                    league_code, min_event_date, max_event_date, status, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    zip_path.name,
                    rel_name,
                    digest,
                    len(rows),
                    top_country,
                    _league_code(top_league, top_country),
                    min_date,
                    max_date,
                    "staged",
                    imported_at,
                ),
            )

            raw_ins = match_ins = odds_ins = 0
            raw_dup = match_dup = odds_dup = 0
            invalid_odds = 0

            for i, row in enumerate(rows, start=1):
                rhash = row_hash(rel_name, i, row)
                try:
                    _execute_with_backoff(
                        conn,
                        """
                        INSERT INTO external_historical_csv_raw_rows (
                            file_hash, row_hash, source_file, row_number, raw_row_json, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (digest, rhash, rel_name, i, json.dumps(row, ensure_ascii=False), imported_at),
                    )
                    raw_ins += 1
                except sqlite3.IntegrityError:
                    raw_dup += 1

                match = _normalize_match_row(rel_name, row, rhash)
                try:
                    _execute_with_backoff(
                        conn,
                        """
                        INSERT INTO external_match_history_staging (
                            row_hash, source_file, sport, league, country_name, home_team, away_team,
                            round, status, event_date, event_hour, kickoff_utc,
                            home_ht_goals, away_ht_goals, home_ft_goals, away_ft_goals,
                            home_xg, away_xg, home_penalties, away_penalties, home_corners, away_corners,
                            raw_row_json, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            match["row_hash"],
                            match["source_file"],
                            match["sport"],
                            match["league"],
                            match["country_name"],
                            match["home_team"],
                            match["away_team"],
                            match["round"],
                            match["status"],
                            match["event_date"],
                            match["event_hour"],
                            match["kickoff_utc"],
                            match["home_ht_goals"],
                            match["away_ht_goals"],
                            match["home_ft_goals"],
                            match["away_ft_goals"],
                            match["home_xg"],
                            match["away_xg"],
                            match["home_penalties"],
                            match["away_penalties"],
                            match["home_corners"],
                            match["away_corners"],
                            match["raw_row_json"],
                            match["created_at"],
                        ),
                    )
                    match_ins += 1
                except sqlite3.IntegrityError:
                    match_dup += 1

                odds_rows = _normalize_odds_rows(rel_name, row, cfg=cfg, base_rhash=rhash)
                for odds_col, _meta in _odds_mappings(cfg):
                    val = _parse_float(row.get(odds_col))
                    if val is not None and val <= 1.0:
                        invalid_odds += 1
                for odds_row in odds_rows:
                    try:
                        _execute_with_backoff(
                            conn,
                            """
                            INSERT INTO external_match_odds_staging (
                                row_hash, source_file, league, country_name, home_team, away_team,
                                event_date, event_hour, market, outcome, odds, implied_probability,
                                period, raw_row_json, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                odds_row["row_hash"],
                                odds_row["source_file"],
                                odds_row["league"],
                                odds_row["country_name"],
                                odds_row["home_team"],
                                odds_row["away_team"],
                                odds_row["event_date"],
                                odds_row["event_hour"],
                                odds_row["market"],
                                odds_row["outcome"],
                                odds_row["odds"],
                                odds_row["implied_probability"],
                                odds_row["period"],
                                odds_row["raw_row_json"],
                                odds_row["created_at"],
                            ),
                        )
                        odds_ins += 1
                    except sqlite3.IntegrityError:
                        odds_dup += 1

            conn.commit()
            PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(PROCESSED_DIR / path.name))
            entry.update(
                {
                    "status": "staged",
                    "rows_count": len(rows),
                    "raw_rows_inserted": raw_ins,
                    "match_rows_inserted": match_ins,
                    "odds_rows_inserted": odds_ins,
                }
            )
            batch.files_staged += 1
            batch.raw_rows_staged += raw_ins
            batch.raw_rows_skipped_duplicate += raw_dup
            batch.match_rows_staged += match_ins
            batch.match_rows_skipped_duplicate += match_dup
            batch.odds_rows_staged += odds_ins
            batch.odds_rows_skipped_duplicate += odds_dup
            batch.odds_rows_invalid_skipped += invalid_odds
        except Exception as exc:
            conn.rollback()
            entry["status"] = "failed"
            entry["error"] = str(exc)[:500]
            batch.errors.append(f"{rel_name}: {exc}")
            batch.files_rejected += 1
            REJECTED_DIR.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(path), str(REJECTED_DIR / path.name))
            except OSError:
                pass

        batch.files.append(entry)

    if not dry_run:
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        archive_dest = ARCHIVE_DIR / zip_path.name
        if not archive_dest.exists():
            shutil.copy2(str(zip_path), str(archive_dest))

    return batch


def write_profile(profile: ZipProfile, path: Path | None = None) -> Path:
    p = path or PROFILE_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(profile.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def write_import_summary(batch: ImportBatch, path: Path | None = None) -> Path:
    p = path or IMPORT_SUMMARY_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(batch.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return p
