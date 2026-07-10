#!/usr/bin/env python3
"""Pre-automation evaluation DB integrity audit (read-only)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.forward_evaluation.db import connect_eval_db, eval_db_path

KNOWN_FIXTURES = (1494204, 1494205, 1494208)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def main() -> int:
    path = eval_db_path()
    conn = connect_eval_db()
    issues: list[str] = []
    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        frozen_n = conn.execute("SELECT COUNT(*) FROM frozen_predictions").fetchone()[0]
        pending_n = conn.execute(
            "SELECT COUNT(*) FROM frozen_predictions WHERE evaluation_status='PENDING'"
        ).fetchone()[0]
        rank_n = conn.execute("SELECT COUNT(*) FROM exact_score_rankings").fetchone()[0]
        orphans = conn.execute(
            """
            SELECT COUNT(*) FROM exact_score_rankings r
            LEFT JOIN frozen_predictions f ON f.prediction_id = r.prediction_id
            WHERE f.prediction_id IS NULL
            """
        ).fetchone()[0]
        dup_hash = conn.execute(
            """
            SELECT fixture_id, payload_hash, COUNT(*) AS c FROM frozen_predictions
            GROUP BY fixture_id, payload_hash HAVING c > 1
            """
        ).fetchall()

        known_rows = conn.execute(
            f"SELECT fixture_id, evaluation_status, payload_hash, kickoff, frozen_at FROM frozen_predictions WHERE fixture_id IN ({','.join('?'*3)})",
            list(KNOWN_FIXTURES),
        ).fetchall()

        rank_gaps: list[dict] = []
        for row in known_rows:
            pid = conn.execute(
                "SELECT prediction_id FROM frozen_predictions WHERE fixture_id=? ORDER BY frozen_at DESC LIMIT 1",
                (row["fixture_id"],),
            ).fetchone()
            if not pid:
                continue
            ranks = conn.execute(
                "SELECT rank FROM exact_score_rankings WHERE prediction_id=? ORDER BY rank",
                (pid["prediction_id"],),
            ).fetchall()
            have = {int(r["rank"]) for r in ranks}
            missing = [i for i in range(1, 6) if i not in have]
            if missing:
                rank_gaps.append({"fixture_id": row["fixture_id"], "missing_ranks": missing})

        post_kickoff: list[dict] = []
        for row in conn.execute("SELECT fixture_id, kickoff, frozen_at FROM frozen_predictions").fetchall():
            ko = _parse_dt(row["kickoff"])
            fr = _parse_dt(row["frozen_at"])
            if ko and fr and fr > ko:
                post_kickoff.append({"fixture_id": row["fixture_id"], "kickoff": row["kickoff"], "frozen_at": row["frozen_at"]})

        if orphans:
            issues.append(f"orphan_rank_rows:{orphans}")
        if dup_hash:
            issues.append(f"duplicate_payload_hash_rows:{len(dup_hash)}")
        if rank_gaps:
            issues.append(f"missing_top5_ranks:{rank_gaps}")
        if post_kickoff:
            issues.append(f"post_kickoff_freeze:{post_kickoff}")

        sha = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        report = {
            "db_path": str(path),
            "db_checksum_sha256": sha,
            "tables": tables,
            "frozen_count": frozen_n,
            "pending_count": pending_n,
            "rank_row_count": rank_n,
            "known_fixtures": [dict(r) for r in known_rows],
            "orphan_rank_rows": orphans,
            "duplicate_payload_groups": len(dup_hash),
            "rank_gaps": rank_gaps,
            "post_kickoff_freeze_violations": post_kickoff,
            "integrity_pass": len(issues) == 0,
            "issues": issues,
        }
        print(json.dumps(report, indent=2, default=str))
        return 0 if report["integrity_pass"] else 2
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
