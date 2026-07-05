#!/usr/bin/env python3
import json, sqlite3, sys
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from worldcup_predictor.config.settings import get_settings
c = sqlite3.connect(get_settings().sqlite_path)
c.row_factory = sqlite3.Row

# external raw - all oddsft keys
row = c.execute("SELECT raw_row_json FROM external_historical_csv_raw_rows LIMIT 1").fetchone()
j = json.loads(row["raw_row_json"])
odds_keys = sorted(k for k in j if "odds" in k.lower())
print("odds keys sample:", odds_keys)
print("ft odds:", {k: j[k] for k in j if k.startswith("oddsFT")})
print("goals:", j.get("goalsHomeFullTime"), j.get("goalsAwayFullTime"), "status:", j.get("status"))

# oddalerts_odds_history
print("\n=== oddalerts_odds_history markets/selections ===")
for r in c.execute("SELECT market, selection, COUNT(1) n FROM oddalerts_odds_history GROUP BY market, selection ORDER BY n DESC LIMIT 30"):
    print(dict(r))

# ecse_training_dataset
try:
    n = c.execute("SELECT COUNT(1) FROM ecse_training_dataset").fetchone()[0]
    nd = c.execute("SELECT COUNT(1) FROM ecse_training_dataset WHERE ft_draw_closing IS NOT NULL AND ft_draw_closing > 1").fetchone()[0]
    nh = c.execute("SELECT COUNT(1) FROM ecse_training_dataset WHERE ft_home_closing IS NOT NULL").fetchone()[0]
    print(f"\necse_training_dataset total={n} with draw={nd} with home={nh}")
    sample = c.execute("SELECT ft_home_closing, ft_draw_closing, ft_away_closing, home_goals, away_goals, league FROM ecse_training_dataset WHERE ft_draw_closing IS NOT NULL LIMIT 3").fetchall()
    for s in sample: print(dict(s))
except Exception as e:
    print("ecse", e)

# Count external rows with complete ft 1x2
print("\n=== external rows with oddsft_1/x/2 non-null ===")
# sample 5000 and count
complete = 0
ft_keys = Counter()
for row in c.execute("SELECT raw_row_json FROM external_historical_csv_raw_rows"):
    j = json.loads(row["raw_row_json"])
    h = j.get("oddsFT_1")
    d = j.get("oddsFT_X")
    a = j.get("oddsFT_2")
    gh = j.get("goalsHomeFullTime")
    ga = j.get("goalsAwayFullTime")
    if h and d and a:
        complete += 1
        try:
            if float(h) and float(d) and float(a) and gh is not None and ga is not None:
                ft_keys["valid"] += 1
        except: pass
print("rows with h/d/a keys present:", complete, "valid numeric with goals:", ft_keys["valid"])

# Quick exact match scan on external (limited)
TARGET = (1.75, 3.90, 4.40)
TOL = 0.005
exact = 0
close = 0
for row in c.execute("SELECT raw_row_json FROM external_historical_csv_raw_rows"):
    j = json.loads(row["raw_row_json"])
    try:
        oh = float(j.get("oddsFT_1") or 0)
        od = float(j.get("oddsFT_X") or 0)
        oa = float(j.get("oddsFT_2") or 0)
        gh = j.get("goalsHomeFullTime")
        ga = j.get("goalsAwayFullTime")
        if not (oh > 1 and od > 1 and oa > 1):
            continue
        if gh is None or ga is None or str(gh).strip() == "" or str(ga).strip() == "":
            continue
        int(float(gh)); int(float(ga))
    except (TypeError, ValueError):
        continue
    for fav, draw, dog, orient in [(oh, od, oa, "home"), (oa, od, oh, "away")]:
        if abs(fav-TARGET[0])<=TOL and abs(draw-TARGET[1])<=TOL and abs(dog-TARGET[2])<=TOL:
            exact += 1
            break
    for fav, draw, dog in [(oh, od, oa), (oa, od, oh)]:
        if 1.70<=fav<=1.80 and 3.80<=draw<=4.00 and 4.25<=dog<=4.60:
            close += 1
            break
print(f"external exact matches: {exact}, close: {close}")
