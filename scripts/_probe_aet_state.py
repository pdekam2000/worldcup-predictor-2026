#!/usr/bin/env python3
import json, sqlite3, sys
c = sqlite3.connect(sys.argv[1] if len(sys.argv) > 1 else "data/football_intelligence.db")
c.row_factory = sqlite3.Row
cols = [r[1] for r in c.execute("PRAGMA table_info(fixture_results)").fetchall()]
ver = c.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
out = {"schema_version": ver[0] if ver else None, "regulation_columns": "regulation_home_goals" in cols, "fixtures": []}
for fid in [1567308, 1565179, 1562344, 1565176]:
    r = c.execute("SELECT * FROM fixture_results WHERE fixture_id=?", (fid,)).fetchone()
    e = c.execute("SELECT final_score, rank_of_actual_score, top5_correct FROM ecse_prediction_evaluations WHERE fixture_id=?", (fid,)).fetchone()
    f = c.execute("SELECT status, home_team, away_team FROM fixtures WHERE fixture_id=?", (fid,)).fetchone()
    out["fixtures"].append({"fixture_id": fid, "fixture": dict(f) if f else None, "result": dict(r) if r else None, "ecse_eval": dict(e) if e else None})
print(json.dumps(out, indent=2, default=str))
