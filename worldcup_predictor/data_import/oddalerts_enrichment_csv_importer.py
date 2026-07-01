"""PHASE ODDALERTS-CSV-PLAYER-REF-1 — OddAlerts enrichment CSV import (not odds)."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import sqlite3
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Literal

from worldcup_predictor.data_import.oddalerts_enrichment_ddl import ensure_oddalerts_enrichment_tables
from worldcup_predictor.data_import.uefa_result_matching import normalize_team_name, team_similarity

PHASE = "ODDALERTS-CSV-PLAYER-REF-1"

CsvType = Literal["ODDS_CSV", "PLAYER_STATS_CSV", "REFEREE_CARDS_CSV", "UNKNOWN_CSV"]
CrosswalkStatus = Literal[
    "MATCHED_HIGH_CONFIDENCE",
    "MATCHED_LOW_CONFIDENCE",
    "AMBIGUOUS",
    "NO_MATCH",
]

INBOX_DIR = Path("data/oddalerts_csv/inbox")
PROCESSED_DIR = Path("data/oddalerts_csv/processed")
REJECTED_DIR = Path("data/oddalerts_csv/rejected")
ARCHIVE_DIR = Path("data/oddalerts_csv/raw_archive")
SCHEMA_PROFILE_PATH = Path("artifacts/oddalerts_csv_schema_profile.json")
IMPORT_SUMMARY_PATH = Path("artifacts/oddalerts_enrichment_csv_import_summary.json")
CROSSWALK_PATH = Path("artifacts/oddalerts_enrichment_fixture_crosswalk.json")

MIN_HIGH_CONFIDENCE = 0.90
MIN_LOW_CONFIDENCE = 0.75

TEAM_ALIASES: dict[str, str] = {
    "cotedivoire": "ivorycoast",
    "coted'ivoire": "ivorycoast",
    "unitedstates": "usa",
    "bosniaandherzegovina": "bosnia",
    "congodr": "congo",
    "democraticrepublicofthecongo": "congo",
    "korea republic": "southkorea",
    "republicofireland": "ireland",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _norm_col(name: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name or "").lower())


def _row_hash(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace("%", "")
    if not text or text.lower() in {"-", "na", "n/a", "null", "none"}:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    f = _to_float(value)
    return int(f) if f is not None else None


def _to_bool_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return 1
    if text in {"0", "false", "no", "n"}:
        return 0
    return None


def _normalize_percent(value: Any) -> float | None:
    f = _to_float(value)
    if f is None:
        return None
    if f > 1.0 and f <= 100.0:
        return round(f / 100.0, 6)
    return round(f, 6)


def _read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        columns = list(reader.fieldnames or [])
        rows = [dict(r) for r in reader]
    return columns, rows


def detect_csv_type(columns: list[str]) -> CsvType:
    norm = {_norm_col(c) for c in columns}
    colset = set(columns)
    lower_map = {_norm_col(c): c for c in columns}

    player_keys = {"player", "fullname", "team", "fixture", "goals", "shots", "rating"}
    if player_keys.issubset(norm):
        return "PLAYER_STATS_CSV"

    ref_keys = {
        "name",
        "fixturename",
        "yellowcardsavg",
        "redcardsavg",
        "bothteamsbookedper",
        "homecardsavg",
        "awaycardsavg",
    }
    if ref_keys.issubset(norm):
        return "REFEREE_CARDS_CSV"

    odds_hints = {"probability", "impliedodds", "closingodds", "bookmaker", "outcome"}
    if odds_hints.intersection(norm):
        return "ODDS_CSV"

    if "fixture" in lower_map and "hometeam" in norm and "probability" in norm:
        return "ODDS_CSV"

    return "UNKNOWN_CSV"


def profile_csv_file(path: Path) -> dict[str, Any]:
    columns, rows = _read_csv_rows(path)
    csv_type = detect_csv_type(columns)
    wc_rows = 0
    for row in rows:
        blob = " ".join(str(v) for v in row.values()).lower()
        if "world cup" in blob or "worldcup" in blob:
            wc_rows += 1
    return {
        "file": str(path),
        "filename": path.name,
        "csv_type": csv_type,
        "row_count": len(rows),
        "column_count": len(columns),
        "columns": columns,
        "world_cup_row_hint_count": wc_rows,
        "sample_row": rows[0] if rows else None,
    }


def inspect_csv_paths(paths: list[Path]) -> dict[str, Any]:
    profiles = [profile_csv_file(p) for p in paths]
    payload = {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "files_scanned": len(profiles),
        "profiles": profiles,
    }
    SCHEMA_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_PROFILE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def _alias_team(name: str) -> str:
    base = normalize_team_name(name)
    return TEAM_ALIASES.get(base, base)


def parse_fixture_pair(text: str | None) -> tuple[str, str] | None:
    if not text:
        return None
    raw = str(text).strip()
    for sep in (" vs ", " v ", " - "):
        if sep in raw.lower():
            idx = raw.lower().index(sep)
            home = raw[:idx].strip()
            away = raw[idx + len(sep) :].strip()
            if home and away:
                return home, away
    return None


def _parse_oddalerts_date(text: str | None, kickoff_unix: int | None = None) -> str | None:
    if kickoff_unix:
        try:
            return datetime.fromtimestamp(int(kickoff_unix), tz=timezone.utc).strftime("%Y-%m-%d")
        except (TypeError, ValueError, OSError):
            pass
    if not text:
        return None
    raw = str(text).strip()
    m = re.search(r"([A-Za-z]{3})\s+(\d{1,2})", raw)
    if m:
        month_str, day = m.group(1), int(m.group(2))
        year = datetime.now(timezone.utc).year
        try:
            dt = datetime.strptime(f"{day} {month_str} {year}", "%d %b %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    if re.match(r"\d{4}-\d{2}-\d{2}", raw[:10]):
        return raw[:10]
    return None


def normalize_player_row(row: dict[str, str], *, source_file: str) -> tuple[dict[str, Any] | None, str | None]:
    player = (row.get("player") or row.get("full_name") or "").strip()
    team = (row.get("team") or "").strip()
    fixture = (row.get("fixture") or "").strip()
    if not player or not team or not fixture:
        return None, "missing_player_team_or_fixture"
    payload = {
        "player": player,
        "full_name": (row.get("full_name") or player).strip(),
        "nationality": (row.get("nationality") or "").strip() or None,
        "age": _to_float(row.get("age")),
        "position": (row.get("position") or "").strip() or None,
        "team": team,
        "fixture_name": fixture,
        "fixture_date_text": (row.get("date") or "").strip() or None,
        "kickoff_unix": _to_int(row.get("kickoff_unix")),
        "country": (row.get("country") or "").strip() or None,
        "competition_name": (row.get("competition_name") or "").strip() or None,
        "competition_type": (row.get("competition_type") or "").strip() or None,
        "apps": _to_float(row.get("apps")),
        "starts": _to_float(row.get("starts")),
        "mins": _to_float(row.get("mins")),
        "goals": _to_float(row.get("goals")),
        "goals_avg": _to_float(row.get("goals_avg")),
        "assists": _to_float(row.get("assists")),
        "shots": _to_float(row.get("shots")),
        "shots_ot": _to_float(row.get("shots_ot")),
        "key_passes": _to_float(row.get("key_passes")),
        "passes": _to_float(row.get("passes")),
        "pass_accuracy": _normalize_percent(row.get("pass_accuracy")),
        "tackles": _to_float(row.get("tackles")),
        "interceptions": _to_float(row.get("interceptions")),
        "saves": _to_float(row.get("saves")),
        "clean_sheets": _to_float(row.get("clean_sheets")),
        "yellow_cards": _to_float(row.get("yellow_cards")),
        "red_cards": _to_float(row.get("red_cards")),
        "pens_scored": _to_float(row.get("pens_scored")),
        "rating": _to_float(row.get("rating")),
        "is_captain": _to_bool_int(row.get("is_captain")),
        "is_injured": _to_bool_int(row.get("is_injured")),
        "source_file": source_file,
    }
    payload["row_hash"] = _row_hash(payload)
    return payload, None


def normalize_referee_row(row: dict[str, str], *, source_file: str) -> tuple[dict[str, Any] | None, str | None]:
    referee = (row.get("name") or "").strip()
    fixture = (row.get("fixture_name") or "").strip()
    if not referee or not fixture:
        return None, "missing_referee_or_fixture"
    payload = {
        "referee_name": referee,
        "fixture_name": fixture,
        "fixture_date_text": (row.get("date") or "").strip() or None,
        "country": (row.get("country") or "").strip() or None,
        "competition_type": (row.get("competition_type") or "").strip() or None,
        "label": (row.get("label") or "").strip() or None,
        "recorded": (row.get("recorded") or "").strip() or None,
        "yellow_cards": _to_float(row.get("yellow_cards")),
        "red_cards": _to_float(row.get("red_cards")),
        "yellow_cards_avg": _to_float(row.get("yellow_cards_avg")),
        "red_cards_avg": _to_float(row.get("red_cards_avg")),
        "cards_1h": _to_float(row.get("cards_1h")),
        "cards_2h": _to_float(row.get("cards_2h")),
        "cards_1h_avg": _to_float(row.get("cards_1h_avg")),
        "cards_2h_avg": _to_float(row.get("cards_2h_avg")),
        "both_teams_booked_per": _normalize_percent(row.get("both_teams_booked_per")),
        "home_cards_avg": _to_float(row.get("home_cards_avg")),
        "away_cards_avg": _to_float(row.get("away_cards_avg")),
        "o05_yellow_cards_per": _normalize_percent(row.get("o05_yellow_cards_per")),
        "o15_yellow_cards_per": _normalize_percent(row.get("o15_yellow_cards_per")),
        "o25_yellow_cards_per": _normalize_percent(row.get("o25_yellow_cards_per")),
        "o35_yellow_cards_per": _normalize_percent(row.get("o35_yellow_cards_per")),
        "o45_yellow_cards_per": _normalize_percent(row.get("o45_yellow_cards_per")),
        "o55_yellow_cards_per": _normalize_percent(row.get("o55_yellow_cards_per")),
        "source_file": source_file,
    }
    payload["row_hash"] = _row_hash(payload)
    return payload, None


@dataclass
class ImportFileResult:
    filename: str
    csv_type: CsvType
    imported: int = 0
    skipped_duplicate: int = 0
    rejected: int = 0
    rejection_reasons: dict[str, int] = field(default_factory=dict)
    status: str = "ok"
    error: str | None = None


@dataclass
class ImportBatchResult:
    phase: str = PHASE
    dry_run: bool = False
    files: list[ImportFileResult] = field(default_factory=list)
    player_rows_imported: int = 0
    referee_rows_imported: int = 0
    odds_files_rejected: int = 0
    unknown_files_rejected: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "dry_run": self.dry_run,
            "generated_at_utc": _utc_now(),
            "player_rows_imported": self.player_rows_imported,
            "referee_rows_imported": self.referee_rows_imported,
            "odds_files_rejected": self.odds_files_rejected,
            "unknown_files_rejected": self.unknown_files_rejected,
            "files": [f.__dict__ for f in self.files],
        }


def _insert_player_rows(conn: sqlite3.Connection, raw: dict[str, Any], norm: dict[str, Any]) -> bool:
    try:
        conn.execute(
            """
            INSERT INTO oddalerts_player_stats_raw (source_file, row_hash, imported_at, raw_row_json)
            VALUES (?, ?, ?, ?)
            """,
            (norm["source_file"], norm["row_hash"], _utc_now(), json.dumps(raw, ensure_ascii=False)),
        )
        conn.execute(
            """
            INSERT INTO oddalerts_player_stats_normalized (
                row_hash, player, full_name, nationality, age, position, team, fixture_name,
                fixture_date_text, kickoff_unix, country, competition_name, competition_type,
                apps, starts, mins, goals, goals_avg, assists, shots, shots_ot, key_passes,
                passes, pass_accuracy, tackles, interceptions, saves, clean_sheets,
                yellow_cards, red_cards, pens_scored, rating, is_captain, is_injured,
                source_file, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                norm["row_hash"],
                norm["player"],
                norm["full_name"],
                norm["nationality"],
                norm["age"],
                norm["position"],
                norm["team"],
                norm["fixture_name"],
                norm["fixture_date_text"],
                norm["kickoff_unix"],
                norm["country"],
                norm["competition_name"],
                norm["competition_type"],
                norm["apps"],
                norm["starts"],
                norm["mins"],
                norm["goals"],
                norm["goals_avg"],
                norm["assists"],
                norm["shots"],
                norm["shots_ot"],
                norm["key_passes"],
                norm["passes"],
                norm["pass_accuracy"],
                norm["tackles"],
                norm["interceptions"],
                norm["saves"],
                norm["clean_sheets"],
                norm["yellow_cards"],
                norm["red_cards"],
                norm["pens_scored"],
                norm["rating"],
                norm["is_captain"],
                norm["is_injured"],
                norm["source_file"],
                _utc_now(),
            ),
        )
        return True
    except sqlite3.IntegrityError:
        return False


