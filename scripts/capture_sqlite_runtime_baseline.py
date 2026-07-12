#!/usr/bin/env python3
"""Capture SQLite runtime baseline for lock hardening evidence."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path


def main() -> int:
    settings = get_settings()
    db_path = get_db_path(settings.sqlite_path)
    conn = connect(db_path)
    journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
    busy = int(conn.execute("PRAGMA busy_timeout").fetchone()[0])
    sync = conn.execute("PRAGMA synchronous").fetchone()[0]
    fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    wal_checkpoint = None
    try:
        row = conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
        wal_checkpoint = list(row) if row else None
    except Exception:
        pass
    conn.close()

    size_bytes = db_path.stat().st_size if db_path.exists() else 0
    lightweight = ROOT / "artifacts/provider_rescue/lightweight_validation.json"
    health = {}
    if lightweight.exists():
        health = json.loads(lightweight.read_text(encoding="utf-8"))

    out = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "database_path": str(db_path),
        "size_bytes": size_bytes,
        "journal_mode": journal,
        "busy_timeout_ms": busy,
        "synchronous": sync,
        "foreign_keys": bool(fk),
        "wal_checkpoint_passive": wal_checkpoint,
        "lightweight_validation": health,
        "lock_dir": os.environ.get("WORLDCUP_LOCK_DIR", "artifacts/locks"),
    }
    dest = ROOT / "artifacts/sqlite_lock/sqlite_runtime_baseline.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
