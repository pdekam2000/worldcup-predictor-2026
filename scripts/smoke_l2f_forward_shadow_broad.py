#!/usr/bin/env python3
"""Broader controlled smoke: prefer future fixtures; else backfill-safe recent ECSE fixtures."""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/opt/worldcup-predictor")
from worldcup_predictor.research.infra_l2f_forward.forward_hook import maybe_run_l2f_forward_shadow
from worldcup_predictor.research.football_strength_foundation.constants import SHADOW_TABLE

fi = Path(sys.argv[1] if len(sys.argv) > 1 else "data/football_intelligence.db")
limit = int(sys.argv[2] if len(sys.argv) > 2 else 3)
out_path = Path(sys.argv[3] if len(sys.argv) > 3 else "/tmp/l2f_smoke.json")
conn = sqlite3.connect(fi)
conn.row_factory = sqlite3.Row
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
rows = conn.execute(
    """
    SELECT f.fixture_id, f.home_team, f.away_team, f.kickoff_utc, e.lambda_home, e.lambda_away
    FROM fixtures f
    JOIN ecse_prediction_snapshots e ON e.fixture_id = f.fixture_id
    WHERE e.lambda_home IS NOT NULL AND e.lambda_away IS NOT NULL
      AND f.kickoff_utc > ?
    ORDER BY f.kickoff_utc ASC LIMIT ?
    """,
    (now, limit),
).fetchall()
backfill = False
if not rows:
    backfill = True
    rows = conn.execute(
        """
        SELECT f.fixture_id, f.home_team, f.away_team, f.kickoff_utc, e.lambda_home, e.lambda_away
        FROM fixtures f
        JOIN ecse_prediction_snapshots e ON e.fixture_id = f.fixture_id
        WHERE e.lambda_home IS NOT NULL AND e.lambda_away IS NOT NULL
        ORDER BY e.id DESC LIMIT ?
        """,
        (limit,),
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
    before = conn.execute(f"SELECT COUNT(*) n FROM {SHADOW_TABLE} WHERE fixture_id=?", (fid,)).fetchone()["n"]
    first = maybe_run_l2f_forward_shadow(
        conn=conn,
        fixture_id=fid,
        freeze_meta=freeze_meta,
        prediction_scope="owner_shadow",
        settings=None,
        backfill=backfill,
    )
    second = maybe_run_l2f_forward_shadow(
        conn=conn,
        fixture_id=fid,
        freeze_meta=freeze_meta,
        prediction_scope="owner_shadow",
        settings=None,
        backfill=backfill,
    )
    models = {
        row["model_id"]: row["n"]
        for row in conn.execute(
            f"SELECT model_id, COUNT(*) n FROM {SHADOW_TABLE} WHERE fixture_id=? GROUP BY model_id",
            (fid,),
        )
    }
    lam = sum(n for m, n in models.items() if m.startswith("LAMBDA_V2_"))
    ex = sum(n for m, n in models.items() if m.startswith("EXACT_V2_"))
    results.append(
        {
            "fixture_id": fid,
            "home": r["home_team"],
            "away": r["away_team"],
            "kickoff_utc": r["kickoff_utc"],
            "before_shadow_rows": before,
            "first": first,
            "second": second,
            "lambda_v2_rows": lam,
            "exact_v2_rows": ex,
            "models": models,
        }
    )

payload = {
    "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "backfill_mode": backfill,
    "n_fixtures": len(results),
    "results": results,
    "totals": {
        "lambda_v2_rows": sum(r["lambda_v2_rows"] for r in results),
        "exact_v2_rows": sum(r["exact_v2_rows"] for r in results),
    },
}
out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"n": len(results), "backfill": backfill, "totals": payload["totals"], "out": str(out_path)}, indent=2))
conn.close()