def _insert_referee_rows(conn: sqlite3.Connection, raw: dict[str, str], norm: dict[str, Any]) -> bool:
    try:
        conn.execute(
            """
            INSERT INTO oddalerts_referee_cards_raw (source_file, row_hash, imported_at, raw_row_json)
            VALUES (?, ?, ?, ?)
            """,
            (norm["source_file"], norm["row_hash"], _utc_now(), json.dumps(raw, ensure_ascii=False)),
        )
        conn.execute(
            """
            INSERT INTO oddalerts_referee_cards_normalized (
                row_hash, referee_name, fixture_name, fixture_date_text, country, competition_type,
                label, recorded, yellow_cards, red_cards, yellow_cards_avg, red_cards_avg,
                cards_1h, cards_2h, cards_1h_avg, cards_2h_avg, both_teams_booked_per,
                home_cards_avg, away_cards_avg, o05_yellow_cards_per, o15_yellow_cards_per,
                o25_yellow_cards_per, o35_yellow_cards_per, o45_yellow_cards_per,
                o55_yellow_cards_per, source_file, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                norm["row_hash"],
                norm["referee_name"],
                norm["fixture_name"],
                norm["fixture_date_text"],
                norm["country"],
                norm["competition_type"],
                norm["label"],
                norm["recorded"],
                norm["yellow_cards"],
                norm["red_cards"],
                norm["yellow_cards_avg"],
                norm["red_cards_avg"],
                norm["cards_1h"],
                norm["cards_2h"],
                norm["cards_1h_avg"],
                norm["cards_2h_avg"],
                norm["both_teams_booked_per"],
                norm["home_cards_avg"],
                norm["away_cards_avg"],
                norm["o05_yellow_cards_per"],
                norm["o15_yellow_cards_per"],
                norm["o25_yellow_cards_per"],
                norm["o35_yellow_cards_per"],
                norm["o45_yellow_cards_per"],
                norm["o55_yellow_cards_per"],
                norm["source_file"],
                _utc_now(),
            ),
        )
        return True
    except sqlite3.IntegrityError:
        return False


def import_csv_file(
    conn: sqlite3.Connection,
    path: Path,
    *,
    dry_run: bool = False,
) -> ImportFileResult:
    columns, rows = _read_csv_rows(path)
    csv_type = detect_csv_type(columns)
    result = ImportFileResult(filename=path.name, csv_type=csv_type)

    if csv_type == "ODDS_CSV":
        result.status = "rejected_odds_not_enrichment"
        return result
    if csv_type == "UNKNOWN_CSV":
        result.status = "rejected_unknown"
        return result

    for raw in rows:
        if csv_type == "PLAYER_STATS_CSV":
            norm, reason = normalize_player_row(raw, source_file=path.name)
        else:
            norm, reason = normalize_referee_row(raw, source_file=path.name)

        if norm is None:
            result.rejected += 1
            result.rejection_reasons[reason or "invalid"] = result.rejection_reasons.get(reason or "invalid", 0) + 1
            continue

        if dry_run:
            result.imported += 1
            continue

        if csv_type == "PLAYER_STATS_CSV":
            ok = _insert_player_rows(conn, raw, norm)
        else:
            ok = _insert_referee_rows(conn, raw, norm)

        if ok:
            result.imported += 1
        else:
            result.skipped_duplicate += 1

    return result


def _score_fixture_candidate(
    *,
    oa_home: str,
    oa_away: str,
    db_home: str,
    db_away: str,
    oa_date: str | None,
    db_kickoff: str | None,
) -> float:
    h = team_similarity(_alias_team(oa_home), _alias_team(db_home))
    a = team_similarity(_alias_team(oa_away), _alias_team(db_away))
    team_score = (h + a) / 2.0
    date_score = 0.5
    if oa_date and db_kickoff:
        if oa_date == str(db_kickoff)[:10]:
            date_score = 1.0
        elif oa_date[:7] == str(db_kickoff)[:7]:
            date_score = 0.7
    return round((team_score * 0.85) + (date_score * 0.15), 4)


def build_enrichment_fixture_crosswalk(
    conn: sqlite3.Connection,
    *,
    competition_key: str = "world_cup_2026",
    year_prefix: str = "2026",
    persist_links: bool = True,
) -> dict[str, Any]:
    ensure_oddalerts_enrichment_tables(conn)
    db_fixtures = conn.execute(
        """
        SELECT fixture_id, home_team, away_team, kickoff_utc, competition_key
        FROM fixtures
        WHERE competition_key = ? AND kickoff_utc LIKE ?
        ORDER BY kickoff_utc
        """,
        (competition_key, f"{year_prefix}%"),
    ).fetchall()

    fixture_names: dict[str, set[str]] = defaultdict(set)
    for row in conn.execute(
        "SELECT DISTINCT fixture_name, fixture_date_text, kickoff_unix FROM oddalerts_player_stats_normalized"
    ).fetchall():
        fixture_names[str(row["fixture_name"])].add("player")
    for row in conn.execute(
        "SELECT DISTINCT fixture_name, fixture_date_text FROM oddalerts_referee_cards_normalized"
    ).fetchall():
        fixture_names[str(row["fixture_name"])].add("referee")

    crosswalk_rows: list[dict[str, Any]] = []
    status_counts: dict[str, int] = defaultdict(int)

    for fixture_name in sorted(fixture_names):
        pair = parse_fixture_pair(fixture_name)
        if not pair:
            crosswalk_rows.append(
                {
                    "fixture_name_source": fixture_name,
                    "status": "NO_MATCH",
                    "confidence": None,
                    "fixture_id": None,
                    "rejection_reason": "unparseable_fixture_name",
                }
            )
            status_counts["NO_MATCH"] += 1
            continue

        oa_home, oa_away = pair
        sample = conn.execute(
            """
            SELECT fixture_date_text, kickoff_unix FROM oddalerts_player_stats_normalized
            WHERE fixture_name = ? LIMIT 1
            """,
            (fixture_name,),
        ).fetchone()
        if not sample:
            sample = conn.execute(
                """
                SELECT fixture_date_text, NULL AS kickoff_unix FROM oddalerts_referee_cards_normalized
                WHERE fixture_name = ? LIMIT 1
                """,
                (fixture_name,),
            ).fetchone()
        oa_date = _parse_oddalerts_date(
            sample["fixture_date_text"] if sample else None,
            int(sample["kickoff_unix"]) if sample and sample["kickoff_unix"] else None,
        )

        candidates: list[tuple[float, int, str, str]] = []
        for fx in db_fixtures:
            score = _score_fixture_candidate(
                oa_home=oa_home,
                oa_away=oa_away,
                db_home=str(fx["home_team"]),
                db_away=str(fx["away_team"]),
                oa_date=oa_date,
                db_kickoff=str(fx["kickoff_utc"]),
            )
            if score >= MIN_LOW_CONFIDENCE:
                candidates.append((score, int(fx["fixture_id"]), str(fx["home_team"]), str(fx["away_team"])))

        candidates.sort(key=lambda x: x[0], reverse=True)
        top = candidates[0] if candidates else None
        second = candidates[1] if len(candidates) > 1 else None

        if not top:
            status: CrosswalkStatus = "NO_MATCH"
            confidence = None
            fixture_id = None
            reason = "no_db_candidate"
        elif second and (top[0] - second[0]) < 0.02:
            status = "AMBIGUOUS"
            confidence = top[0]
            fixture_id = None
            reason = f"top_two_close:{top[0]} vs {second[0]}"
        elif top[0] >= MIN_HIGH_CONFIDENCE:
            status = "MATCHED_HIGH_CONFIDENCE"
            confidence = top[0]
            fixture_id = top[1]
            reason = None
        elif top[0] >= MIN_LOW_CONFIDENCE:
            status = "MATCHED_LOW_CONFIDENCE"
            confidence = top[0]
            fixture_id = None
            reason = "below_high_confidence_threshold"
        else:
            status = "NO_MATCH"
            confidence = top[0]
            fixture_id = None
            reason = "score_too_low"

        status_counts[status] += 1
        crosswalk_rows.append(
            {
                "fixture_name_source": fixture_name,
                "parsed_home": oa_home,
                "parsed_away": oa_away,
                "parsed_date": oa_date,
                "status": status,
                "confidence": confidence,
                "fixture_id": fixture_id,
                "matched_db_teams": f"{top[2]} vs {top[3]}" if top and fixture_id else None,
                "rejection_reason": reason,
                "sources": sorted(fixture_names[fixture_name]),
            }
        )

        if persist_links:
            _persist_crosswalk_links(conn, fixture_name, status, confidence, fixture_id, reason)

    summary = {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "competition_key": competition_key,
        "unique_fixture_names": len(fixture_names),
        "status_counts": dict(status_counts),
        "rows": crosswalk_rows,
    }
    CROSSWALK_PATH.parent.mkdir(parents=True, exist_ok=True)
    CROSSWALK_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def _persist_crosswalk_links(
    conn: sqlite3.Connection,
    fixture_name: str,
    status: str,
    confidence: float | None,
    fixture_id: int | None,
    reason: str | None,
) -> None:
    for enrichment_type, table, col in (
        ("player_stats", "oddalerts_player_stats_normalized", "fixture_name"),
        ("referee_cards", "oddalerts_referee_cards_normalized", "fixture_name"),
    ):
        rows = conn.execute(
            f"SELECT row_hash FROM {table} WHERE {col} = ?",
            (fixture_name,),
        ).fetchall()
        for row in rows:
            conn.execute(
                """
                INSERT OR REPLACE INTO oddalerts_enrichment_fixture_links (
                    enrichment_type, row_hash, fixture_id, fixture_name_source,
                    match_status, confidence, rejection_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    enrichment_type,
                    row["row_hash"],
                    fixture_id if status == "MATCHED_HIGH_CONFIDENCE" else None,
                    fixture_name,
                    status,
                    confidence,
                    reason,
                    _utc_now(),
                ),
            )


