#!/usr/bin/env python3
import json, sqlite3, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.outcomes.evaluation_score_policy import regulation_score_for_evaluation

ids = json.loads(Path(sys.argv[1]).read_text())
settings = get_settings()
conn = sqlite3.connect(settings.sqlite_path)
conn.row_factory = sqlite3.Row
out = []
for item in ids:
    fid = int(item["fixture_id"])
    fr = conn.execute("SELECT * FROM fixture_results WHERE fixture_id=?", (fid,)).fetchone()
    fx = conn.execute("SELECT home_team, away_team FROM fixtures WHERE fixture_id=?", (fid,)).fetchone()
    ev = conn.execute("SELECT rank_of_actual_score FROM ecse_prediction_evaluations WHERE fixture_id=?", (fid,)).fetchone()
    _, _, reg, _ = regulation_score_for_evaluation(dict(fr) if fr else None, dict(fx) if fx else None)
    out.append({"fixture_id": fid, "match": item["match"], "prod_regulation": reg, "prod_rank": ev["rank_of_actual_score"] if ev else None})
print(json.dumps(out))
