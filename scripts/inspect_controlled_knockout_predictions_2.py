#!/usr/bin/env python3
"""CONTROLLED-KNOCKOUT-PREDICTIONS-2 Part F — Inspect stored predictions."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if not os.environ.get("APP_ENV") and (ROOT / ".env.production").is_file():
    os.environ.setdefault("APP_ENV", "production")

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.odds.freshness_audit import _latest_odds
from worldcup_predictor.odds.freshness_policy import classify_odds_freshness, is_knockout_match, is_low_priority_match

TARGET_IDS = [1567824, 1569870, 1568100]
COLOMBIA_ID = 1567310
OUTPUT = ROOT / "artifacts" / "controlled_knockout_predictions_2" / "stored_predictions.json"


def _inspect_fixture(conn: sqlite3.Connection, fid: int) -> dict:
    fx = dict(conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fid,)).fetchone() or {})
    wde = conn.execute(
        "SELECT payload_json, predicted_at FROM worldcup_stored_predictions WHERE fixture_id=? ORDER BY predicted_at DESC LIMIT 1",
        (fid,),
    ).fetchone()
    ecse = conn.execute(
        "SELECT * FROM ecse_prediction_snapshots WHERE fixture_id=? ORDER BY id DESC LIMIT 1",
        (fid,),
    ).fetchone()

    wde_payload = {}
    if wde and wde["payload_json"]:
        wde_payload = json.loads(wde["payload_json"])

    top3 = top5 = probs = []
    if ecse:
        if ecse["top_3_scores_json"]:
            top3 = json.loads(ecse["top_3_scores_json"])
        if ecse["top_5_scores_json"]:
            top5 = json.loads(ecse["top_5_scores_json"])
        if "top_scores_json" in ecse.keys() and ecse["top_scores_json"]:
            try:
                raw = json.loads(ecse["top_scores_json"])
                probs = raw if isinstance(raw, list) else []
            except json.JSONDecodeError:
                probs = []

    btts = (wde_payload.get("probabilities") or {}).get("btts") or wde_payload.get("detailed_markets", {}).get("btts") or {}
    ou = (wde_payload.get("probabilities") or {}).get("over_under_2_5") or wde_payload.get("detailed_markets", {}).get("over_under_25") or {}

    odds = _latest_odds(conn, fid)
    cls = classify_odds_freshness(
        odds_snapshot_at=odds["snapshot_at"] if odds else wde_payload.get("odds_snapshot_at"),
        knockout=is_knockout_match(round_name=fx.get("round_name"), status=fx.get("status")),
        low_priority=is_low_priority_match(kickoff_utc=fx.get("kickoff_utc")),
        odds_source=odds.get("source") if odds else wde_payload.get("odds_freshness_metadata", {}).get("odds_source"),
        has_odds=bool(odds) or bool(wde_payload.get("odds_snapshot_at")),
    )

    return {
        "fixture_id": fid,
        "match": f"{fx.get('home_team')} vs {fx.get('away_team')}",
        "kickoff_utc": fx.get("kickoff_utc"),
        "round": fx.get("round_name"),
        "status": fx.get("status"),
        "odds": {
            "source": wde_payload.get("odds_freshness_metadata", {}).get("odds_source") or (odds.get("source") if odds else None),
            "snapshot_at": wde_payload.get("odds_snapshot_at") or (odds["snapshot_at"] if odds else None),
            "odds_age_hours": wde_payload.get("odds_age_hours") or cls.odds_age_hours,
            "freshness_status": wde_payload.get("odds_freshness_status") or cls.status.value,
            "freshness_metadata": wde_payload.get("odds_freshness_metadata"),
        },
        "wde": {
            "stored": wde is not None,
            "predicted_at": wde["predicted_at"] if wde else None,
            "pick_1x2": wde_payload.get("prediction"),
            "confidence": wde_payload.get("confidence"),
            "btts": btts.get("selection") or btts.get("display"),
            "ou_2_5": ou.get("selection") or ou.get("display"),
            "engine_version": wde_payload.get("prediction_engine_version"),
            "cache_source": wde_payload.get("cache_source"),
        },
        "ecse": {
            "stored": ecse is not None,
            "snapshot_id": ecse["id"] if ecse else None,
            "generated_at": ecse["generated_at"] if ecse else None,
            "top1": ecse["top_1_score"] if ecse else None,
            "top3": top3,
            "top3_count": len(top3),
            "top5": top5,
            "model_version": ecse["model_version"] if ecse else None,
            "candidate_probabilities": probs[:10] if probs else None,
        },
    }


def _counts(conn: sqlite3.Connection) -> dict:
    return {
        "ecse_snapshots_total": conn.execute("SELECT COUNT(*) FROM ecse_prediction_snapshots").fetchone()[0],
        "ecse_evaluated": conn.execute("SELECT COUNT(*) FROM ecse_prediction_evaluations").fetchone()[0],
        "ecse_pending": conn.execute(
            """
            SELECT COUNT(*) FROM ecse_prediction_snapshots s
            LEFT JOIN ecse_prediction_evaluations e ON e.snapshot_id=s.id
            WHERE e.id IS NULL
            """
        ).fetchone()[0],
        "wde_stored_total": conn.execute("SELECT COUNT(*) FROM worldcup_stored_predictions").fetchone()[0],
        "wde_evaluated": conn.execute("SELECT COUNT(*) FROM worldcup_prediction_evaluations").fetchone()[0],
        "wde_pending": conn.execute(
            """
            SELECT COUNT(*) FROM worldcup_stored_predictions s
            LEFT JOIN worldcup_prediction_evaluations e ON e.fixture_id=s.fixture_id
            WHERE e.fixture_id IS NULL
            """
        ).fetchone()[0],
    }


def main() -> int:
    settings = get_settings()
    conn = sqlite3.connect(settings.sqlite_path)
    conn.row_factory = sqlite3.Row
    payload = {
        "targets": [_inspect_fixture(conn, fid) for fid in TARGET_IDS],
        "colombia_reference": _inspect_fixture(conn, COLOMBIA_ID),
        "production_counts": _counts(conn),
    }
    conn.close()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
