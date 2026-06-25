"""Dump stored prediction for fixture 1489393."""
import json
import sqlite3
from pathlib import Path

DB = Path("/opt/worldcup-predictor/data/football_intelligence.db")
fid = 1489393
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# predictions table schema
cols = [r[1] for r in conn.execute("PRAGMA table_info(predictions)").fetchall()]
print("columns:", cols)

row = conn.execute(
    "SELECT * FROM worldcup_stored_predictions WHERE fixture_id=? ORDER BY updated_at DESC LIMIT 1",
    (fid,),
).fetchone()
if not row:
    print("NO ROW")
else:
    d = dict(row)
    payload = json.loads(d.get("payload_json") or "{}")
    out = {
        "fixture_id": d.get("fixture_id"),
        "updated_at": d.get("updated_at"),
        "generated_at": payload.get("generated_at"),
        "generated_by": payload.get("generated_by"),
        "cache_source": payload.get("cache_source"),
        "prediction_engine_version": payload.get("prediction_engine_version"),
        "is_placeholder": payload.get("is_placeholder"),
        "confidence": payload.get("confidence") or payload.get("confidence_score"),
        "data_quality_pct": payload.get("data_quality_pct"),
        "national_team_intelligence_version": (payload.get("national_team_intelligence") or {}).get("version"),
        "adaptive_confidence_version": payload.get("adaptive_confidence_version"),
        "adaptive_confidence_trace": payload.get("adaptive_confidence_trace"),
        "fusion_quality_band": payload.get("fusion_quality_band"),
        "no_bet": payload.get("no_bet_flag") or payload.get("no_bet"),
    }
    print(json.dumps(out, indent=2, default=str))

# sportmonks enrichment row
sm = conn.execute(
    "SELECT sportmonks_fixture_id, status, base_enrichment_available, premium_odds_available, premium_predictions_available, premium_xg_available, length(raw_json) as raw_len, fetched_at_utc FROM sportmonks_fixture_enrichment WHERE fixture_id_api_football=? LIMIT 1",
    (fid,),
).fetchone()
print("sportmonks:", dict(sm) if sm else None)
