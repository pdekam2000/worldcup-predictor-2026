#!/usr/bin/env python3
import json, sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
conn = sqlite3.connect('data/football_intelligence.db')
conn.row_factory = sqlite3.Row
now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
rows = conn.execute("""
SELECT f.fixture_id, f.home_team, f.away_team, f.kickoff_utc, f.status, f.round_name,
  EXISTS(SELECT 1 FROM worldcup_stored_predictions w WHERE w.fixture_id=f.fixture_id) as has_wde,
  EXISTS(SELECT 1 FROM ecse_prediction_snapshots e WHERE e.fixture_id=f.fixture_id) as has_ecse
FROM fixtures f
WHERE f.competition_key='world_cup_2026' AND f.is_placeholder=0
  AND f.status IN ('NS','TBD','SCHEDULED','TIMED')
  AND f.kickoff_utc > ?
ORDER BY f.kickoff_utc ASC LIMIT 10
""", (now,)).fetchall()
out=[]
for r in rows:
    d=dict(r)
    try:
        dt=datetime.fromisoformat(str(d['kickoff_utc']).replace('Z','+00:00'))
        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        d['kickoff_vienna']=dt.astimezone(ZoneInfo('Europe/Vienna')).strftime('%Y-%m-%d %H:%M %Z')
    except Exception as e:
        d['kickoff_vienna']=str(e)
    out.append(d)
print(json.dumps({'now_utc':now,'count':len(out),'fixtures':out}, indent=2))
