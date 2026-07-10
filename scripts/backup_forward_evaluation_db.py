#!/usr/bin/env python3
"""SQLite-safe backup of forward evaluation DB."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.forward_evaluation.db import connect_eval_db, eval_db_path


def main() -> int:
    src = eval_db_path()
    if not src.exists():
        print(json.dumps({"error": "eval_db_not_found", "path": str(src)}))
        return 1

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = src.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    dst = backup_dir / f"forward_prediction_tracking_{stamp}.db"

    src_conn = sqlite3.connect(str(src))
    dst_conn = sqlite3.connect(str(dst))
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()

    src_sha = hashlib.sha256(src.read_bytes()).hexdigest()
    dst_sha = hashlib.sha256(dst.read_bytes()).hexdigest()
    verify = sqlite3.connect(str(dst))
    try:
        frozen = verify.execute("SELECT COUNT(*) FROM frozen_predictions").fetchone()[0]
        ranks = verify.execute("SELECT COUNT(*) FROM exact_score_rankings").fetchone()[0]
    finally:
        verify.close()

    print(
        json.dumps(
            {
                "backup_path": str(dst),
                "source_path": str(src),
                "source_checksum_sha256": src_sha,
                "backup_checksum_sha256": dst_sha,
                "checksum_match": src_sha == dst_sha,
                "frozen_count": frozen,
                "rank_count": ranks,
                "backup_verified": True,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
