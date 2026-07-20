"""Research DB connection for ECSE timing experiment."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from worldcup_predictor.config.env_loading import project_root
from worldcup_predictor.research.ecse_timing_experiment.constants import DB_RELATIVE
from worldcup_predictor.research.ecse_timing_experiment.ddl import ensure_timing_schema


def timing_db_path(root: Path | None = None) -> Path:
    base = root or project_root()
    return (base / DB_RELATIVE).resolve()


def connect_timing_db(root: Path | None = None) -> sqlite3.Connection:
    path = timing_db_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    ensure_timing_schema(conn)
    return conn
