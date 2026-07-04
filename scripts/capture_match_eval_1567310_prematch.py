#!/usr/bin/env python3
"""MATCH-EVAL-1567310-1 Part A — Read-only prematch snapshot capture."""

from __future__ import annotations

import hashlib
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

FIXTURE_ID = 1567310
OUTPUT = ROOT / "MATCH_EVAL_1567310_1_PREMATCH_SNAPSHOT.md"
ARTIFACT = ROOT / "artifacts" / "match_eval" / "1567310_prematch_snapshot.json"


def _payload_hash(raw: str | None) -> str:
    if not raw:
        return "—"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def capture_prematch(*, db_path: str) -> dict:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    fx = conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (FIXTURE_ID,)).fetchone()
    wde = conn.execute(
        "SELECT * FROM worldcup_stored_predictions WHERE fixture_id=? ORDER BY predicted_at ASC LIMIT 1",
        (FIXTURE_ID,),
    ).fetchone()
    ecse = conn.execute(
        "SELECT * FROM ecse_prediction_snapshots WHERE fixture_id=? ORDER BY id ASC LIMIT 1",
        (FIXTURE_ID,),
    ).fetchone()
    result = conn.execute("SELECT * FROM fixture_results WHERE fixture_id=?", (FIXTURE_ID,)).fetchone()
    ecse_eval = None
    if ecse:
        ecse_eval = conn.execute(
            "SELECT * FROM ecse_prediction_evaluations WHERE snapshot_id=?",
            (ecse["id"],),
        ).fetchone()

    wde_payload = {}
    if wde and wde["payload_json"]:
        wde_payload = json.loads(wde["payload_json"])

    top3 = top5 = []
    if ecse:
        if ecse["top_3_scores_json"]:
            top3 = json.loads(ecse["top_3_scores_json"])
        if ecse["top_5_scores_json"]:
            top5 = json.loads(ecse["top_5_scores_json"])

    probs = wde_payload.get("probabilities") or {}
    btts = probs.get("btts") or wde_payload.get("detailed_markets", {}).get("btts") or {}
    ou = probs.get("over_under_2_5") or wde_payload.get("detailed_markets", {}).get("over_under_25") or {}

    snap = {
        "fixture_id": FIXTURE_ID,
        "match": f"{fx['home_team']} vs {fx['away_team']}" if fx else "—",
        "stage": fx["round_name"] if fx else None,
        "kickoff_utc": fx["kickoff_utc"] if fx else None,
        "fixture_status_at_capture": fx["status"] if fx else None,
        "wde": {
            "row_id": wde["fixture_id"] if wde else None,
            "predicted_at": wde["predicted_at"] if wde else None,
            "payload_sha256_prefix": _payload_hash(wde["payload_json"] if wde else None),
            "prediction_1x2": wde_payload.get("prediction"),
            "confidence": wde_payload.get("confidence"),
            "btts_pick": btts.get("selection") or btts.get("display"),
            "ou_pick": ou.get("selection") or ou.get("display"),
            "odds_freshness_status": wde_payload.get("odds_freshness_status"),
            "odds_age_hours": wde_payload.get("odds_age_hours"),
            "odds_snapshot_at": wde_payload.get("odds_snapshot_at"),
            "odds_freshness_metadata": wde_payload.get("odds_freshness_metadata"),
            "prediction_engine_version": wde_payload.get("prediction_engine_version"),
            "generated_at": wde_payload.get("generated_at"),
            "generated_by": wde_payload.get("generated_by"),
            "cache_source": wde_payload.get("cache_source"),
        },
        "ecse": {
            "snapshot_id": ecse["id"] if ecse else None,
            "snapshot_key": ecse["snapshot_key"] if ecse else None,
            "generated_at": ecse["generated_at"] if ecse else None,
            "model_version": ecse["model_version"] if ecse else None,
            "top_1_score": ecse["top_1_score"] if ecse else None,
            "top_3_scores": top3,
            "top_5_scores": top5,
            "confidence_score": ecse["confidence_score"] if ecse else None,
            "is_frozen": ecse["is_frozen"] if ecse else None,
            "prediction_source": ecse["prediction_source"] if ecse else None,
            "evaluation_exists_at_capture": ecse_eval is not None,
        },
        "result_at_capture": dict(result) if result else None,
    }
    conn.close()
    return snap


def render_md(s: dict) -> str:
    w = s["wde"]
    e = s["ecse"]
    lines = [
        "# MATCH-EVAL-1567310-1 — Frozen Prematch Snapshot",
        "",
        "**Read-only capture — original prediction must remain frozen.**",
        "",
        "## Match",
        "",
        f"- **fixture_id:** {s['fixture_id']}",
        f"- **Match:** {s['match']}",
        f"- **Stage:** {e and s.get('stage') or '—'}",
        f"- **Kickoff UTC:** {s['kickoff_utc']}",
        f"- **Fixture status at capture:** {s['fixture_status_at_capture']}",
        "",
        "## WDE stored prediction",
        "",
        f"- **predicted_at:** {w['predicted_at']}",
        f"- **payload hash (sha256 prefix):** `{w['payload_sha256_prefix']}`",
        f"- **1X2 pick:** {w['prediction_1x2']}",
        f"- **Confidence:** {w['confidence']}",
        f"- **BTTS pick:** {w['btts_pick']}",
        f"- **O/U 2.5 pick:** {w['ou_pick']}",
        f"- **odds_freshness_status:** {w['odds_freshness_status']}",
        f"- **odds_age_hours:** {w['odds_age_hours']}",
        f"- **odds_snapshot_at:** {w['odds_snapshot_at']}",
        f"- **prediction_engine_version:** {w['prediction_engine_version']}",
        f"- **generated_at:** {w['generated_at']}",
        f"- **generated_by:** {w['generated_by']}",
        f"- **cache_source:** {w['cache_source']}",
        "",
        "## ECSE snapshot",
        "",
        f"- **snapshot_id:** {e['snapshot_id']}",
        f"- **snapshot_key:** {e['snapshot_key']}",
        f"- **generated_at:** {e['generated_at']}",
        f"- **model_version:** {e['model_version']}",
        f"- **Top1:** {e['top_1_score']}",
        f"- **Top3:** {', '.join(e['top_3_scores'] or [])}",
        f"- **Top5:** {', '.join(e['top_5_scores'] or [])}",
        f"- **confidence_score:** {e['confidence_score']}",
        f"- **is_frozen:** {e['is_frozen']}",
        f"- **prediction_source:** {e['prediction_source']}",
        f"- **evaluation at capture:** {e['evaluation_exists_at_capture']}",
        "",
        "## Result at capture",
        "",
        f"{json.dumps(s['result_at_capture'], indent=2) if s['result_at_capture'] else '_None — match not finished or not synced_'}",
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    settings = get_settings()
    snap = capture_prematch(db_path=settings.sqlite_path)
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(snap, indent=2), encoding="utf-8")
    OUTPUT.write_text(render_md(snap), encoding="utf-8")
    print(json.dumps({"prematch_md": str(OUTPUT), "artifact": str(ARTIFACT), **snap}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
