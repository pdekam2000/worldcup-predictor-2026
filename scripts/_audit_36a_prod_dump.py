"""Phase 36A audit — fixture 1489393 production payload dump."""
import json
import sqlite3
from pathlib import Path

DB = Path("/opt/worldcup-predictor/data/football_intelligence.db")
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

fid = 1489393
out = {}

fx = conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fid,)).fetchone()
out["fixture_row"] = dict(fx) if fx else None

pred = conn.execute("SELECT payload_json, source, predicted_at FROM worldcup_stored_predictions WHERE fixture_id=?", (fid,)).fetchone()
if pred:
    p = json.loads(pred["payload_json"])
    out["stored"] = {
        "source": pred["source"],
        "predicted_at": pred["predicted_at"],
        "confidence": p.get("confidence"),
        "prediction_engine_version": p.get("prediction_engine_version"),
        "adaptive_confidence_version": p.get("adaptive_confidence_version"),
        "generated_by": p.get("generated_by"),
        "generated_at": p.get("generated_at"),
        "cache_source": p.get("cache_source"),
        "data_quality": p.get("data_quality"),
        "no_bet": p.get("no_bet"),
        "pick_tier": p.get("pick_tier"),
        "adaptive_confidence_trace": p.get("adaptive_confidence_trace"),
        "audit_trace_confidence": (p.get("audit_trace") or {}).get("confidence"),
        "national_team_intelligence": p.get("national_team_intelligence"),
        "data_signals": p.get("data_signals"),
        "specialist_aggregated": (p.get("specialist_summary") or {}).get("aggregated_score"),
        "specialist_agents": {
            k: {
                "status": v.get("status"),
                "status_reason": v.get("status_reason"),
                "impact_score": v.get("impact_score"),
                "domain": v.get("domain"),
            }
            for k, v in ((p.get("specialist_summary") or {}).get("agents") or {}).items()
        },
        "metadata_fusion": (p.get("audit_trace") or {}).get("promotion_modes"),
    }

# sportmonks enrichment cache
for table in ("sportmonks_enrichment_cache", "api_football_cache", "enrichment_cache"):
    try:
        rows = conn.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        if rows:
            cnt = conn.execute(f"SELECT COUNT(*) c FROM {table} WHERE fixture_id=?", (fid,)).fetchone()["c"]
            out[f"table_{table}_count"] = cnt
    except Exception as e:
        out[f"table_{table}_error"] = str(e)

# Check sportmonks if different schema
for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%sportmonks%'").fetchall():
    tname = t["name"]
    try:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({tname})").fetchall()]
        if "fixture_id" in cols:
            cnt = conn.execute(f"SELECT COUNT(*) c FROM {tname} WHERE fixture_id=?", (fid,)).fetchone()["c"]
            out[f"sportmonks_table_{tname}"] = cnt
    except Exception:
        pass

print(json.dumps(out, indent=2, default=str)[:15000])
