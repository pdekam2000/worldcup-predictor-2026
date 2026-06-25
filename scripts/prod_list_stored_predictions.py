#!/usr/bin/env python3
import json
from worldcup_predictor.database.repository import FootballIntelligenceRepository

r = FootballIntelligenceRepository()
rows = r._conn.execute("SELECT fixture_id, payload_json FROM worldcup_stored_predictions").fetchall()
for row in rows:
    p = json.loads(row["payload_json"])
    rb = (p.get("recommended_bets") or [{}])[0]
    print(
        row["fixture_id"],
        p.get("confidence"),
        p.get("pick_tier"),
        p.get("no_bet"),
        rb.get("status"),
        str(rb.get("display_text", ""))[:55],
    )
