import sqlite3
conn = sqlite3.connect("data/football_intelligence.db")
conn.row_factory = sqlite3.Row
print("team_mappings count", conn.execute("SELECT COUNT(*) c FROM team_mappings").fetchone()["c"])
rows = conn.execute("SELECT api_team_id, team_name, competition_key FROM team_mappings LIMIT 5").fetchall()
for r in rows:
    print(dict(r))
print("enrichment with lineups", conn.execute("SELECT COUNT(*) c FROM fixture_enrichment WHERE lineups_json IS NOT NULL AND lineups_json != ''").fetchone()["c"])
row = conn.execute("SELECT fixture_id, home_team_id, away_team_id FROM fixtures WHERE home_team_id IS NOT NULL LIMIT 3").fetchall()
for r in row:
    print(dict(r))
