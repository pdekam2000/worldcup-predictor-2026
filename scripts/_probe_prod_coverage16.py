#!/usr/bin/env python3
import sqlite3
ids=[1562344,1565176,1562345,1564789,1565177,1567306,1567307,1567308,1562586,1567311,1567309,1567312,1565178,1565179,1567310,1567824]
c=sqlite3.connect('data/football_intelligence.db')
for label, q in [('fixtures','SELECT 1 FROM fixtures WHERE fixture_id=?'),('results','SELECT 1 FROM fixture_results WHERE fixture_id=?'),('ecse','SELECT 1 FROM ecse_prediction_snapshots WHERE fixture_id=?')]:
    print(label, sum(1 for i in ids if c.execute(q,(i,)).fetchone()))
