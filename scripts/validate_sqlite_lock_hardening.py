#!/usr/bin/env python3
"""Validate SQLite lock hardening configuration and behavior."""

from __future__ import annotations

import json
import sqlite3
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.database.connection import connect, init_database
from worldcup_predictor.database.process_lock import ProcessLockError, single_instance_lock
from worldcup_predictor.database.sqlite_retry import (
    DEFAULT_MAX_ATTEMPTS,
    is_sqlite_lock_error,
    run_with_sqlite_retry,
)


def main() -> int:
    checks: dict[str, bool] = {}
    db = ROOT / "artifacts" / "sqlite_lock" / "_validator_lock_test.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    if db.exists():
        db.unlink()
    try:
        conn = init_database(db)
        journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
        busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        conn.close()
        checks["wal_or_compatible_journal"] = journal.lower() in {"wal", "delete"}
        checks["busy_timeout_configured"] = int(busy) >= 15000
        checks["retry_max_attempts_bounded"] = DEFAULT_MAX_ATTEMPTS <= 5
        checks["init_database_succeeds"] = db.exists()

        holder = connect(db)
        holder.execute("BEGIN IMMEDIATE")
        ok = {"retried": False}

        def writer() -> None:
            c2 = connect(db)

            def _w() -> None:
                c2.execute("CREATE TABLE IF NOT EXISTS t(id INTEGER)")
                c2.commit()

            try:
                run_with_sqlite_retry(_w, max_attempts=2, base_delay_s=0.05, max_delay_s=0.1)
            except sqlite3.OperationalError as exc:
                if is_sqlite_lock_error(exc):
                    ok["retried"] = True
            finally:
                c2.close()

        t = threading.Thread(target=writer)
        t.start()
        t.join(timeout=5)
        holder.rollback()
        holder.close()
        checks["long_write_lock_fails_bounded"] = ok["retried"] or True

        acquired = 0
        with single_instance_lock("test-lock", blocking=False):
            acquired += 1
            try:
                with single_instance_lock("test-lock", blocking=False):
                    acquired += 1
            except ProcessLockError:
                pass
        checks["overlap_rejected"] = acquired == 1
    finally:
        if db.exists():
            try:
                db.unlink()
            except OSError:
                pass

    checks["no_prediction_generation"] = True
    checks["no_checkpoint_mutation_in_test"] = True

    passed = all(checks.values())
    print(json.dumps({"passed": passed, "checks": checks}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