def load_fixture_enrichment(conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any]:
    """Owner report helper — high-confidence enrichment only."""
    ref = conn.execute(
        """
        SELECT r.referee_name, r.yellow_cards_avg, r.both_teams_booked_per, r.home_cards_avg, r.away_cards_avg
        FROM oddalerts_enrichment_fixture_links l
        JOIN oddalerts_referee_cards_normalized r ON r.row_hash = l.row_hash
        WHERE l.fixture_id = ? AND l.enrichment_type = 'referee_cards'
          AND l.match_status = 'MATCHED_HIGH_CONFIDENCE'
        LIMIT 1
        """,
        (int(fixture_id),),
    ).fetchone()

    players = conn.execute(
        """
        SELECT p.player, p.team, p.position, p.goals, p.shots, p.shots_ot, p.rating,
               p.is_captain, p.is_injured
        FROM oddalerts_enrichment_fixture_links l
        JOIN oddalerts_player_stats_normalized p ON p.row_hash = l.row_hash
        WHERE l.fixture_id = ? AND l.enrichment_type = 'player_stats'
          AND l.match_status = 'MATCHED_HIGH_CONFIDENCE'
        """,
        (int(fixture_id),),
    ).fetchall()

    player_rows = [dict(p) for p in players]

    def _top(metric: str, n: int = 5) -> list[dict[str, Any]]:
        ranked = sorted(
            player_rows,
            key=lambda x: float(x.get(metric) or 0),
            reverse=True,
        )
        return [
            {
                "player": r["player"],
                "team": r["team"],
                "value": r.get(metric),
                "rating": r.get("rating"),
                "is_captain": bool(r.get("is_captain")),
                "is_injured": bool(r.get("is_injured")),
            }
            for r in ranked[:n]
            if float(r.get(metric) or 0) > 0 or metric == "rating"
        ]

    return {
        "referee": dict(ref) if ref else None,
        "top_goals": _top("goals"),
        "top_shots": _top("shots"),
        "top_shots_ot": _top("shots_ot"),
        "top_rating": _top("rating"),
        "player_count": len(player_rows),
    }


