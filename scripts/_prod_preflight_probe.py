#!/usr/bin/env python3
import json, sqlite3, os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "football_intelligence.db"
ids = [1567306,1567307,1567308,1562586,1567311,1567309,1567312,1565178,1565179,1567310,1567824]
out = {"db_path": str(DB), "exists": DB.exists()}
if DB.exists():
    out["size_bytes"] = DB.stat().st_size
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    try:
        out["schema_version"] = c.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0]
    except Exception as e:
        out["schema_error"] = str(e)
    cols = [r[1] for r in c.execute("PRAGMA table_info(fixture_results)").fetchall()]
    out["fixture_results_columns"] = cols
    out["regulation_columns"] = "regulation_home_goals" in cols
    out["fixture_results_count"] = c.execute("SELECT COUNT(*) FROM fixture_results").fetchone()[0]
    cov = {}
    for i in ids:
        fx = c.execute("SELECT fixture_id, home_team, away_team, status FROM fixtures WHERE fixture_id=?", (i,)).fetchone()
        if "regulation_home_goals" in cols:
            fr = c.execute(
                "SELECT home_goals, away_goals, regulation_home_goals, regulation_away_goals, final_stage, penalty_score FROM fixture_results WHERE fixture_id=?",
                (i,),
            ).fetchone()
        else:
            fr = c.execute(
                "SELECT home_goals, away_goals, penalty_score FROM fixture_results WHERE fixture_id=?",
                (i,),
            ).fetchone()
        cov[i] = {"fixture": dict(fx) if fx else None, "result": dict(fr) if fr else None}
    out["target_coverage"] = cov
    c.close()
print(json.dumps(out, indent=2, default=str))
