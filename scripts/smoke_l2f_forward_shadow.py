#!/usr/bin/env python3
"""Controlled production smoke for L2-F forward shadow (owner fixtures only)."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.research.infra_l2f_forward.forward_hook import maybe_run_l2f_forward_shadow
from worldcup_predictor.research.football_strength_foundation.constants import SHADOW_TABLE


def main() -> int:
    fi = Path(sys.argv[1] if len(sys.argv) > 1 else "data/football_intelligence.db")
    limit = int(sys.argv[2] if len(sys.argv) > 2 else 3)
    out_path = Path(sys.argv[3] if len(sys.argv) > 3 else "l2f_forward_shadow_smoke.json")
    conn = sqlite3.connect(fi)
    conn.row_factory = sqlite3.Row
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    rows = conn.execute(
        """
        SELECT f.fixture_id, f.home_team, f.away_team, f.kickoff_utc, e.lambda_home, e.lambda_away
        FROM fixtures f
        JOIN ecse_prediction_snapshots e ON e.fixture_id = f.fixture_id
        WHERE f.kickoff_utc > ?
          AND f.status IN ('NS','TBD','SCHEDULED')
          AND e.lambda_home IS NOT NULL AND e.lambda_away IS NOT NULL
        ORDER BY f.kickoff_utc ASC
        LIMIT ?
        """,
        (now, limit),
    ).fetchall()
    results = []
    for r in rows:
        fid = int(r["fixture_id"])
        freeze_meta = {
            "capture_status": "created",
            "freeze_id": f"smoke-l2f-{fid}",
            "prediction_scope": "owner_shadow",
            "quarantined": False,
            "conflict_detected": False,
        }
        before = conn.execute(
            f"SELECT COUNT(*) AS n FROM {SHADOW_TABLE} WHERE fixture_id=?",
            (fid,),
        ).fetchone()
        before_n = int(before["n"]) if before else 0
        meta = maybe_run_l2f_forward_shadow(
            conn=conn,
            fixture_id=fid,
            freeze_meta=freeze_meta,
            prediction_scope="owner_shadow",
            settings=None,
        )
        # second call for idempotency
        meta2 = maybe_run_l2f_forward_shadow(
            conn=conn,
            fixture_id=fid,
            freeze_meta=freeze_meta,
            prediction_scope="owner_shadow",
            settings=None,
        )
        after = conn.execute(
            f"""
            SELECT model_id, COUNT(*) AS n FROM {SHADOW_TABLE}
            WHERE fixture_id=? GROUP BY model_id
            """,
            (fid,),
        ).fetchall()
        results.append(
            {
                "fixture_id": fid,
                "home": r["home_team"],
                "away": r["away_team"],
                "kickoff_utc": r["kickoff_utc"],
                "before_shadow_rows": before_n,
                "first": meta,
                "second": meta2,
                "models": {row["model_id"]: row["n"] for row in after},
            }
        )
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fi_db": str(fi),
        "n_fixtures": len(results),
        "results": results,
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"n": len(results), "out": str(out_path)}, indent=2))
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
