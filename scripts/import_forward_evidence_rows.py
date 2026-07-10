#!/usr/bin/env python3
"""Import frozen forward evaluation evidence from JSON (idempotent)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.forward_evaluation.db import connect_eval_db


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="infile", required=True)
    args = parser.parse_args()

    data = json.loads(Path(args.infile).read_text(encoding="utf-8"))
    conn = connect_eval_db()
    imported_frozen = 0
    imported_ranks = 0
    try:
        for row in data.get("frozen_predictions") or []:
            cols = list(row.keys())
            placeholders = ",".join("?" * len(cols))
            sql = f"INSERT OR IGNORE INTO frozen_predictions ({','.join(cols)}) VALUES ({placeholders})"
            cur = conn.execute(sql, [row[c] for c in cols])
            if cur.rowcount:
                imported_frozen += 1
        for row in data.get("exact_score_rankings") or []:
            cols = list(row.keys())
            placeholders = ",".join("?" * len(cols))
            sql = f"INSERT OR IGNORE INTO exact_score_rankings ({','.join(cols)}) VALUES ({placeholders})"
            cur = conn.execute(sql, [row[c] for c in cols])
            if cur.rowcount:
                imported_ranks += 1
        conn.commit()
    finally:
        conn.close()
    print(json.dumps({"imported_frozen": imported_frozen, "imported_ranks": imported_ranks}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
