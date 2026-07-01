"""OddAlerts probability CSV market mapping, audit, import, and analysis."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from worldcup_predictor.data_import.historical_csv_odds import _norm_team
from worldcup_predictor.data_import.oddalerts_probability_market_ddl import (
    ensure_oddalerts_probability_market_tables,
)
from worldcup_predictor.data_import.oddalerts_enrichment_csv_importer import (
    MIN_HIGH_CONFIDENCE,
    MIN_LOW_CONFIDENCE,
    TEAM_ALIASES,
    _alias_team,
    _score_fixture_candidate,
    parse_fixture_pair,
)
from worldcup_predictor.data_import.uefa_result_matching import normalize_team_name

PHASE = "ODDALERTS-CSV-MARKET-MAPPING-ALL"
PROCESS_DATE = "2026-06-30"
MAPPING_CONFIG_PATH = Path("config/oddalerts_probability_market_mapping.json")
PROCESSED_DIR = Path("data/oddalerts_csv/processed")
INBOX_DIR = Path("data/oddalerts_csv/inbox")
ARCHIVE_DIR = Path("data/oddalerts_csv/raw_archive")

ECSE_KEYS = frozenset(
    {
        "match_result_home",
        "match_result_draw",
        "match_result_away",
        "goals_over_2_5",
        "goals_under_2_5",
        "btts_yes",
        "btts_no",
    }
)

OUTCOME_SUFFIXES = sorted(
    [
        "under_115",
        "over_115",
        "under_105",
        "over_105",
        "under_95",
        "over_95",
        "under_85",
        "over_85",
        "under_75",
        "over_75",
        "under_65",
        "over_65",
        "under_55",
        "over_55",
        "under_45",
        "over_45",
        "under_35",
        "over_35",
        "under_25",
        "over_25",
        "under_15",
        "over_15",
        "under_05",
        "over_05",
        "home_draw",
        "home_away",
        "draw_away",
        "home",
        "draw",
        "away",
        "yes",
        "no",
    ],
    key=len,
    reverse=True,
)

FILENAME_RE = re.compile(
    r"^oddalerts_(?P<body>.+)_(?P<dfrom>unknown|\d{4}-\d{2}-\d{2})_(?P<dto>unknown|\d{4}-\d{2}-\d{2})_(?P<emailts>\d{8})_(?P<hash>[a-f0-9]{6,})\.csv$",
    re.I,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _slug(text: str) -> str:
    t = re.sub(r"[^a-z0-9]+", "_", (text or "").lower().strip())
    return re.sub(r"_+", "_", t).strip("_")


def load_mapping_config(path: Path | None = None) -> dict[str, Any]:
    p = path or MAPPING_CONFIG_PATH
    return json.loads(p.read_text(encoding="utf-8"))


def parse_filename_metadata(filename: str) -> dict[str, Any]:
    m = FILENAME_RE.match(filename)
    if not m:
        return {"export_market": None, "export_outcome": None, "date_from": None, "date_to": None, "email_date": None}
    body = m.group("body")
    outcome = None
    market_body = body
    for suffix in OUTCOME_SUFFIXES:
        token = f"_{suffix}"
        if body.endswith(token):
            outcome = suffix
            market_body = body[: -len(token)]
            break

    mb = market_body
    if mb.startswith("fulltime_result"):
        export_market = "Fulltime Result Probability"
    elif mb.startswith("both_teams_to_score"):
        export_market = "Both Teams To Score Probability"
    elif mb.startswith("double_chance"):
        export_market = "Double Chance Probability"
    elif mb.startswith("first_half_winner"):
        export_market = "First Half Winner Probability"
    elif mb.startswith("corners_over_under_"):
        n = mb.rsplit("_", 1)[-1]
        export_market = f"Corners Over/Under {n} Probability"
    elif mb.startswith("home_over_under_"):
        nums = re.findall(r"(\d)_(\d)$", mb)
        export_market = f"Home Over/Under {nums[0][0]}.{nums[0][1]} Probability" if nums else "Home Over/Under Probability"
    elif mb.startswith("away_over_under_"):
        nums = re.findall(r"(\d)_(\d)$", mb)
        export_market = f"Away Over/Under {nums[0][0]}.{nums[0][1]} Probability" if nums else "Away Over/Under Probability"
    elif mb.startswith("over_under_"):
        nums = re.findall(r"(\d)_(\d)$", mb)
        export_market = f"Over/Under {nums[0][0]}.{nums[0][1]} Probability" if nums else "Over/Under Probability"
    else:
        export_market = mb.replace("_", " ").title() + " Probability"

    email_ts = m.group("emailts")
    email_date = f"{email_ts[:4]}-{email_ts[4:6]}-{email_ts[6:8]}" if len(email_ts) == 8 else None
    dfrom = m.group("dfrom")
    dto = m.group("dto")
    return {
        "export_market": export_market,
        "export_outcome": outcome,
        "date_from": None if dfrom == "unknown" else dfrom,
        "date_to": None if dto == "unknown" else dto,
        "email_date": email_date,
    }


def normalize_market_outcome(
    export_market: str | None,
    export_outcome: str | None,
    row_outcome: str | None = None,
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or load_mapping_config()
    market_raw = (export_market or "").strip()
    market_norm = _slug(market_raw.replace(" Probability", ""))
    outcome_raw = (export_outcome or row_outcome or "").strip().rstrip("-").strip()
    outcome_norm = _slug(outcome_raw)

    result: dict[str, Any] = {
        "normalized_market_key": None,
        "market_family": "unknown",
        "threshold_value": None,
        "side": None,
        "outcome_type": outcome_norm or None,
        "mapping_status": "unknown",
    }

    def _set(key: str, family: str, **extra: Any) -> None:
        result["normalized_market_key"] = key
        result["market_family"] = family
        result["mapping_status"] = "mapped"
        result.update(extra)

    if "fulltime" in market_norm and "result" in market_norm:
        m = {"home": "match_result_home", "draw": "match_result_draw", "away": "match_result_away"}
        if outcome_norm in m:
            _set(m[outcome_norm], "match_result")
        return result

    if "both_teams" in market_norm or market_norm == "btts":
        m = {"yes": "btts_yes", "no": "btts_no"}
        if outcome_norm in m:
            _set(m[outcome_norm], "btts")
        return result

    if "double_chance" in market_norm:
        m = {
            "home_draw": "double_chance_home_draw",
            "home_away": "double_chance_home_away",
            "draw_away": "double_chance_draw_away",
        }
        if outcome_norm in m:
            _set(m[outcome_norm], "double_chance")
        return result

    # tolerate catalog slug fragments like over_under_2_5_over + outcome over_25
    if market_norm.startswith("over_under") and "corners" not in market_norm:
        base = re.sub(r"_(over|under)$", "", market_norm)
        thresh_match = re.search(r"over_under_(\d)_(\d)", base) or re.search(r"over_under_(\d)_(\d)", market_norm)
        if thresh_match:
            thresh = float(f"{thresh_match.group(1)}.{thresh_match.group(2)}")
            key_map = {
                (1.5, "over_15"): "goals_over_1_5",
                (1.5, "under_15"): "goals_under_1_5",
                (2.5, "over_25"): "goals_over_2_5",
                (2.5, "under_25"): "goals_under_2_5",
                (3.5, "over_35"): "goals_over_3_5",
                (3.5, "under_35"): "goals_under_3_5",
                (4.5, "over_45"): "goals_over_4_5",
                (4.5, "under_45"): "goals_under_4_5",
            }
            hit = key_map.get((thresh, outcome_norm))
            if hit:
                _set(hit, "goals_over_under", threshold_value=thresh)
        return result

    if market_norm.startswith("home_over_under"):
        base = re.sub(r"_(over|under)$", "", market_norm)
        thresh_match = re.search(r"home_over_under_(\d)_(\d)", base) or re.search(r"home_over_under_(\d)_(\d)", market_norm)
        if thresh_match:
            thresh = float(f"{thresh_match.group(1)}.{thresh_match.group(2)}")
            key_map = {
                (0.5, "over_05"): "home_goals_over_0_5",
                (0.5, "under_05"): "home_goals_under_0_5",
                (1.5, "over_15"): "home_goals_over_1_5",
                (1.5, "under_15"): "home_goals_under_1_5",
            }
            hit = key_map.get((thresh, outcome_norm))
            if hit:
                _set(hit, "home_team_goals", threshold_value=thresh, side="home")
        return result

    if market_norm.startswith("away_over_under"):
        base = re.sub(r"_(over|under)$", "", market_norm)
        thresh_match = re.search(r"away_over_under_(\d)_(\d)", base) or re.search(r"away_over_under_(\d)_(\d)", market_norm)
        if thresh_match:
            thresh = float(f"{thresh_match.group(1)}.{thresh_match.group(2)}")
            key_map = {
                (0.5, "over_05"): "away_goals_over_0_5",
                (0.5, "under_05"): "away_goals_under_0_5",
                (1.5, "over_15"): "away_goals_over_1_5",
                (1.5, "under_15"): "away_goals_under_1_5",
            }
            hit = key_map.get((thresh, outcome_norm))
            if hit:
                _set(hit, "away_team_goals", threshold_value=thresh, side="away")
        return result

    if "first_half" in market_norm:
        m = {"home": "first_half_home", "draw": "first_half_draw", "away": "first_half_away"}
        if outcome_norm in m:
            _set(m[outcome_norm], "first_half_result")
        return result

    if "corners_over_under" in market_norm:
        thresh_match = re.search(r"corners_over_under_(\d+)", market_norm)
        corners_map = cfg.get("corners_threshold_map") or {}
        if thresh_match and outcome_norm:
            n = thresh_match.group(1)
            suffix = corners_map.get(n)
            if not suffix:
                suffix = f"{n}_5"
            if outcome_norm.startswith("over_"):
                _set(f"corners_over_{suffix}", "corners_over_under", threshold_value=float(n) + 0.5)
            elif outcome_norm.startswith("under_"):
                _set(f"corners_under_{suffix}", "corners_over_under", threshold_value=float(n) + 0.5)
        return result

    return result


def discover_probability_csv_files(conn: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    seen_hashes: set[str] = set()
    files: list[dict[str, Any]] = []

    def add_path(path: Path, *, catalog_meta: dict[str, Any] | None = None) -> None:
        if not path.is_file() or not path.name.endswith(".csv"):
            return
        if path.name.startswith("_"):
            return
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in seen_hashes:
            return
        seen_hashes.add(digest)
        meta = parse_filename_metadata(path.name)
        if catalog_meta:
            for k, v in catalog_meta.items():
                if k in {"catalog_row_count"} and v:
                    meta[k] = v
        files.append(
            {
                "path": str(path.resolve()),
                "filename": path.name,
                "source_sha256": digest,
                **meta,
            }
        )

    if conn is not None:
        try:
            rows = conn.execute(
                """
                SELECT source_file, source_sha256, market, outcome, date_from, date_to, row_count
                FROM oddalerts_inbox_csv_catalog
                WHERE csv_type = 'ODDS_CSV' AND import_status = 'staged'
                """
            ).fetchall()
            for row in rows:
                fname = row["source_file"]
                for root in (PROCESSED_DIR, INBOX_DIR, ARCHIVE_DIR):
                    candidate = root / fname
                    if candidate.is_file():
                        add_path(
                            candidate,
                            catalog_meta={
                                "export_market": row["market"],
                                "export_outcome": row["outcome"],
                                "date_from": row["date_from"],
                                "date_to": row["date_to"],
                                "catalog_row_count": row["row_count"],
                            },
                        )
                        break
        except sqlite3.OperationalError:
            pass

    for root in (PROCESSED_DIR, INBOX_DIR, ARCHIVE_DIR):
        if root.is_dir():
            for path in sorted(root.glob("oddalerts_*.csv")):
                add_path(path)

    return sorted(files, key=lambda x: x["filename"])


def _parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).strip().replace("%", ""))
    except (TypeError, ValueError):
        return None


def _row_hash(source_file: str, row: dict[str, str], normalized_key: str | None, bookmaker: str) -> str:
    payload = {
        "source_file": source_file,
        "id": row.get("ID"),
        "kickoff": row.get("Kickoff"),
        "home": row.get("Home Team"),
        "away": row.get("Away Team"),
        "normalized_market_key": normalized_key,
        "bookmaker": bookmaker,
        "outcome": row.get("Outcome"),
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def audit_probability_csvs(
    files: list[dict[str, Any]],
    *,
    sample_rows_per_file: int = 3,
) -> dict[str, Any]:
    markets: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    bookmakers: dict[str, int] = defaultdict(int)
    date_ranges: dict[str, int] = defaultdict(int)
    unknown_markets: dict[str, int] = defaultdict(int)
    unknown_outcomes: dict[str, int] = defaultdict(int)
    missing_bookmaker = 0
    total_rows = 0
    columns_seen: set[str] = set()
    file_summaries: list[dict[str, Any]] = []

    for finfo in files:
        path = Path(finfo["path"])
        export_market = finfo.get("export_market")
        export_outcome = finfo.get("export_outcome")
        file_rows = 0
        file_bookmakers: set[str] = set()
        sample_rows: list[dict[str, Any]] = []

        with path.open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames:
                columns_seen.update(reader.fieldnames)
            for i, row in enumerate(reader):
                file_rows += 1
                total_rows += 1
                bm = (row.get("Bookmaker") or "").strip() or "unknown"
                if bm == "unknown":
                    missing_bookmaker += 1
                bookmakers[bm] += 1
                file_bookmakers.add(bm)

                row_outcome = (row.get("Outcome") or export_outcome or "").strip()
                mapped = normalize_market_outcome(export_market, export_outcome, row_outcome)
                mlabel = export_market or "unknown"
                markets[mlabel][row_outcome or export_outcome or "unknown"] += 1
                if mapped["mapping_status"] != "mapped":
                    unknown_markets[mlabel] += 1
                    unknown_outcomes[f"{mlabel}|{row_outcome}"] += 1

                dr = f"{finfo.get('date_from') or 'unknown'}..{finfo.get('date_to') or 'unknown'}"
                date_ranges[dr] += 1

                if i < sample_rows_per_file:
                    sample_rows.append(
                        {
                            "fixture": row.get("Fixture"),
                            "kickoff": row.get("Kickoff"),
                            "bookmaker": bm,
                            "probability": row.get("Probability (%)"),
                            "outcome": row_outcome,
                            "normalized_market_key": mapped.get("normalized_market_key"),
                        }
                    )

        file_summaries.append(
            {
                "filename": finfo["filename"],
                "export_market": export_market,
                "export_outcome": export_outcome,
                "row_count": file_rows,
                "bookmakers": sorted(file_bookmakers),
                "sample_rows": sample_rows,
            }
        )

    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "date_processed": PROCESS_DATE,
        "files_scanned": len(files),
        "total_rows": total_rows,
        "columns_detected": sorted(columns_seen),
        "markets_found": {k: dict(v) for k, v in sorted(markets.items())},
        "bookmakers_found": dict(sorted(bookmakers.items(), key=lambda x: -x[1])),
        "date_ranges_found": dict(sorted(date_ranges.items(), key=lambda x: -x[1])),
        "unknown_markets": dict(sorted(unknown_markets.items(), key=lambda x: -x[1])),
        "unknown_outcomes": dict(sorted(unknown_outcomes.items(), key=lambda x: -x[1])),
        "missing_bookmaker_rows": missing_bookmaker,
        "files": file_summaries,
    }


def import_probability_rows(
    conn: sqlite3.Connection,
    files: list[dict[str, Any]],
    *,
    batch_size: int = 500,
) -> dict[str, Any]:
    ensure_oddalerts_probability_market_tables(conn)

    inserted = 0
    skipped_duplicate = 0
    unknown_rows = 0
    mapped_rows = 0
    by_market_key: dict[str, int] = defaultdict(int)
    by_bookmaker: dict[str, int] = defaultdict(int)

    insert_sql = """
        INSERT OR IGNORE INTO oddalerts_probability_market_rows (
            row_hash, source_file, source_file_hash, export_email_date,
            export_market, export_outcome, normalized_market_key, market_family,
            threshold_value, side, outcome_type, bookmaker, bookmaker_slug,
            probability_min, probability_max, export_date_start, export_date_end,
            fixture_name, fixture_date, kickoff_time, competition_name, country,
            home_team_normalized, away_team_normalized, internal_fixture_id,
            fixture_match_status, fixture_match_confidence,
            model_probability, opening_odds, closing_odds, peak_odds,
            raw_row_json, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """

    for finfo in files:
        path = Path(finfo["path"])
        export_market = finfo.get("export_market")
        export_outcome = finfo.get("export_outcome")
        batch: list[tuple[Any, ...]] = []

        with path.open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                row_outcome = (row.get("Outcome") or export_outcome or "").strip()
                mapped = normalize_market_outcome(export_market, export_outcome, row_outcome)
                bookmaker = (row.get("Bookmaker") or "").strip() or "unknown"
                nkey = mapped.get("normalized_market_key")
                rh = _row_hash(path.name, row, nkey, bookmaker)
                kickoff = (row.get("Kickoff") or "").strip()
                fixture_date = kickoff[:10] if kickoff else None
                home = (row.get("Home Team") or "").strip()
                away = (row.get("Away Team") or "").strip()
                fixture_name = (row.get("Fixture") or f"{home} vs {away}").strip()

                prob = _parse_float(row.get("Probability (%)"))
                if mapped["mapping_status"] == "mapped":
                    mapped_rows += 1
                    if nkey:
                        by_market_key[nkey] += 1
                else:
                    unknown_rows += 1

                by_bookmaker[bookmaker] += 1
                batch.append(
                    (
                        rh,
                        path.name,
                        finfo["source_sha256"],
                        finfo.get("email_date"),
                        export_market,
                        export_outcome or row_outcome,
                        nkey,
                        mapped.get("market_family"),
                        mapped.get("threshold_value"),
                        mapped.get("side"),
                        mapped.get("outcome_type"),
                        bookmaker,
                        _slug(bookmaker),
                        prob,
                        prob,
                        finfo.get("date_from"),
                        finfo.get("date_to"),
                        fixture_name,
                        fixture_date,
                        kickoff,
                        (row.get("Competition Name") or "").strip() or None,
                        (row.get("Competition Country") or "").strip() or None,
                        normalize_team_name(home) if home else None,
                        normalize_team_name(away) if away else None,
                        None,
                        None,
                        None,
                        prob,
                        _parse_float(row.get("Opening Odds")),
                        _parse_float(row.get("Closing Odds")),
                        _parse_float(row.get("Peak Odds")),
                        json.dumps(row, ensure_ascii=False),
                        _utc_now(),
                    )
                )

                if len(batch) >= batch_size:
                    before = conn.total_changes
                    conn.executemany(insert_sql, batch)
                    inserted += conn.total_changes - before
                    skipped_duplicate += len(batch) - (conn.total_changes - before)
                    batch.clear()

        if batch:
            before = conn.total_changes
            conn.executemany(insert_sql, batch)
            inserted += conn.total_changes - before
            skipped_duplicate += len(batch) - (conn.total_changes - before)

    conn.commit()
    return {
        "rows_inserted": inserted,
        "rows_skipped_duplicate": skipped_duplicate,
        "mapped_rows": mapped_rows,
        "unknown_rows": unknown_rows,
        "by_normalized_market_key": dict(sorted(by_market_key.items())),
        "by_bookmaker": dict(sorted(by_bookmaker.items(), key=lambda x: -x[1])),
    }


def build_bookmaker_coverage(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT bookmaker, normalized_market_key, market_family, COUNT(*) c
        FROM oddalerts_probability_market_rows
        GROUP BY bookmaker, normalized_market_key, market_family
        """
    ).fetchall()

    by_bookmaker: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"row_count": 0, "markets": defaultdict(int), "families": defaultdict(int), "ecse_keys": set()}
    )
    for row in rows:
        bm = row["bookmaker"] or "unknown"
        by_bookmaker[bm]["row_count"] += int(row["c"])
        nkey = row["normalized_market_key"] or "unknown"
        by_bookmaker[bm]["markets"][nkey] += int(row["c"])
        fam = row["market_family"] or "unknown"
        by_bookmaker[bm]["families"][fam] += int(row["c"])
        if nkey in ECSE_KEYS:
            by_bookmaker[bm]["ecse_keys"].add(nkey)

    corners_keys = [r[0] for r in conn.execute(
        "SELECT DISTINCT normalized_market_key FROM oddalerts_probability_market_rows WHERE market_family = 'corners_over_under'"
    ).fetchall()]

    payload: dict[str, Any] = {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "bookmakers_detected": sorted(by_bookmaker.keys()),
        "row_count_by_bookmaker": {k: v["row_count"] for k, v in sorted(by_bookmaker.items(), key=lambda x: -x[1]["row_count"])},
        "market_coverage_by_bookmaker": {},
        "ecse_required_coverage_by_bookmaker": {},
        "corners_coverage_by_bookmaker": {},
    }

    for bm, data in by_bookmaker.items():
        payload["market_coverage_by_bookmaker"][bm] = dict(sorted(data["markets"].items(), key=lambda x: -x[1]))
        payload["ecse_required_coverage_by_bookmaker"][bm] = {
            "available": sorted(data["ecse_keys"]),
            "missing": sorted(ECSE_KEYS - data["ecse_keys"]),
            "complete": data["ecse_keys"] >= ECSE_KEYS,
        }
        corners = {k: v for k, v in data["markets"].items() if k.startswith("corners_")}
        payload["corners_coverage_by_bookmaker"][bm] = corners

    payload["corners_keys_detected"] = sorted(k for k in corners_keys if k)
    return payload


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
        key = f"{kickoff}|{_norm_team(row['home_team'])}|{_norm_team(row['away_team'])}"
        index[key].append(dict(row))
    return index


