"""PHASE ECSE-X2-M2 — Read-only helpers."""

from __future__ import annotations

import sqlite3

BASELINE_TABLE = "ecse_score_distributions"


def baseline_table_row_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute(f"SELECT COUNT(1) FROM {BASELINE_TABLE}").fetchone()[0])
