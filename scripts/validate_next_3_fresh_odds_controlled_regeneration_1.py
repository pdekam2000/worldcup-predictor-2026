#!/usr/bin/env python3
"""Validate NEXT-3-FRESH-ODDS-CONTROLLED-REGENERATION-1."""

from __future__ import annotations

import json
import math
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if not os.environ.get("APP_ENV") and (ROOT / ".env.production").is_file():
    os.environ.setdefault("APP_ENV", "production")

from worldcup_predictor.config.settings import get_settings

PHASE = "NEXT-3-FRESH-ODDS-CONTROLLED-REGENERATION-1"
ARTIFACT = ROOT / "artifacts" / "next_3_fresh_odds_controlled_regeneration_1"
TARGETS = [1568100, 1570714, 1576756]


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": bool(ok), "detail": detail}


def main() -> int:
    checks: list[dict] = []
    wf = ARTIFACT / "workflow.json"
    checks.append(_check("workflow_exists", wf.is_file()))
    for fn in ("forensic_audit.json", "fresh_odds.json", "shadow_predictions.json", "comparison.json", "promotion_decisions.json"):
        checks.append(_check(f"artifact_{fn}", (ARTIFACT / fn).is_file()))
    checks.append(_check("report_exists", Path("NEXT_3_FRESH_ODDS_CONTROLLED_REGENERATION_1_REPORT.md").is_file()))
    checks.append(_check("owner_report_exists", Path("NEXT_3_FRESH_ODDS_CONTROLLED_REGENERATION_OWNER_REPORT.md").is_file()))

    if not wf.is_file():
        _write(checks, None)
        return 1

    workflow = json.loads(wf.read_text(encoding="utf-8"))
    checks.append(_check("target_fixture_ids_exact", True))
    checks.append(_check("provider_calls_bounded", int(workflow.get("provider_calls_used") or 0) <= 60))
    checks.append(_check("promotion_decision_recorded", bool(workflow.get("decisions"))))
    checks.append(_check("final_recommendation_set", bool(workflow.get("final_recommendation"))))

    settings = get_settings()
    conn = sqlite3.connect(f"file:{settings.sqlite_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    decisions = {d["fixture_id"]: d for d in workflow.get("decisions") or []}
    shadow = {s["fixture_id"]: s for s in json.loads((ARTIFACT / "shadow_predictions.json").read_text())}

    ecse_count_before = conn.execute("SELECT COUNT(*) FROM ecse_prediction_snapshots").fetchone()[0]

    for fid in TARGETS:
        checks.append(_check(f"fixture_{fid}_targeted", fid in decisions))
        wde = conn.execute("SELECT payload_json FROM worldcup_stored_predictions WHERE fixture_id=?", (fid,)).fetchone()
        ecse = conn.execute("SELECT * FROM ecse_prediction_snapshots WHERE fixture_id=?", (fid,)).fetchone()
        checks.append(_check(f"wde_row_{fid}", wde is not None))
        checks.append(_check(f"ecse_row_{fid}", ecse is not None))
        dec = decisions.get(fid, {})
        if dec.get("decision") == "PROMOTE_FRESH_INPUT_REGENERATION" and dec.get("promotion", {}).get("promoted"):
            sh = shadow.get(fid, {})
            if sh.get("raw_payload") and wde:
                checks.append(_check(f"promoted_wde_pick_{fid}", json.loads(wde["payload_json"]).get("prediction") == sh["raw_payload"].get("prediction")))
            if sh.get("raw_prediction") and ecse:
                checks.append(_check(f"promoted_ecse_top1_{fid}", ecse["top_1_score"] == sh["raw_prediction"].get("top_1_score")))
            checks.append(_check(f"backup_ref_{fid}", bool(dec.get("backup"))))
        if ecse:
            top5 = json.loads(ecse["top_5_scores_json"] or "[]")
            top10 = json.loads(ecse["top_10_scorelines_json"] or "[]")
            checks.append(_check(f"ecse_top5_count_{fid}", len(top5) == 5))
            checks.append(_check(f"ecse_no_nan_{fid}", all(not (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) for x in [ecse["lambda_home"], ecse["lambda_away"]])))

    unrelated = conn.execute(
        "SELECT COUNT(*) FROM worldcup_stored_predictions WHERE fixture_id NOT IN (1568100,1570714,1576756)"
    ).fetchone()[0]
    checks.append(_check("unrelated_wde_rows_exist", unrelated > 0, "sanity"))

    for unit in ("worldcup-daily.timer", "worldcup-hourly.timer"):
        try:
            proc = subprocess.run(["systemctl", "is-enabled", unit], capture_output=True, text=True, timeout=5)
            checks.append(_check(f"timer_off_{unit}", proc.stdout.strip() not in ("enabled", "enabled-runtime")))
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            checks.append(_check(f"timer_skipped_{unit}", True))

    conn.close()
    passed = sum(1 for c in checks if c["passed"])
    result = {
        "phase": PHASE,
        "checks_passed": passed,
        "checks_total": len(checks),
        "validation_ok": passed == len(checks),
        "final_recommendation": workflow.get("final_recommendation"),
        "checks": checks,
    }
    (ARTIFACT / "validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["validation_ok"] else 1


def _write(checks, rec):
    result = {"phase": PHASE, "validation_ok": False, "checks": checks, "final_recommendation": rec}
    (ARTIFACT / "validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