def crosswalk_probability_rows(conn: sqlite3.Connection) -> dict[str, Any]:
    fixture_index = build_fixture_index(conn)
    pairs = conn.execute(
        """
        SELECT DISTINCT fixture_name, home_team_normalized, away_team_normalized, kickoff_time, fixture_date
        FROM oddalerts_probability_market_rows
        """
    ).fetchall()

    status_counts: dict[str, int] = defaultdict(int)
    crosswalk_rows: list[dict[str, Any]] = []

    for row in pairs:
        fixture_name = row["fixture_name"] or ""
        home = row["home_team_normalized"] or ""
        away = row["away_team_normalized"] or ""
        kickoff = (row["kickoff_time"] or row["fixture_date"] or "")[:10]

        if not home or not away or not kickoff:
            parsed = parse_fixture_pair(fixture_name)
            if parsed:
                home = home or _alias_team(parsed[0])
                away = away or _alias_team(parsed[1])

        fixture_id = None
        confidence = None
        status = "LOCAL_FIXTURE_MISSING"
        reason = "no_db_candidate"
        matched_teams = None

        if home and away and kickoff:
            key = f"{kickoff}|{_norm_team(home)}|{_norm_team(away)}"
            hits = fixture_index.get(key, [])
            if len(hits) == 1:
                fx = hits[0]
                score = _score_fixture_candidate(
                    oa_home=home,
                    oa_away=away,
                    db_home=str(fx["home_team"]),
                    db_away=str(fx["away_team"]),
                    oa_date=kickoff,
                    db_kickoff=str(fx["kickoff_utc"]),
                )
                if score >= MIN_HIGH_CONFIDENCE:
                    status = "MATCHED_HIGH_CONFIDENCE"
                    fixture_id = int(fx["fixture_id"])
                    confidence = score
                    matched_teams = f"{fx['home_team']} vs {fx['away_team']}"
                    reason = None
                elif score >= MIN_LOW_CONFIDENCE:
                    status = "MATCHED_LOW_CONFIDENCE"
                    confidence = score
                    reason = "below_high_confidence_threshold"
                else:
                    status = "LOCAL_FIXTURE_MISSING"
                    confidence = score
                    reason = "score_too_low"
            elif len(hits) > 1:
                status = "AMBIGUOUS"
                reason = "multiple_db_fixtures_same_key"
                confidence = 1.0

        status_counts[status] += 1
        crosswalk_rows.append(
            {
                "fixture_name": fixture_name,
                "home_team_normalized": home,
                "away_team_normalized": away,
                "kickoff_date": kickoff,
                "status": status,
                "confidence": confidence,
                "fixture_id": fixture_id,
                "matched_db_teams": matched_teams,
                "rejection_reason": reason,
            }
        )

        if fixture_id and status == "MATCHED_HIGH_CONFIDENCE":
            conn.execute(
                """
                UPDATE oddalerts_probability_market_rows
                SET internal_fixture_id = ?, fixture_match_status = ?, fixture_match_confidence = ?
                WHERE fixture_name = ? AND COALESCE(kickoff_time, fixture_date) LIKE ?
                  AND home_team_normalized = ? AND away_team_normalized = ?
                """,
                (fixture_id, status, confidence, fixture_name, f"{kickoff}%", home, away),
            )

    conn.commit()
    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "unique_fixtures": len(crosswalk_rows),
        "status_counts": dict(status_counts),
        "rows": crosswalk_rows,
    }


