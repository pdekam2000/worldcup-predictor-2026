import sqlite3
conn = sqlite3.connect("data/football_intelligence.db")
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT fixture_id, home_team, away_team, home_team_id, away_team_id, status "
    "FROM fixtures WHERE competition_key='world_cup_2026' AND status IN ('NS','TIMED') LIMIT 5"
).fetchall()
for r in rows:
    print(dict(r))
