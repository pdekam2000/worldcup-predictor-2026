#!/usr/bin/env python3
import sqlite3
from datetime import datetime
c=sqlite3.connect('data/football_intelligence.db')
c.row_factory=sqlite3.Row
rows=c.execute("""
SELECT COUNT(*) n FROM ecse_prediction_snapshots s
JOIN ecse_prediction_evaluations e ON e.snapshot_id=s.id
JOIN fixtures f ON f.fixture_id=s.fixture_id
JOIN fixture_results fr ON fr.fixture_id=s.fixture_id
WHERE s.is_frozen=1
  AND f.status IN ('FT','AET','PEN')
  AND datetime(replace(replace(s.generated_at,' UTC',''),'T',' ')) < datetime(f.kickoff_utc)
""").fetchone()
print('eligible', rows['n'])
for r in c.execute("""
SELECT s.fixture_id, f.home_team, f.away_team, e.final_score, e.rank_of_actual_score, s.top_1_score
FROM ecse_prediction_snapshots s
JOIN ecse_prediction_evaluations e ON e.snapshot_id=s.id
JOIN fixtures f ON f.fixture_id=s.fixture_id
WHERE s.is_frozen=1 LIMIT 20
"""):
    print(dict(r))