def analyze_multi_bookmaker(conn: sqlite3.Connection, *, disagreement_threshold: float = 8.0) -> dict[str, Any]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in conn.execute(
        """
        SELECT fixture_name, kickoff_time, normalized_market_key, bookmaker,
               model_probability, opening_odds, closing_odds
        FROM oddalerts_probability_market_rows
        WHERE normalized_market_key IS NOT NULL AND bookmaker IS NOT NULL
        """
    ).fetchall():
        key = (row["fixture_name"] or "", row["kickoff_time"] or "", row["normalized_market_key"] or "")
        groups[key].append(dict(row))

    multi_groups = 0
    high_disagreement = 0
    samples: list[dict[str, Any]] = []

    for (fixture, kickoff, nkey), items in groups.items():
        bookmakers = {i["bookmaker"] for i in items}
        if len(bookmakers) < 2:
            continue
        multi_groups += 1
        probs = [float(i["model_probability"]) for i in items if i.get("model_probability") is not None]
        if len(probs) < 2:
            continue
        spread = max(probs) - min(probs)
        avg = statistics.mean(probs)
        med = statistics.median(probs)
        flagged = spread >= disagreement_threshold
        if flagged:
            high_disagreement += 1
        if flagged or len(samples) < 50:
            samples.append(
                {
                    "fixture_name": fixture,
                    "kickoff_time": kickoff,
                    "normalized_market_key": nkey,
                    "bookmakers": sorted(bookmakers),
                    "bookmaker_count": len(bookmakers),
                    "probabilities": {i["bookmaker"]: i["model_probability"] for i in items},
                    "average_probability": round(avg, 4),
                    "median_probability": round(med, 4),
                    "min_probability": round(min(probs), 4),
                    "max_probability": round(max(probs), 4),
                    "spread": round(spread, 4),
                    "high_disagreement": flagged,
                }
            )

    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "fixture_market_groups": len(groups),
        "multi_bookmaker_groups": multi_groups,
        "high_disagreement_groups": high_disagreement,
        "disagreement_threshold_pct": disagreement_threshold,
        "samples": samples[:200],
    }


