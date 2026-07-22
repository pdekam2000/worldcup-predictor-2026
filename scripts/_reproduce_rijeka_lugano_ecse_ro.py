#!/usr/bin/env python3
"""RO reproduce ECSE for Rijeka/Lugano — find first identical stage."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
import sys

ROOT = Path("/opt/worldcup-predictor")
sys.path.insert(0, str(ROOT))

from worldcup_predictor.research.ecse_live.prediction_builder import (
    MODEL_VERSION,
    build_ecse_live_prediction,
    build_odds_feature_row,
)
from worldcup_predictor.research.ecse_match_display import (
    _load_lambda,
    _load_top_scores,
    resolve_registry_fixture_id,
)
from worldcup_predictor.research.ecse_lambda_extraction import extract_lambdas
from worldcup_predictor.research.ecse_score_distribution import generate_score_distribution

IDS = [1593490, 1556516]
DB = ROOT / "data" / "football_intelligence.db"


def main() -> None:
    conn = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    out = {}
    for fid in IDS:
        resolved = resolve_registry_fixture_id(conn, fid)
        registry_id = resolved.get("registry_fixture_id")
        lambdas = _load_lambda(conn, registry_id) if registry_id is not None else None
        tops = _load_top_scores(conn, registry_id, limit=10) if registry_id is not None else None
        odds_row = build_odds_feature_row(conn, fid)
        feat = extract_lambdas(odds_row) if odds_row else None
        live_dist = None
        if feat:
            live_dist = generate_score_distribution(float(feat["lambda_home"]), float(feat["lambda_away"]))
        pred = build_ecse_live_prediction(
            conn,
            fid,
            {
                "fixture_id": fid,
                "competition_key": "conference_league",
                "home_team": "?",
                "away_team": "?",
                "kickoff_utc": "",
            },
        )
        out[str(fid)] = {
            "resolved": resolved,
            "registry_id": registry_id,
            "registry_lambdas": lambdas,
            "registry_top5": (tops or [])[:5],
            "odds_row": odds_row,
            "live_lambda_features": feat,
            "live_top5": [
                {"scoreline": e["scoreline"], "probability": e["probability"]}
                for e in (live_dist or [])[:5]
            ],
            "built_prediction_source": (pred or {}).get("prediction_source"),
            "built_raw_source": ((pred or {}).get("raw_features") or {}).get("source"),
            "built_lambda": {
                "home": (pred or {}).get("lambda_home"),
                "away": (pred or {}).get("lambda_away"),
            },
            "built_top5": (pred or {}).get("top_5_scores"),
            "built_top10": (pred or {}).get("top_10_scorelines"),
            "model_version": MODEL_VERSION,
        }
    # diffs
    a, b = out["1593490"], out["1556516"]
    print(json.dumps({
        "registry_ids_equal": a["registry_id"] == b["registry_id"],
        "registry_id_a": a["registry_id"],
        "registry_id_b": b["registry_id"],
        "resolved_a": a["resolved"],
        "resolved_b": b["resolved"],
        "pred_source_a": a["built_prediction_source"],
        "pred_source_b": b["built_prediction_source"],
        "raw_source_a": a["built_raw_source"],
        "raw_source_b": b["built_raw_source"],
        "registry_lambdas_equal": a["registry_lambdas"] == b["registry_lambdas"],
        "odds_rows_equal": a["odds_row"] == b["odds_row"],
        "live_feat_equal": a["live_lambda_features"] == b["live_lambda_features"],
        "built_lambda_equal": a["built_lambda"] == b["built_lambda"],
        "built_top5_equal": a["built_top5"] == b["built_top5"],
        "live_top5_equal": a["live_top5"] == b["live_top5"],
        "detail": out,
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
