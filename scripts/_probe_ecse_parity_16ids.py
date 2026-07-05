#!/usr/bin/env python3
import json, sqlite3, sys
from datetime import datetime, timezone

def parse_ts(v):
    if not v: return None
    t=str(v).replace(' UTC','').replace('Z','+00:00')
    try:
        dt=datetime.fromisoformat(t)
        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None

ids=[1562344,1565176,1562345,1564789,1565177,1567306,1567307,1567308,1562586,1567311,1567309,1567312,1565178,1565179,1567310,1567824]
c=sqlite3.connect('data/football_intelligence.db')
c.row_factory=sqlite3.Row
fr_cols={r[1] for r in c.execute('PRAGMA table_info(fixture_results)').fetchall()}
out=[]
for fid in ids:
    fx=c.execute('SELECT * FROM fixtures WHERE fixture_id=?',(fid,)).fetchone()
    snap=c.execute('SELECT * FROM ecse_prediction_snapshots WHERE fixture_id=? ORDER BY id DESC LIMIT 1',(fid,)).fetchone()
    fr=c.execute('SELECT * FROM fixture_results WHERE fixture_id=?',(fid,)).fetchone()
    ev=c.execute('SELECT * FROM ecse_prediction_evaluations WHERE fixture_id=?',(fid,)).fetchone()
    d={'fixture_id':fid,'has_fixture':fx is not None,'has_ecse':snap is not None,'has_result':fr is not None,'has_eval':ev is not None}
    if fx:
        d.update({'home_team':fx['home_team'],'away_team':fx['away_team'],'kickoff_utc':fx['kickoff_utc'],'status':fx['status']})
    if snap:
        d['generated_at']=snap['generated_at']
    reg_h=reg_a=None
    if fr:
        reg_h=fr['regulation_home_goals'] if 'regulation_home_goals' in fr_cols and fr['regulation_home_goals'] is not None else fr['home_goals']
        reg_a=fr['regulation_away_goals'] if 'regulation_away_goals' in fr_cols and fr['regulation_away_goals'] is not None else fr['away_goals']
        d['actual']=f"{reg_h}-{reg_a}" if reg_h is not None else None
    reasons=[]
    if not fx: reasons.append('MISSING_PRODUCTION_ECSE')
    elif not snap: reasons.append('MISSING_PRODUCTION_ECSE')
    elif str(fx['status']).upper() not in ('FT','AET','PEN'): reasons.append('STATUS_NOT_FINAL')
    elif reg_h is None: reasons.append('SCORE_MISSING')
    elif parse_ts(fx['kickoff_utc']) and parse_ts(snap['generated_at']) and parse_ts(snap['generated_at'])>=parse_ts(fx['kickoff_utc']):
        reasons.append('SNAPSHOT_AFTER_KICKOFF')
    d['eligible']=not reasons
    d['exclusion']=reasons or ['OK']
    out.append(d)
print(json.dumps(out,indent=2))