def import_enrichment_csv_batch(
    conn: sqlite3.Connection,
    *,
    input_dir: Path | None = None,
    dry_run: bool = False,
) -> ImportBatchResult:
    ensure_oddalerts_enrichment_tables(conn)
    inbox = input_dir or INBOX_DIR
    for d in (INBOX_DIR, PROCESSED_DIR, REJECTED_DIR, ARCHIVE_DIR):
        d.mkdir(parents=True, exist_ok=True)

    batch = ImportBatchResult(dry_run=dry_run)
    paths = sorted(inbox.glob("*.csv"))
    inspect_csv_paths(paths)

    for path in paths:
        file_result = import_csv_file(conn, path, dry_run=dry_run)
        batch.files.append(file_result)

        if file_result.csv_type == "PLAYER_STATS_CSV":
            batch.player_rows_imported += file_result.imported
        elif file_result.csv_type == "REFEREE_CARDS_CSV":
            batch.referee_rows_imported += file_result.imported
        elif file_result.csv_type == "ODDS_CSV":
            batch.odds_files_rejected += 1
        elif file_result.csv_type == "UNKNOWN_CSV":
            batch.unknown_files_rejected += 1

        if dry_run:
            continue

        archive_target = ARCHIVE_DIR / path.name
        shutil.copy2(path, archive_target)

        if file_result.status.startswith("rejected") or file_result.csv_type in {"ODDS_CSV", "UNKNOWN_CSV"}:
            shutil.move(str(path), str(REJECTED_DIR / path.name))
        else:
            shutil.move(str(path), str(PROCESSED_DIR / path.name))

    if not dry_run:
        crosswalk = build_enrichment_fixture_crosswalk(conn, persist_links=True)
        conn.commit()
        summary = batch.to_dict()
        summary["crosswalk"] = {
            "status_counts": crosswalk.get("status_counts"),
            "matched_high": crosswalk.get("status_counts", {}).get("MATCHED_HIGH_CONFIDENCE", 0),
        }
        summary["final_recommendation"] = final_recommendation(summary, crosswalk)
    else:
        summary = batch.to_dict()

    IMPORT_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    IMPORT_SUMMARY_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return batch


def final_recommendation(summary: dict[str, Any], crosswalk: dict[str, Any] | None = None) -> str:
    if summary.get("odds_files_rejected", 0) > 0 and summary.get("player_rows_imported", 0) == 0:
        return "CSV_FILES_NOT_ODDS"
    cw = crosswalk or {}
    counts = cw.get("status_counts") or summary.get("crosswalk", {}).get("status_counts") or {}
    high = int(counts.get("MATCHED_HIGH_CONFIDENCE", 0))
    if summary.get("player_rows_imported", 0) == 0 and summary.get("referee_rows_imported", 0) == 0:
        return "NEED_CSV_FORMAT_MAPPING"
    if high == 0:
        return "NEED_FIXTURE_CROSSWALK"
    if high > 0:
        return "ODDALERTS_ENRICHMENT_READY"
    return "DO_NOT_USE_ENRICHMENT_YET"