def build_ecse_readiness_dryrun(conn: sqlite3.Connection) -> dict[str, Any]:
    ecse: dict[str, Any] = {}
    for key in sorted(ECSE_KEYS):
        count = conn.execute(
            "SELECT COUNT(*) c FROM oddalerts_probability_market_rows WHERE normalized_market_key = ?",
            (key,),
        ).fetchone()["c"]
        bookmakers = [
            r[0]
            for r in conn.execute(
                """
                SELECT DISTINCT bookmaker FROM oddalerts_probability_market_rows
                WHERE normalized_market_key = ?
                """,
                (key,),
            ).fetchall()
        ]
        ecse[key] = {"row_count": int(count), "bookmakers": bookmakers, "ready": int(count) > 0}

    extra_families = {
        "goals_ou_all": ["goals_over_1_5", "goals_under_1_5", "goals_over_3_5", "goals_under_3_5", "goals_over_4_5", "goals_under_4_5"],
        "team_totals": [
            "home_goals_over_0_5",
            "home_goals_under_0_5",
            "home_goals_over_1_5",
            "home_goals_under_1_5",
            "away_goals_over_0_5",
            "away_goals_under_0_5",
            "away_goals_over_1_5",
            "away_goals_under_1_5",
        ],
        "double_chance": ["double_chance_home_draw", "double_chance_home_away", "double_chance_draw_away"],
        "first_half": ["first_half_home", "first_half_draw", "first_half_away"],
    }
    extras: dict[str, Any] = {}
    for label, keys in extra_families.items():
        extras[label] = {}
        for k in keys:
            c = conn.execute(
                "SELECT COUNT(*) c FROM oddalerts_probability_market_rows WHERE normalized_market_key = ?",
                (k,),
            ).fetchone()["c"]
            extras[label][k] = int(c)

    corners = conn.execute(
        """
        SELECT normalized_market_key, COUNT(*) c
        FROM oddalerts_probability_market_rows
        WHERE market_family = 'corners_over_under'
        GROUP BY normalized_market_key
        """
    ).fetchall()
    extras["corners"] = {r["normalized_market_key"]: int(r["c"]) for r in corners}

    ecse_ready = all(v["ready"] for v in ecse.values())
    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "ecse_required": ecse,
        "ecse_all_ready": ecse_ready,
        "extra_coverage": extras,
    }


