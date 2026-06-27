#!/usr/bin/env python3
import json
import sqlite3
import urllib.request

APP = "/opt/worldcup-predictor"
db = sqlite3.connect(f"{APP}/data/football_intelligence.db")
db.row_factory = sqlite3.Row
for fid in [1489409, 1489410]:
    row = db.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fid,)).fetchone()
    print("fixture", fid, dict(row) if row else None)

base = "http://127.0.0.1:8000"
for fid in [1489409, 1489410]:
  try:
    p = json.loads(urllib.request.urlopen(f"{base}/api/predict/{fid}", timeout=15).read())
    print("predict", fid, "keys", list(p.keys())[:15])
  except Exception as e:
    print("predict err", fid, e)

try:
  m = json.loads(urllib.request.urlopen(f"{base}/api/matches?competition=world_cup_2026&include_summary=true&page_size=10", timeout=20).read())
  for r in (m.get("matches") or [])[:5]:
    print("match", r.get("fixture_id"), r.get("competition_key"), r.get("home_team_logo"), r.get("away_team_logo"))
except Exception as e:
  print("matches err", e)
