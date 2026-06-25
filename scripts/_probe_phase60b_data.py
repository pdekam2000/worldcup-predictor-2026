import sqlite3
from pathlib import Path

db = Path("data/football_intelligence.db")
c = sqlite3.connect(db)
c.row_factory = sqlite3.Row
for t in ["fixtures", "fixture_results", "fixture_goal_events"]:
    n = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(t, n)
fin = c.execute(
    "SELECT COUNT(*) FROM fixtures WHERE status IN ('FT','AET','PEN','FINISHED')"
).fetchone()[0]
print("finished fixtures", fin)
with_events = c.execute("SELECT COUNT(DISTINCT fixture_id) FROM fixture_goal_events").fetchone()[0]
print("fixtures with goal events", with_events)
with_fgm = c.execute(
    "SELECT COUNT(*) FROM fixture_results WHERE first_goal_minute IS NOT NULL"
).fetchone()[0]
print("fixture_results with first_goal_minute", with_fgm)
rows = c.execute(
    """
    SELECT competition_key, COUNT(*) c FROM fixtures
    WHERE status IN ('FT','AET','PEN','FINISHED')
    GROUP BY competition_key ORDER BY c DESC LIMIT 15
    """
).fetchall()
print("top comps", [dict(r) for r in rows])
c.close()
for p in [
    "data/survival_dataset.parquet",
    "artifacts/survival_dataset.parquet",
    "artifacts/phase51h_egie_backtest.jsonl",
]:
    print(p, Path(p).is_file())
