#!/usr/bin/env python3
"""Quick probe of target knockout fixtures — production or local DB."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TARGET_IDS = [
    1567306, 1567307, 1567308, 1562586, 1567311,
    1567309, 1567312, 1565178, 1565179, 1567310, 1567824,
]


def _db_path() -> str:
    import os
    p = os.environ.get("SQLITE_PATH") or str(ROOT / "data" / "football_intelligence.db")
    return p


def main() -> int:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    out = []
    for fid in TARGET_IDS:
        row: dict = {"fixture_id": fid}
        f = conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fid,)).fetchone()
        r = conn.execute("SELECT * FROM fixture_results WHERE fixture_id=?", (fid,)).fetchone()
        wde = conn.execute(
            "SELECT fixture_id, predicted_at, payload_json FROM worldcup_stored_predictions WHERE fixture_id=?",
            (fid,),
        ).fetchone()
        ecse_cols = [r[1] for r in conn.execute("PRAGMA table_info(ecse_prediction_snapshots)").fetchall()]
        ecse_sel = ["id", "generated_at", "is_frozen", "top_1_score"]
        for col in ("top_3_scores_json", "top_5_scores_json", "top_3_scores", "top_5_scores_json", "raw_features_json"):
            if col in ecse_cols and col not in ecse_sel:
                ecse_sel.append(col)
        ecse = conn.execute(
            f"SELECT {', '.join(ecse_sel)} FROM ecse_prediction_snapshots WHERE fixture_id=? ORDER BY id DESC LIMIT 1",
            (fid,),
        ).fetchone()
        wde_ev = conn.execute(
            "SELECT * FROM worldcup_prediction_evaluations WHERE fixture_id=?", (fid,)
        ).fetchall()
        ecse_ev = conn.execute(
            "SELECT * FROM ecse_prediction_evaluations WHERE fixture_id=?", (fid,)
        ).fetchall()
        row["fixture"] = dict(f) if f else None
        row["result"] = dict(r) if r else None
        if wde:
            row["wde"] = {
                "predicted_at": wde["predicted_at"],
                "has_payload": bool(wde["payload_json"]),
            }
        else:
            row["wde"] = None
        if ecse:
            ecse_d = dict(ecse)
            for k in ("top_3_scores_json", "top_5_scores_json", "raw_features_json"):
                if ecse_d.get(k):
                    try:
                        ecse_d[k] = json.loads(ecse_d[k])
                    except json.JSONDecodeError:
                        pass
            row["ecse"] = ecse_d
        else:
            row["ecse"] = None
        row["wde_evaluations"] = [dict(e) for e in wde_ev]
        row["ecse_evaluations"] = [dict(e) for e in ecse_ev]
        out.append(row)
    conn.close()
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
