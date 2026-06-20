"""Supplemental production audit — get_settings vs explicit env, cache rows."""
import os
import sqlite3
import sys

sys.path.insert(0, "/opt/worldcup-predictor")
os.chdir("/opt/worldcup-predictor")

from worldcup_predictor.config.settings import Settings, get_settings

s_default = get_settings()
s_prod = Settings(_env_file="/opt/worldcup-predictor/.env.production")
print(f"get_settings_sportmonks_configured: {s_default.sportmonks_configured}")
print(f"explicit_production_sportmonks_configured: {s_prod.sportmonks_configured}")

db = "/opt/worldcup-predictor/data/football_intelligence.db"
try:
    conn = sqlite3.connect(db)
    rows = conn.execute("SELECT COUNT(*) FROM sportmonks_fixture_enrichment").fetchone()[0]
    print(f"sportmonks_cache_rows: {rows}")
except Exception as exc:
    print(f"sportmonks_cache_rows: error {type(exc).__name__}")
