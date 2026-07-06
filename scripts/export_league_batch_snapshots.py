#!/usr/bin/env python3
"""Export frozen league batch snapshots for production import (idempotent)."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BATCH_IDS = ("tomorrow_4_league_20260707", "domestic_league_control_20260712")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/football_intelligence.db")
    parser.add_argument("--out", default="artifacts/league_batch_snapshot_export.json")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    snapshots = [
        dict(r)
        for r in conn.execute(
            """
            SELECT batch_id, target_date, fixture_id, competition_key, competition_type, kickoff_utc,
                   snapshot_json, prediction_timestamp, is_frozen
            FROM owner_league_batch_snapshots
            WHERE batch_id IN (?, ?) AND is_frozen=1
            """,
            BATCH_IDS,
        )
    ]
    fixture_ids = sorted({int(s["fixture_id"]) for s in snapshots})
    fixtures = [
        dict(r)
        for r in conn.execute(
            f"SELECT * FROM fixtures WHERE fixture_id IN ({','.join('?' * len(fixture_ids))})",
            fixture_ids,
        )
    ]
    conn.close()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "batch_ids": list(BATCH_IDS),
        "snapshot_count": len(snapshots),
        "snapshots": snapshots,
        "fixtures": fixtures,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(out), "snapshots": len(snapshots), "fixtures": len(fixtures)}, indent=2))
    return 0 if snapshots else 1


if __name__ == "__main__":
    raise SystemExit(main())
