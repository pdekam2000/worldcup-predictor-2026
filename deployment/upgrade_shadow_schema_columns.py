#!/usr/bin/env python3
"""CLI wrapper for additive shadow schema column upgrades."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.research.football_strength_foundation.schema_upgrade import upgrade_shadow_tables


def main() -> int:
    db = Path(sys.argv[1] if len(sys.argv) > 1 else "/opt/worldcup-predictor/data/football_intelligence.db")
    conn = sqlite3.connect(db)
    applied = upgrade_shadow_tables(conn)
    print("applied", applied)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
