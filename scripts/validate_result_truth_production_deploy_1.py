#!/usr/bin/env python3
"""RESULT-TRUTH-PRODUCTION-DEPLOY-1 validation."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PHASE = "RESULT-TRUTH-PRODUCTION-DEPLOY-1"
ARTIFACT = ROOT / "artifacts" / "result_truth_production_deploy_1" / "validation.json"
WORKFLOW = ROOT / "artifacts" / "result_truth_production_deploy_1" / "workflow.json"
PREFLIGHT = ROOT / "RESULT_TRUTH_PRODUCTION_DEPLOY_1_PREFLIGHT.md"
REPORT = ROOT / "RESULT_TRUTH_PRODUCTION_DEPLOY_1_REPORT.md"

TARGET_IDS = [
    1567306, 1567307, 1567308, 1562586, 1567311, 1567309,
    1567312, 1565178, 1565179, 1567310, 1567824,
]

EXPECTED = {"wde": {"1x2": 7, "btts": 5, "ou": 5}, "ecse": {"top1": 1, "top3": 5, "top5": 7}}


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": bool(ok), "detail": detail}


def main() -> int:
    settings_path = os.environ.get("SQLITE_PATH", str(ROOT / "data" / "football_intelligence.db"))
    workflow = json.loads(WORKFLOW.read_text(encoding="utf-8")) if WORKFLOW.is_file() else {}
    blocked = workflow.get("final_recommendation") == "CODE_SYNC_REQUIRED_BEFORE_RESULT_DEPLOY"

    checks: list[dict] = []
    checks.append(_check("preflight_md_exists", PREFLIGHT.is_file()))
    checks.append(_check("report_md_exists", REPORT.is_file()))
    checks.append(_check("workflow_exists", WORKFLOW.is_file()))

    if blocked:
        checks.append(_check("deploy_blocked_code_sync", True, workflow.get("block_reason", "")))
        result = {
            "phase": PHASE,
            "deploy_blocked": True,
            "checks_passed": sum(1 for c in checks if c["passed"]),
            "checks_total": len(checks),
            "checks": checks,
            "validation_ok": all(c["passed"] for c in checks),
            "final_recommendation": "CODE_SYNC_REQUIRED_BEFORE_RESULT_DEPLOY",
        }
        ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0 if result["validation_ok"] else 1

    conn = sqlite3.connect(f"file:{settings_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cols = {r[1] for r in conn.execute("PRAGMA table_info(fixture_results)").fetchall()}
    for col in ("regulation_home_goals", "regulation_away_goals", "final_stage", "qualified_team", "result_synced_at"):
        checks.append(_check(f"column_{col}", col in cols))

    from worldcup_predictor.outcomes.market_result_resolver import resolve_market_result

    for fid in TARGET_IDS:
        fx = conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fid,)).fetchone()
        fr = conn.execute("SELECT * FROM fixture_results WHERE fixture_id=?", (fid,)).fetchone()
        checks.append(_check(f"fixture_{fid}_present", fx is not None and fr is not None))

    for fid, reg, qual in [(1567308, "2-2", "Belgium"), (1565179, "1-1", "Argentina"), (1565178, "1-1", "Egypt")]:
        fx = dict(conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fid,)).fetchone())
        fr = dict(conn.execute("SELECT * FROM fixture_results WHERE fixture_id=?", (fid,)).fetchone())
        r = resolve_market_result(fr, fx, market_type="1x2")
        q = resolve_market_result(fr, fx, market_type="qualification")
        checks.append(_check(f"aet_reg_{fid}", r.get("final_score") == reg and r.get("actual_result") == "draw"))
        checks.append(_check(f"aet_qual_{fid}", qual in str(q.get("qualified_team") or "")))

    tracker = (ROOT / "CONTROLLED_KNOCKOUT_PREDICTIONS_OWNER_TRACKER.md")
    if tracker.is_file():
        t = tracker.read_text(encoding="utf-8")
        checks.append(_check("canada_draw_in_tracker", "Canada vs Morocco" in t and "Draw" in t))

    metrics = workflow.get("metrics") or {}
    if metrics:
        wde, ecse = metrics.get("wde", {}), metrics.get("ecse", {})
        checks.append(_check("wde_1x2_match", wde.get("1x2") == EXPECTED["wde"]["1x2"], str(wde.get("1x2"))))
        checks.append(_check("ecse_top3_match", ecse.get("top3") == EXPECTED["ecse"]["top3"], str(ecse.get("top3"))))

    checks.append(_check("backup_documented", bool(workflow.get("backup_path"))))
    checks.append(_check("provider_calls_bounded", int(workflow.get("provider_calls", 999)) <= 30))
    checks.append(_check("payload_hashes_preserved", workflow.get("payload_hashes_preserved") is True))

    conn.close()
    passed = sum(1 for c in checks if c["passed"])
    result = {
        "phase": PHASE,
        "deploy_blocked": False,
        "checks_passed": passed,
        "checks_total": len(checks),
        "checks": checks,
        "validation_ok": passed == len(checks),
        "final_recommendation": workflow.get("final_recommendation"),
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["validation_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
