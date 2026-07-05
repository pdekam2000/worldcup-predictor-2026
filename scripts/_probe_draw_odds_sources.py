#!/usr/bin/env python3
"""Probe all potential 1X2 draw odds sources in historical DB."""
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

# 1. prematch_clean selections
print("=== historical_csv_odds_prematch_clean ft_result selections ===")
for r in c.execute(
    "SELECT selection, COUNT(1) n FROM historical_csv_odds_prematch_clean WHERE market='ft_result' GROUP BY selection"
):
    print(dict(r))

# 2. imports selections for ft_result
print("\n=== historical_csv_odds_imports ft_result selections ===")
for r in c.execute(
    "SELECT selection, COUNT(1) n FROM historical_csv_odds_imports WHERE market='ft_result' GROUP BY selection ORDER BY n DESC"
):
    print(dict(r))

# 3. Check if draw exists in other markets we could NOT use
print("\n=== double_chance selections sample ===")
for r in c.execute(
    "SELECT selection, COUNT(1) n FROM historical_csv_odds_prematch_clean WHERE market='double_chance' GROUP BY selection LIMIT 10"
):
    print(dict(r))

# 4. external raw rows - sample keys from various source files
print("\n=== external_historical_csv_raw_rows source_file samples ===")
files = c.execute(
    """
    SELECT source_file, COUNT(1) n
    FROM external_historical_csv_raw_rows
    GROUP BY source_file
    ORDER BY n DESC
    LIMIT 15
    """
).fetchall()
for f in files:
    print(f["source_file"], f["n"])

print("\n=== raw row JSON key patterns ===")
key_counter: Counter = Counter()
draw_key_samples = []
for row in c.execute(
    "SELECT raw_row_json, source_file FROM external_historical_csv_raw_rows LIMIT 500"
):
    try:
        j = json.loads(row["raw_row_json"])
        for k in j.keys():
            key_counter[k.lower()] += 1
        drawish = {k: j[k] for k in j if any(x in k.lower() for x in ("draw", "d", "x", "odd", "home", "away", "result", "score", "goal"))}
        if any("draw" in k.lower() for k in j) and len(draw_key_samples) < 3:
            draw_key_samples.append((row["source_file"], drawish))
    except Exception:
        pass
print("top keys:", key_counter.most_common(30))
for sf, d in draw_key_samples:
    print("draw sample file:", sf, d)

# 5. Check historical_fixture_registry + results join count
print("\n=== registry with results ===")
r = c.execute(
    """
    SELECT COUNT(1) FROM historical_fixture_registry r
    INNER JOIN historical_fixture_results res ON res.registry_fixture_id = r.registry_fixture_id
    WHERE res.home_goals IS NOT NULL AND res.away_goals IS NOT NULL
    """
).fetchone()[0]
print("finished with scores:", r)

# 6. Try pivot from imports with draw if any
print("\n=== imports pivot test (any draw?) ===")
try:
    n = c.execute(
        """
        SELECT COUNT(DISTINCT match_key) FROM historical_csv_odds_imports
        WHERE market='ft_result' AND LOWER(selection) IN ('draw','x','tie')
        """
    ).fetchone()[0]
    print("fixtures with draw in imports:", n)
except Exception as e:
    print("err", e)

# 7. oddalerts tables
for t in ["oddalerts_odds_history", "historical_odds_snapshots", "historical_match_odds"]:
    try:
        n = c.execute(f"SELECT COUNT(1) FROM {t}").fetchone()[0]
        cols = [x[1] for x in c.execute(f"PRAGMA table_info({t})").fetchall()]
        print(f"\n=== {t} rows={n} cols={cols[:20]} ===")
    except Exception as e:
        print(f"\n=== {t}: {e} ===")

# 8. Sample imports raw_json for ft_result home row - look for draw embedded
print("\n=== imports raw_json sample (ft_result home) ===")
row = c.execute(
    """
    SELECT raw_json, source_file, selection, closing_odds
    FROM historical_csv_odds_imports
    WHERE market='ft_result' AND selection='home'
    LIMIT 1
    """
).fetchone()
if row:
    try:
        j = json.loads(row["raw_json"])
        print("source", row["source_file"], "keys", list(j.keys())[:25])
        print("selectionsque", {k: j[k] for k in j if any(x in k.lower() for x in ("draw", "home", "away", "odd", "close", "open"))})
    except Exception as e:
        print("parse err", e, row["raw_json"][:200])

# 9. Check if separate CSV path has draw - first_half_winner has draw
print("\n=== first_half_winner selections in prematch_clean ===")
for r in c.execute(
    "SELECT selection, COUNT(1) n FROM historical_csv_odds_prematch_clean WHERE market='first_half_winner' GROUP BY selection"
):
    print(dict(r))
