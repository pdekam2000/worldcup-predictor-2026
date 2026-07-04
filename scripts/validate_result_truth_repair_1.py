#!/usr/bin/env python3
"""RESULT-TRUTH-REPAIR-1 validation."""

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
from worldcup_predictor.outcomes.market_result_resolver import resolve_market_result

PHASE = "RESULT-TRUTH-REPAIR-1"
TARGET_IDS = [t["fixture_id"] for t in [
    {"fixture_id": 1567306}, {"fixture_id": 1567307}, {"fixture_id": 1567308},
    {"fixture_id": 1562586}, {"fixture_id": 1567311}, {"fixture_id": 1567309},
    {"fixture_id": 1567312}, {"fixture_id": 1565178}, {"fixture_id": 1565179},
    {"fixture_id": 1567310}, {"fixture_id": 1567824},
]]
ARTIFACT = ROOT / "artifacts" / "result_truth_repair_1" / "validation.json"
WORKFLOW = ROOT / "artifacts" / "result_truth_repair_1" / "workflow.json"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": bool(ok), "detail": detail}


def main() -> int:
    settings = get_settings()
    checks: list[dict] = []
    workflow = json.loads(WORKFLOW.read_text(encoding="utf-8")) if WORKFLOW.is_file() else {}

    checks.append(_check("workflow_exists", WORKFLOW.is_file()))
    checks.append(_check("backup_exists", bool(workflow.get("backup_path")) and Path(workflow["backup_path"]).is_file()))
    checks.append(_check("provider_calls_bounded", int(workflow.get("provider_calls", 999)) <= 30))
    checks.append(_check("payload_hashes_preserved", workflow.get("payload_hashes_before") == workflow.get("payload_hashes_after")))
    checks.append(_check("regulation_columns", bool(workflow.get("counts_after", {}).get("regulation_columns_present"))))

    before = workflow.get("counts_before") or {}
    after = workflow.get("counts_after") or {}
    for key in ("fixtures", "wde_predictions", "ecse_snapshots", "wde_evaluations"):
        checks.append(_check(f"row_count_{key}_preserved", before.get(key) == after.get(key), f"{before.get(key)} vs {after.get(key)}"))

    for md in (
        "RESULT_TRUTH_REPAIR_1_SCHEMA_AUDIT.md",
        "CANADA_MOROCCO_OWNER_TRACKER_DISCREPANCY_FORENSIC.md",
        "CANONICAL_11_MATCH_EVALUATION_SCORECARD.md",
        "PREDICTION_PAYLOAD_HASH_DRIFT_AUDIT.md",
        "RESULT_TRUTH_REPAIR_1_REPORT.md",
        "CONTROLLED_KNOCKOUT_PREDICTIONS_OWNER_TRACKER.md",
    ):
        checks.append(_check(f"report_{md}", (ROOT / md).is_file()))

    conn = sqlite3.connect(f"file:{settings.sqlite_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cols = {r[1] for r in conn.execute("PRAGMA table_info(fixture_results)").fetchall()}
    for col in ("regulation_home_goals", "regulation_away_goals", "final_stage", "qualified_team"):
        checks.append(_check(f"column_{col}", col in cols))

    for fid in TARGET_IDS:
        fx = conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fid,)).fetchone()
        fr = conn.execute("SELECT * FROM fixture_results WHERE fixture_id=?", (fid,)).fetchone()
        checks.append(_check(f"fixture_{fid}_present", fx is not None and fr is not None))
        if fr:
            checks.append(_check(
                f"fixture_{fid}_regulation",
                fr["regulation_home_goals"] is not None and fr["regulation_away_goals"] is not None,
            ))

    belgium = conn.execute("SELECT * FROM fixture_results WHERE fixture_id=1567308").fetchone()
    arg = conn.execute("SELECT * FROM fixture_results WHERE fixture_id=1565179").fetchone()
    aus = conn.execute("SELECT * FROM fixture_results WHERE fixture_id=1565178").fetchone()
    if belgium:
        fx = dict(conn.execute("SELECT * FROM fixtures WHERE fixture_id=1567308").fetchone())
        reg = resolve_market_result(dict(belgium), fx, market_type="1x2")
        checks.append(_check("belgium_90m_2_2", reg.get("final_score") == "2-2"))
        checks.append(_check("belgium_1x2_draw", reg.get("actual_result") == "draw"))
    if arg:
        fx = dict(conn.execute("SELECT * FROM fixtures WHERE fixture_id=1565179").fetchone())
        reg = resolve_market_result(dict(arg), fx, market_type="1x2")
        checks.append(_check("argentina_90m_1_1", reg.get("final_score") == "1-1"))
        checks.append(_check("argentina_1x2_draw", reg.get("actual_result") == "draw"))
    if aus:
        fx = dict(conn.execute("SELECT * FROM fixtures WHERE fixture_id=1565178").fetchone())
        reg = resolve_market_result(dict(aus), fx, market_type="1x2")
        qual = resolve_market_result(dict(aus), fx, market_type="qualification")
        checks.append(_check("australia_90m_1_1", reg.get("final_score") == "1-1"))
        checks.append(_check("egypt_qualified", "Egypt" in str(qual.get("qualified_team") or "")))

    tracker = (ROOT / "CONTROLLED_KNOCKOUT_PREDICTIONS_OWNER_TRACKER.md").read_text(encoding="utf-8") if (ROOT / "CONTROLLED_KNOCKOUT_PREDICTIONS_OWNER_TRACKER.md").is_file() else ""
    checks.append(_check("tracker_canada_draw", "Canada vs Morocco" in tracker and "| Draw |" in tracker))
    checks.append(_check("tracker_source_db_only", "frozen DB rows only" in tracker))

    canada = conn.execute("SELECT payload_json FROM worldcup_stored_predictions WHERE fixture_id=1567824").fetchone()
    if canada:
        payload = json.loads(canada["payload_json"])
        from worldcup_predictor.api.market_level_evaluation import canonical_1x2_selection
        checks.append(_check("canada_authoritative_draw", str(canonical_1x2_selection(payload)).lower() == "draw"))

    conn.close()
    passed = sum(1 for c in checks if c["passed"])
    result = {
        "phase": PHASE,
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
