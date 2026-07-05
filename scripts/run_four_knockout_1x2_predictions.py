#!/usr/bin/env python3
"""Run WDE predictions for four knockout fixtures; report 1X2 only."""

from __future__ import annotations

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

FIXTURES = [
    {"fixture_id": 1570714, "match": "Mexico vs England"},
    {"fixture_id": 1576756, "match": "Portugal vs Spain"},
]

MISSING = [
    {"match": "Argentina vs Egypt", "reason": "not_in_production_db"},
    {"match": "Switzerland vs Colombia", "reason": "not_in_production_db"},
]

PY = str(ROOT / ".venv" / "bin" / "python")
ARTIFACT = ROOT / "artifacts" / "four_knockout_1x2_predictions" / "workflow.json"


def _run(cmd: list[str]) -> dict:
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=600)
    out = proc.stdout.strip()
    payload = None
    if out:
        try:
            payload = json.loads(out)
        except json.JSONDecodeError:
            payload = {"raw_stdout": out[-8000:]}
    return {
        "cmd": " ".join(cmd),
        "exit_code": proc.returncode,
        "stderr_tail": (proc.stderr or "")[-2000:],
        "result": payload,
    }


def _predict(fid: int, *, dry_run: bool) -> dict:
    cmd = [
        PY,
        "scripts/run_production_prediction_pipeline.py",
        "--mode",
        "predictions-only",
        "--fixture-id",
        str(fid),
        "--refresh-stale-odds",
        "--max-odds-provider-calls",
        "20",
    ]
    if dry_run:
        cmd.append("--dry-run")
    return _run(cmd)


def _1x2(fid: int) -> dict:
    settings = get_settings()
    conn = sqlite3.connect(f"file:{settings.sqlite_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    fx = dict(conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fid,)).fetchone() or {})
    wde = conn.execute(
        "SELECT payload_json, predicted_at FROM worldcup_stored_predictions WHERE fixture_id=?",
        (fid,),
    ).fetchone()
    if not wde:
        conn.close()
        return {"fixture_id": fid, "stored": False}
    p = json.loads(wde["payload_json"])
    probs = p.get("probabilities") or {}
    hw = probs.get("home_win")
    dr = probs.get("draw")
    aw = probs.get("away_win")
    if isinstance(hw, dict):
        hw, dr, aw = hw.get("probability"), dr.get("probability") if isinstance(dr, dict) else dr, aw.get("probability") if isinstance(aw, dict) else aw
    out = {
        "fixture_id": fid,
        "match": f"{fx.get('home_team')} vs {fx.get('away_team')}",
        "kickoff_utc": fx.get("kickoff_utc"),
        "round": fx.get("round_name"),
        "stored": True,
        "predicted_at": wde["predicted_at"],
        "pick_1x2": p.get("prediction"),
        "confidence": p.get("confidence"),
        "probabilities_1x2": {
            "home": hw,
            "draw": dr,
            "away": aw,
        },
        "odds_freshness_status": p.get("odds_freshness_status"),
    }
    conn.close()
    return out


def main() -> int:
    result = {
        "phase": "FOUR-KNOCKOUT-1X2-PREDICTIONS",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "fixtures_requested": 4,
        "fixtures_found": len(FIXTURES),
        "missing_fixtures": MISSING,
        "runs": [],
        "predictions_1x2": [],
    }
    for fx in FIXTURES:
        fid = fx["fixture_id"]
        entry = {"fixture_id": fid, "match": fx["match"], "dry_run": _predict(fid, dry_run=True)}
        if entry["dry_run"]["exit_code"] == 0:
            entry["real"] = _predict(fid, dry_run=False)
        else:
            entry["real"] = {"skipped": True}
        entry["output_1x2"] = _1x2(fid)
        result["runs"].append(entry)
        result["predictions_1x2"].append(entry["output_1x2"])
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"artifact": str(ARTIFACT), "predictions_1x2": result["predictions_1x2"], "missing": MISSING}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
