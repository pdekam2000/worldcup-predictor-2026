#!/usr/bin/env python3
"""BRAZIL-NORWAY-CONTROLLED-PREDICTION-1 — Odds + prediction workflow capture."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if not os.environ.get("APP_ENV") and (ROOT / ".env.production").is_file():
    os.environ.setdefault("APP_ENV", "production")

from worldcup_predictor.config.settings import get_settings

FIXTURE_ID = 1568100
ARTIFACT = ROOT / "artifacts" / "brazil_norway_controlled_prediction_1" / "workflow.json"
PY = str(ROOT / ".venv" / "bin" / "python")


def _run(cmd: list[str]) -> dict:
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=600)
    out = proc.stdout.strip()
    payload = None
    if out:
        try:
            payload = json.loads(out)
        except json.JSONDecodeError:
            payload = {"raw_stdout": out[-12000:]}
    return {
        "cmd": " ".join(cmd),
        "exit_code": proc.returncode,
        "stderr_tail": (proc.stderr or "")[-3000:],
        "result": payload,
    }


def _odds_step(mode: str, *, dry_run: bool = False, max_calls: int = 0) -> dict:
    cmd = [
        PY,
        "scripts/run_odds_freshness_refresh.py",
        "--mode",
        mode,
        "--fixture-id",
        str(FIXTURE_ID),
        "--max-provider-calls",
        str(max_calls),
        "--source",
        "auto",
    ]
    if dry_run or mode == "audit":
        cmd.append("--dry-run")
    return _run(cmd)


def _predict(*, dry_run: bool) -> dict:
    cmd = [
        PY,
        "scripts/run_production_prediction_pipeline.py",
        "--mode",
        "predictions-only",
        "--fixture-id",
        str(FIXTURE_ID),
        "--refresh-stale-odds",
        "--max-odds-provider-calls",
        "20",
    ]
    if dry_run:
        cmd.append("--dry-run")
    return _run(cmd)


def _inspect() -> dict:
    settings = get_settings()
    conn = sqlite3.connect(f"file:{settings.sqlite_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    fid = FIXTURE_ID
    fx = dict(conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fid,)).fetchone() or {})
    wde = conn.execute(
        "SELECT payload_json, predicted_at FROM worldcup_stored_predictions WHERE fixture_id=?",
        (fid,),
    ).fetchone()
    ecse = conn.execute(
        "SELECT * FROM ecse_prediction_snapshots WHERE fixture_id=? ORDER BY id DESC LIMIT 1",
        (fid,),
    ).fetchone()
    payload = {}
    if wde and wde["payload_json"]:
        payload = json.loads(wde["payload_json"])
    top3 = top5 = []
    if ecse:
        top3 = json.loads(ecse["top_3_scores_json"] or "[]")
        top5 = json.loads(ecse["top_5_scores_json"] or "[]")
    btts = (payload.get("probabilities") or {}).get("btts") or payload.get("detailed_markets", {}).get("btts") or {}
    ou = (payload.get("probabilities") or {}).get("over_under_2_5") or payload.get("detailed_markets", {}).get("over_under_25") or {}
    phash = ""
    if wde and wde["payload_json"]:
        phash = hashlib.sha256(wde["payload_json"].encode("utf-8")).hexdigest()[:16]
    out = {
        "fixture_id": fid,
        "match": f"{fx.get('home_team')} vs {fx.get('away_team')}",
        "kickoff_utc": fx.get("kickoff_utc"),
        "round": fx.get("round_name"),
        "wde": {
            "stored": wde is not None,
            "predicted_at": wde["predicted_at"] if wde else None,
            "pick_1x2": payload.get("prediction"),
            "confidence": payload.get("confidence"),
            "btts": btts.get("selection") or btts.get("display"),
            "ou_2_5": ou.get("selection") or ou.get("display"),
            "payload_hash": phash,
            "engine_version": payload.get("prediction_engine_version"),
            "cache_source": payload.get("cache_source"),
            "odds_freshness_status": payload.get("odds_freshness_status"),
            "odds_age_hours": payload.get("odds_age_hours"),
            "odds_snapshot_at": payload.get("odds_snapshot_at"),
            "odds_freshness_metadata": payload.get("odds_freshness_metadata"),
        },
        "ecse": {
            "stored": ecse is not None,
            "snapshot_id": ecse["id"] if ecse else None,
            "generated_at": ecse["generated_at"] if ecse else None,
            "top1": ecse["top_1_score"] if ecse else None,
            "top3": top3,
            "top3_count": len(top3),
            "top5": top5,
            "is_frozen": ecse["is_frozen"] if ecse else None,
            "model_version": ecse["model_version"] if ecse else None,
        },
    }
    conn.close()
    return out


def main() -> int:
    result = {
        "phase": "BRAZIL-NORWAY-CONTROLLED-PREDICTION-1",
        "fixture_id": FIXTURE_ID,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "odds": {},
        "prediction": {},
    }
    result["odds"]["audit_before"] = _odds_step("audit", max_calls=0)
    refresh_dry = _odds_step("refresh", dry_run=True, max_calls=20)
    result["odds"]["refresh_dry_run"] = refresh_dry
    would = 0
    if isinstance(refresh_dry.get("result"), dict):
        would = refresh_dry["result"].get("would_refresh") or 0
    if would and refresh_dry["exit_code"] == 0:
        result["odds"]["refresh_real"] = _odds_step("refresh", max_calls=20)
    else:
        result["odds"]["refresh_real"] = {"skipped": True, "reason": "would_refresh=0 or dry-run failed"}
    result["odds"]["audit_after"] = _odds_step("audit", max_calls=0)
    result["prediction"]["dry_run"] = _predict(dry_run=True)
    dry = result["prediction"]["dry_run"]
    if dry["exit_code"] == 0:
        result["prediction"]["real"] = _predict(dry_run=False)
    else:
        result["prediction"]["real"] = {"skipped": True, "reason": "dry_run failed"}
    result["stored_output"] = _inspect()
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"artifact": str(ARTIFACT), "stored": result["stored_output"]}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