def final_mapping_recommendation(
    audit: dict[str, Any],
    import_stats: dict[str, Any],
    ecse: dict[str, Any],
    crosswalk: dict[str, Any],
) -> str:
    unknown_markets = audit.get("unknown_markets") or {}
    if unknown_markets and sum(unknown_markets.values()) > 0:
        return "NEED_UNKNOWN_MARKET_MAPPING"

    if int(import_stats.get("unknown_rows") or 0) > 0:
        return "NEED_UNKNOWN_MARKET_MAPPING"

    if not ecse.get("ecse_all_ready"):
        return "NEED_UNKNOWN_MARKET_MAPPING"

    if int(import_stats.get("rows_inserted") or 0) == 0:
        return "DO_NOT_USE_MARKET_DATA_YET"

    bookmakers = len(audit.get("bookmakers_found") or {})
    if bookmakers > 1:
        return "NEED_BOOKMAKER_POLICY"

    high = crosswalk.get("status_counts", {}).get("MATCHED_HIGH_CONFIDENCE", 0)
    total_fx = crosswalk.get("unique_fixtures", 0)
    if total_fx and high / total_fx < 0.01:
        return "NEED_FIXTURE_CROSSWALK_FIX"

    if import_stats.get("rows_inserted", 0) > 0 and ecse.get("ecse_all_ready"):
        return "READY_FOR_ODDS_SNAPSHOT_PROMOTION_DRYRUN"

    return "ODDALERTS_ALL_MARKETS_MAPPED"
