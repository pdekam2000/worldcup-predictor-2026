#!/usr/bin/env python3
"""Probe ECSE eligibility local vs production for parity forensic."""
import json, sqlite3, sys
from datetime import datetime, timezone
from pathlib import Path

def parse_ts(v):
    if not v: return None
    t = str(v).replace(' UTC','').replace('Z','+00:00')
    try:
        dt = datetime.fromisoformat(t)
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        try:
            return datetime.strptime(t[:19], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
        except ValueError:
            return None

def audit_db(path, label):
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    cols = [r[1] for r in c.execute('PRAGMA table_info(fixture_results)').fetchall()]
    reg_cols = ', fr.regulation_home_goals, fr.regulation_away_goals' if 'regulation_home_goals' in cols else ''
    rows = c.execute(f"""
        SELECT s.fixture_id, f.home_team, f.away_team, f.kickoff_utc, f.status,
               s.generated_at, s.is_frozen, s.id as snap_id,
               e.id as eval_id, e.final_score,
               fr.home_goals, fr.away_goals{reg_cols}
        FROM ecse_prediction_snapshots s
        JOIN fixtures f ON f.fixture_id=s.fixture_id
        LEFT JOIN ecse_prediction_evaluations e ON e.snapshot_id=s.id
        LEFT JOIN fixture_results fr ON fr.fixture_id=s.fixture_id
        WHERE s.is_frozen=1
        ORDER BY f.kickoff_utc
    """).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        ko = parse_ts(d['kickoff_utc'])
        gen = parse_ts(d['generated_at'])
        eligible = False
        reason = []
        if str(d['status']).upper() not in ('FT','AET','PEN'):
            reason.append('STATUS_NOT_FINAL')
        reg_h = d.get('regulation_home_goals') if 'regulation_home_goals' in d else None
        reg_a = d.get('regulation_away_goals') if 'regulation_away_goals' in d else None
        if reg_h is None: reg_h = d['home_goals']
        if reg_a is None: reg_a = d['away_goals']
        if reg_h is None or reg_a is None:
            reason.append('SCORE_MISSING')
        if ko and gen and gen >= ko:
            reason.append('SNAPSHOT_AFTER_KICKOFF')
        if not reason and d['is_frozen']:
            eligible = True
        d['eligible'] = eligible
        d['exclusion'] = reason or ['OK']
        d['actual'] = f"{reg_h}-{reg_a}" if reg_h is not None else None
        out.append(d)
    # also fixtures with eval but no snap
    all_fx = {x['fixture_id'] for x in out}
    print(json.dumps({'label': label, 'frozen_snapshots': len(out), 'eligible': sum(1 for x in out if x['eligible']), 'fixtures': out}, indent=2, default=str))

if __name__ == '__main__':
    audit_db(sys.argv[1], sys.argv[2] if len(sys.argv)>2 else 'db')
