"""Database connection and initialization."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from worldcup_predictor.database.schema import DDL_STATEMENTS, DEFAULT_DB_PATH, SCHEMA_VERSION


def get_db_path(path: str | Path | None = None) -> Path:
    return Path(path or DEFAULT_DB_PATH)


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    db_path = get_db_path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_database(path: str | Path | None = None) -> sqlite3.Connection:
    from worldcup_predictor.access.schema import ACCESS_DDL_STATEMENTS, ACCESS_SCHEMA_VERSION

    conn = connect(path)
    for ddl in DDL_STATEMENTS:
        conn.execute(ddl)
    for ddl in ACCESS_DDL_STATEMENTS:
        conn.execute(ddl)
    version = max(SCHEMA_VERSION, ACCESS_SCHEMA_VERSION)
    conn.execute(
        "INSERT OR REPLACE INTO schema_meta(key, value) VALUES (?, ?)",
        ("schema_version", str(version)),
    )
    conn.commit()
    return conn


def is_connected(path: str | Path | None = None) -> bool:
    db_path = get_db_path(path)
    if not db_path.exists():
        return False
    try:
        conn = connect(db_path)
        conn.execute("SELECT 1 FROM schema_meta LIMIT 1")
        conn.close()
        return True
    except sqlite3.Error:
        return False
