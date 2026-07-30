#!/usr/bin/env python3
"""Apply additive football-strength shadow migrations on production FI DB."""
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path("/opt/worldcup-predictor")
DB = ROOT / "data" / "football_intelligence.db"
MIGS = [
    ROOT / "migrations" / "research_football_strength_lambda_v2.sql",
    ROOT / "migrations" / "research_alternate_totals_capture_status.sql",
]
NEED = {
    "derived_historical_team_form_snapshots",
    "totals_market_shadow_snapshots",
    "lambda_v2_shadow_outputs",
    "alternate_totals_capture_status",
}


def strip_comments(sql: str) -> str:
    out = []
    for line in sql.splitlines():
        if line.strip().startswith("--"):
            continue
        out.append(line)
    return "\n".join(out)


def main() -> int:
    if not DB.exists():
        raise SystemExit(f"missing db: {DB}")
    conn = sqlite3.connect(DB)
    for path in MIGS:
        raw = path.read_text(encoding="utf-8")
        body = strip_comments(raw).lower()
        for bad in ("drop table", "delete from frozen", "update frozen"):
            if bad in body:
                raise SystemExit(f"unsafe DDL in {path.name}: {bad}")
        if "create table if not exists" not in body:
            raise SystemExit(f"missing CREATE TABLE IF NOT EXISTS in {path.name}")
        conn.executescript(raw)
        print(f"applied={path.name}")
    have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    missing = sorted(NEED - have)
    if missing:
        raise SystemExit(f"missing tables: {missing}")
    conn.close()
    print("migrations_applied=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
