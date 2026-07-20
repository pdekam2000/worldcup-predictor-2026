"""WSP/ECSE backup and restore for temporary research runs."""

from __future__ import annotations

import sqlite3
from typing import Any


def backup_prediction_state(conn: sqlite3.Connection, fixture_ids: list[int]) -> dict[str, Any]:
    wsp: dict[str, dict[str, Any]] = {}
    ecse: dict[str, dict[str, Any]] = {}
    for fid in fixture_ids:
        row = conn.execute(
            "SELECT * FROM worldcup_stored_predictions WHERE fixture_id=? LIMIT 1",
            (int(fid),),
        ).fetchone()
        if row:
            wsp[str(fid)] = dict(row)
        snap = conn.execute(
            "SELECT * FROM ecse_prediction_snapshots WHERE fixture_id=? LIMIT 1",
            (int(fid),),
        ).fetchone()
        if snap:
            ecse[str(fid)] = dict(snap)
    return {"wsp": wsp, "ecse": ecse}


def restore_prediction_state(conn: sqlite3.Connection, backup: dict[str, Any]) -> dict[str, int]:
    restored_wsp = 0
    restored_ecse = 0
    for fid_s, row in (backup.get("wsp") or {}).items():
        cols = list(row.keys())
        existing = conn.execute(
            "SELECT 1 FROM worldcup_stored_predictions WHERE fixture_id=? LIMIT 1",
            (int(fid_s),),
        ).fetchone()
        if existing:
            set_clause = ",".join(f"{c}=?" for c in cols if c != "fixture_id")
            vals = [row[c] for c in cols if c != "fixture_id"] + [int(fid_s)]
            if set_clause:
                conn.execute(
                    f"UPDATE worldcup_stored_predictions SET {set_clause} WHERE fixture_id=?",
                    vals,
                )
        else:
            placeholders = ",".join("?" for _ in cols)
            conn.execute(
                f"INSERT INTO worldcup_stored_predictions ({','.join(cols)}) VALUES ({placeholders})",
                [row[c] for c in cols],
            )
        restored_wsp += 1
    for fid_s, row in (backup.get("ecse") or {}).items():
        cols = list(row.keys())
        existing = conn.execute(
            "SELECT 1 FROM ecse_prediction_snapshots WHERE fixture_id=? LIMIT 1",
            (int(fid_s),),
        ).fetchone()
        if existing:
            set_clause = ",".join(f"{c}=?" for c in cols if c not in {"id", "fixture_id"})
            vals = [row[c] for c in cols if c not in {"id", "fixture_id"}] + [int(fid_s)]
            if set_clause:
                conn.execute(
                    f"UPDATE ecse_prediction_snapshots SET {set_clause} WHERE fixture_id=?",
                    vals,
                )
        else:
            use_cols = [c for c in cols if c != "id"]
            placeholders = ",".join("?" for _ in use_cols)
            conn.execute(
                f"INSERT INTO ecse_prediction_snapshots ({','.join(use_cols)}) VALUES ({placeholders})",
                [row[c] for c in use_cols],
            )
        restored_ecse += 1
    conn.commit()
    return {"restored_wsp": restored_wsp, "restored_ecse": restored_ecse}


def verify_wsp_restore(conn: sqlite3.Connection, backup: dict[str, Any], fixture_ids: list[int]) -> bool:
    for fid in fixture_ids:
        before = (backup.get("wsp") or {}).get(str(fid))
        if not before:
            continue
        after = conn.execute(
            "SELECT payload_json FROM worldcup_stored_predictions WHERE fixture_id=? LIMIT 1",
            (int(fid),),
        ).fetchone()
        if not after or after["payload_json"] != before.get("payload_json"):
            return False
    return True
