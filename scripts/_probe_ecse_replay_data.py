#!/usr/bin/env python3
"""Probe ECSE historical replay data availability from 2023."""
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from worldcup_predictor.config.settings import get_settings

c = sqlite3.connect(get_settings().sqlite_path)
c.row_factory = sqlite3.Row

def has(t):
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone() is not None

for t in ["ecse_lambda_features", "ecse_training_dataset", "ecse_prediction_snapshots", "ecse_score_distributions", "external_historical_csv_raw_rows", "historical_fixture_registry", "historical_fixture_results", "xg_snapshots", "worldcup_stored_predictions"]:
    print(t, "exists" if has(t) else "MISSING", end="")
    if has(t):
        print(" rows", c.execute(f"SELECT COUNT(1) FROM {t}").fetchone()[0])
    else:
        print()

# external from 2023 with complete odds+scores
n = 0
by_league = Counter()
by_year = Counter()
sample = 0
for row in c.execute("SELECT raw_row_json, source_file FROM external_historical_csv_raw_rows"):
    j = json.loads(row["raw_row_json"])
    d = str(j.get("eventDate") or "")[:10]
    if not d or d < "2023-01-01":
        continue
    oh, od, oa = j.get("oddsFT_1"), j.get("oddsFT_X"), j.get("oddsFT_2")
    gh, ga = j.get("goalsHomeFullTime"), j.get("goalsAwayFullTime")
    if not all([oh, od, oa, gh is not None and str(gh) != "", ga is not None and str(ga) != ""]):
        continue
    try:
        float(oh); float(od); float(oa); int(float(gh)); int(float(ga))
    except (TypeError, ValueError):
        continue
    n += 1
    by_league[j.get("league") or "?"] += 1
    by_year[d[:4]] += 1

print("external eligible 2023+:", n)
print("years", dict(sorted(by_year.items())))
print("top leagues", by_league.most_common(15))

if has("ecse_prediction_snapshots"):
    rows = c.execute("""
        SELECT COUNT(1) FROM ecse_prediction_snapshots ec
        JOIN fixture_results fr ON fr.fixture_id = ec.fixture_id
        JOIN fixtures f ON f.fixture_id = ec.fixture_id
        WHERE f.kickoff_utc >= '2023-01-01'
    """).fetchone()[0]
    print("ecse_prediction_snapshots finished 2023+:", rows)

if has("ecse_lambda_features"):
    rows = c.execute("""
        SELECT COUNT(1) FROM ecse_lambda_features l
        JOIN historical_fixture_results r ON r.registry_fixture_id = l.registry_fixture_id
        JOIN historical_fixture_registry reg ON reg.registry_fixture_id = l.registry_fixture_id
        WHERE reg.kickoff_utc >= '2023-01-01'
    """).fetchone()[0]
    print("ecse_lambda_features 2023+:", rows)
