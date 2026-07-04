#!/usr/bin/env python3
"""MATCH-EVAL-1567310-1 — Post-sync result and evaluation inspection."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if not os.environ.get("APP_ENV") and (ROOT / ".env.production").is_file():
    os.environ.setdefault("APP_ENV", "production")

from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcomeResolver
from worldcup_predictor.config.settings import get_settings

FIXTURE_ID = 1567310


def main() -> int:
    settings = get_settings()
    conn = sqlite3.connect(settings.sqlite_path)
    conn.row_factory = sqlite3.Row
    fid = FIXTURE_ID

    fx = dict(conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fid,)).fetchone() or {})
    fr = conn.execute("SELECT * FROM fixture_results WHERE fixture_id=?", (fid,)).fetchone()
    frd = dict(fr) if fr else None

    wde_eval = conn.execute(
        "SELECT * FROM worldcup_prediction_evaluations WHERE fixture_id=?", (fid,)
    ).fetchone()
    ecse = conn.execute(
        "SELECT * FROM ecse_prediction_snapshots WHERE fixture_id=? ORDER BY id LIMIT 1", (fid,)
    ).fetchone()
    ecse_eval = None
    if ecse:
        ecse_eval = conn.execute(
            "SELECT * FROM ecse_prediction_evaluations WHERE snapshot_id=?", (ecse["id"],)
        ).fetchone()

    resolver = FixtureOutcomeResolver(settings)
    outcome = resolver.resolve(fid)

    counts = {
        "ecse_snapshots": conn.execute("SELECT COUNT(*) FROM ecse_prediction_snapshots").fetchone()[0],
        "ecse_evaluated": conn.execute("SELECT COUNT(*) FROM ecse_prediction_evaluations").fetchone()[0],
        "ecse_pending": conn.execute(
            """
            SELECT COUNT(*) FROM ecse_prediction_snapshots s
            LEFT JOIN ecse_prediction_evaluations e ON e.snapshot_id=s.id
            WHERE e.id IS NULL
            """
        ).fetchone()[0],
        "wde_stored": conn.execute("SELECT COUNT(*) FROM worldcup_stored_predictions").fetchone()[0],
        "wde_evaluated": conn.execute("SELECT COUNT(*) FROM worldcup_prediction_evaluations").fetchone()[0],
    }

    payload = {
        "fixture": fx,
        "fixture_result": frd,
        "outcome": {
            "is_finished": outcome.is_finished if outcome else False,
            "final_score": outcome.final_score if outcome else None,
            "fixture_status": outcome.fixture_status if outcome else None,
            "ht_score": getattr(outcome, "ht_score", None),
            "match_outcome_type": getattr(outcome, "match_outcome_type", None),
            "penalty_score": getattr(outcome, "penalty_score", None),
        },
        "wde_evaluation": dict(wde_eval) if wde_eval else None,
        "ecse_snapshot_id": ecse["id"] if ecse else None,
        "ecse_evaluation": dict(ecse_eval) if ecse_eval else None,
        "production_counts": counts,
    }
    conn.close()
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
