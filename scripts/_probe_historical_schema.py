#!/usr/bin/env python3
import sqlite3, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from worldcup_predictor.config.settings import get_settings
c=sqlite3.connect(get_settings().sqlite_path)
c.row_factory=sqlite3.Row
print('registry cols', [r[1] for r in c.execute('PRAGMA table_info(historical_fixture_registry)').fetchall()])
rows=c.execute("SELECT market, selection, COUNT(1) c FROM historical_csv_odds_prematch_clean WHERE market='ft_result' GROUP BY market, selection ORDER BY c DESC LIMIT 10").fetchall()
print('prematch selections', [dict(r) for r in rows])
rows=c.execute("SELECT DISTINCT selection FROM historical_csv_odds_imports WHERE market='ft_result' LIMIT 20").fetchall()
print('ft_result distinct selections imports', [r[0] for r in rows])
for t in ['external_historical_csv_files','external_historical_csv_raw_rows']:
    cols=[r[1] for r in c.execute(f'PRAGMA table_info({t})').fetchall()]
    n=c.execute(f'SELECT COUNT(1) FROM {t}').fetchone()[0]
    print(t, 'rows', n, 'cols', cols[:25])
    if t=='external_historical_csv_raw_rows' and n:
        import json
        sample=c.execute(f"SELECT raw_row_json, source_file FROM {t} WHERE source_file LIKE '%result%' OR source_file LIKE '%1x2%' LIMIT 3").fetchall()
        for s in sample:
            try:
                j=json.loads(s['raw_row_json'])
                print('raw sample file', s['source_file'], 'keys', list(j.keys())[:20], 'odds-ish', {k:j[k] for k in j if 'odd' in k.lower() or k.lower() in ('home','draw','away','h','d','a')})
            except Exception as e:
                print('parse err', e)
# production odds_snapshots finished fixtures count
n=c.execute("""
SELECT COUNT(DISTINCT f.fixture_id) FROM fixtures f
INNER JOIN fixture_results fr ON fr.fixture_id=f.fixture_id
INNER JOIN odds_snapshots o ON o.fixture_id=f.fixture_id
WHERE f.is_placeholder=0
""").fetchone()[0]
print('prod finished with odds_snapshots', n)
# ecse training dataset
try:
    cols=[r[1] for r in c.execute('PRAGMA table_info(ecse_training_dataset)').fetchall()]
    n=c.execute('SELECT COUNT(1) FROM ecse_training_dataset').fetchone()[0]
    nd=c.execute('SELECT COUNT(1) FROM ecse_training_dataset WHERE ft_draw_closing IS NOT NULL').fetchone()[0]
    print('ecse_training_dataset rows', n, 'with ft_draw_closing', nd, 'cols sample', cols[:15])
except Exception as e:
    print('ecse_training_dataset', e)
