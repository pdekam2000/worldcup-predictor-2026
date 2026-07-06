#!/usr/bin/env python3
"""Import frozen league batch snapshots without overwriting existing frozen rows."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.competitions import get_competition
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.owner_predict_eval.tomorrow_league_batch import ensure_batch_tables


def _ensure_competition(conn: sqlite3.Connection, key: str, fx_row: dict | None = None) -> None:
    if conn.execute("SELECT 1 FROM competitions WHERE key=?", (key,)).fetchone():
        return
    name = key.replace("_", " ").title()
    league_id = int((fx_row or {}).get("league_id") or 0)
    season = int((fx_row or {}).get("season") or 2026)
    comp_type = str((fx_row or {}).get("competition_type") or "league")
    try:
        cfg = get_competition(key)
        name = cfg.name
        league_id = int(cfg.league_id or league_id)
        season = int(cfg.season or season)
        comp_type = str(cfg.compensation_type or comp_type)
    except KeyError:
        pass
    conn.execute(
        """
        INSERT OR IGNORE INTO competitions
        (key, name, league_id, season, competition_type, supports_groups, supports_table, updated_at)
        VALUES (?, ?, ?, ?, ?, 0, 1, datetime('now'))
        """,
        (key, name, league_id, season, comp_type),
    )


def _upsert_fixture(conn: sqlite3.Connection, row: dict) -> str:
    _ensure_competition(conn, str(row["competition_key"]), row)
    existing = conn.execute(
        "SELECT fixture_id FROM fixtures WHERE fixture_id=?",
        (row["fixture_id"],),
    ).fetchone()
    if existing:
        return "exists"
    cols = [k for k in row.keys() if k != "fixture_id"]
    placeholders = ", ".join("?" for _ in cols)
    col_names = ", ".join(cols)
    conn.execute(
        f"INSERT INTO fixtures (fixture_id, {col_names}) VALUES (?, {placeholders})",
        [row["fixture_id"]] + [row[c] for c in cols],
    )
    return "inserted"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("export_json")
    args = parser.parse_args()

    payload = json.loads(Path(args.export_json).read_text(encoding="utf-8"))
    settings = get_settings()
    conn = connect(settings.sqlite_path)
    ensure_batch_tables(conn)

    fixture_stats = {"inserted": 0, "exists": 0}
    for fx in payload.get("fixtures") or []:
        status = _upsert_fixture(conn, fx)
        fixture_stats[status] += 1

    snap_stats = {"inserted": 0, "skipped_existing": 0}
    for snap in payload.get("snapshots") or []:
        bid = snap["batch_id"]
        fid = int(snap["fixture_id"])
        exists = conn.execute(
            "SELECT id FROM owner_league_batch_snapshots WHERE batch_id=? AND fixture_id=? AND is_frozen=1",
            (bid, fid),
        ).fetchone()
        if exists:
            snap_stats["skipped_existing"] += 1
            continue
        conn.execute(
            """
            INSERT INTO owner_league_batch_snapshots
            (batch_id, target_date, fixture_id, competition_key, competition_type, kickoff_utc,
             snapshot_json, prediction_timestamp, is_frozen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bid,
                snap.get("target_date"),
                fid,
                snap.get("competition_key"),
                snap.get("competition_type"),
                snap.get("kickoff_utc"),
                snap.get("snapshot_json"),
                snap.get("prediction_timestamp"),
                int(snap.get("is_frozen") or 1),
            ),
        )
        snap_stats["inserted"] += 1
    conn.commit()
    conn.close()
    print(json.dumps({"fixtures": fixture_stats, "snapshots": snap_stats}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
