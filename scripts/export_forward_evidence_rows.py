#!/usr/bin/env python3
"""Export frozen forward evaluation evidence rows to JSON (read-only)."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--fixture-ids", required=True, help="comma-separated")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    ids = [int(x.strip()) for x in args.fixture_ids.split(",") if x.strip()]
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    ph = ",".join("?" * len(ids))
    frozen = [dict(r) for r in conn.execute(f"SELECT * FROM frozen_predictions WHERE fixture_id IN ({ph})", ids)]
    ranks = [dict(r) for r in conn.execute(f"SELECT * FROM exact_score_rankings WHERE fixture_id IN ({ph})", ids)]
    conn.close()
    payload = {"fixture_ids": ids, "frozen_predictions": frozen, "exact_score_rankings": ranks}
    Path(args.out).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"exported_frozen": len(frozen), "exported_ranks": len(ranks), "out": args.out}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
