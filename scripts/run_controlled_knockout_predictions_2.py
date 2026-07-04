#!/usr/bin/env python3
"""CONTROLLED-KNOCKOUT-PREDICTIONS-2 — Orchestrate odds + prediction workflow, capture JSON."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts" / "controlled_knockout_predictions_2" / "workflow_results.json"
FIXTURE_IDS = [1567824, 1569870, 1568100]  # filled after discovery; overridden by discovery.json


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
        "stderr_tail": proc.stderr[-2000:] if proc.stderr else "",
        "result": payload,
    }


def odds_workflow(fixture_id: int, py: str) -> dict:
    steps = {}
    steps["audit_before"] = _run([
        py, "scripts/run_odds_freshness_refresh.py",
        "--mode", "audit", "--fixture-id", str(fixture_id),
        "--dry-run", "--max-provider-calls", "0", "--source", "auto",
    ])
    refresh_dry = _run([
        py, "scripts/run_odds_freshness_refresh.py",
        "--mode", "refresh", "--fixture-id", str(fixture_id),
        "--dry-run", "--max-provider-calls", "20", "--source", "auto",
    ])
    steps["refresh_dry_run"] = refresh_dry
    would = 0
    if isinstance(refresh_dry.get("result"), dict):
        would = refresh_dry["result"].get("would_refresh") or 0
    if would and refresh_dry["exit_code"] == 0:
        steps["refresh_real"] = _run([
            py, "scripts/run_odds_freshness_refresh.py",
            "--mode", "refresh", "--fixture-id", str(fixture_id),
            "--max-provider-calls", "20", "--source", "auto",
        ])
    else:
        steps["refresh_real"] = {"skipped": True, "reason": "dry_run_would_refresh=0 or failed"}
    steps["audit_after"] = _run([
        py, "scripts/run_odds_freshness_refresh.py",
        "--mode", "audit", "--fixture-id", str(fixture_id),
        "--dry-run", "--max-provider-calls", "0", "--source", "auto",
    ])
    return steps


def prediction_workflow(fixture_id: int, py: str) -> dict:
    dry = _run([
        py, "scripts/run_production_prediction_pipeline.py",
        "--mode", "predictions-only", "--fixture-id", str(fixture_id),
        "--refresh-stale-odds", "--max-odds-provider-calls", "20", "--dry-run",
    ])
    real = {"skipped": True}
    if dry["exit_code"] == 0:
        real = _run([
            py, "scripts/run_production_prediction_pipeline.py",
            "--mode", "predictions-only", "--fixture-id", str(fixture_id),
            "--refresh-stale-odds", "--max-odds-provider-calls", "20",
        ])
    return {"dry_run": dry, "real": real}


def main() -> int:
    py = str(ROOT / ".venv" / "bin" / "python")
    discovery_path = ROOT / "artifacts" / "controlled_knockout_predictions_2" / "discovery.json"
    fixture_ids = FIXTURE_IDS
    if discovery_path.exists():
        disc = json.loads(discovery_path.read_text(encoding="utf-8"))
        fixture_ids = [t["fixture_id"] for t in disc.get("targets", [])]

    payload = {
        "phase": "CONTROLLED-KNOCKOUT-PREDICTIONS-2",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "fixture_ids": fixture_ids,
        "fixtures": {},
    }
    for fid in fixture_ids:
        payload["fixtures"][str(fid)] = {
            "odds": odds_workflow(fid, py),
            "prediction": prediction_workflow(fid, py),
        }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"artifact": str(ARTIFACT), "fixture_ids": fixture_ids}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
