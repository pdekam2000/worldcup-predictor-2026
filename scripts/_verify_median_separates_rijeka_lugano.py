#!/usr/bin/env python3
"""Prove median aggregation separates Rijeka/Lugano ECSE on prod RO DB."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path("/opt/worldcup-predictor")
sys.path.insert(0, str(ROOT))

import sqlite3
from worldcup_predictor.research.ecse_live.prediction_builder import build_ecse_live_prediction, build_odds_feature_row

DB = ROOT / "data" / "football_intelligence.db"
conn = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
out = {}
for fid in (1593490, 1556516):
    odds = build_odds_feature_row(conn, fid)
    pred = build_ecse_live_prediction(conn, fid, {"fixture_id": fid, "competition_key": "conference_league"})
    out[str(fid)] = {
        "odds_agg": odds.get("_odds_aggregation") if odds else None,
        "ft": (odds.get("ft_home_closing"), odds.get("ft_draw_closing"), odds.get("ft_away_closing")) if odds else None,
        "first_book_home": odds.get("_first_book_ft_home") if odds else None,
        "lambda": ((pred or {}).get("lambda_home"), (pred or {}).get("lambda_away")),
        "top5": (pred or {}).get("top_5_scores"),
        "input_hash": (pred or {}).get("ecse_input_hash"),
        "output_hash": (pred or {}).get("ecse_output_hash"),
        "source": (pred or {}).get("prediction_source"),
    }
print(json.dumps({
    "odds_features_equal": out["1593490"]["ft"] == out["1556516"]["ft"],
    "lambdas_equal": out["1593490"]["lambda"] == out["1556516"]["lambda"],
    "output_hashes_equal": out["1593490"]["output_hash"] == out["1556516"]["output_hash"],
    "input_hashes_equal": out["1593490"]["input_hash"] == out["1556516"]["input_hash"],
    "detail": out,
}, indent=2))
