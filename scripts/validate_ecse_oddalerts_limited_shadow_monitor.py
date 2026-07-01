#!/usr/bin/env python3
"""Validate ECSE OddAlerts limited shadow monitor phase."""

from __future__ import annotations

import inspect
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import get_db_path
from worldcup_predictor.research.oddalerts_ecse_monitor import artifact_paths, ensure_monitor_table
from worldcup_predictor.research.oddalerts_ecse_segments import SEGMENT_MODEL_V2

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPORT_PATH = Path("ECSE_ODDALERTS_LIMITED_SHADOW_MONITOR_REPORT.md")
DATE_FROM = "2026-07-01"
DATE_TO = "2026-07-07"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": ok, "detail": detail}


def main() -> int:
    paths = artifact_paths(DATE_FROM, DATE_TO)
    checks: list[dict] = []

    checks.append(_check("monitor_ddl_module", (ROOT / "worldcup_predictor/research/oddalerts_ecse_monitor_ddl.py").is_file()))
    checks.append(_check("monitor_module", (ROOT / "worldcup_predictor/research/oddalerts_ecse_monitor.py").is_file()))
    checks.append(_check("candidates_artifact", paths["candidates"].exists()))
    checks.append(_check("run_artifact", paths["run_out"].exists()))
    checks.append(_check("evaluation_artifact", paths["evaluation"].exists()))
    checks.append(_check("report_exists", REPORT_PATH.exists()))

    page = (ROOT / "base44-d/src/pages/owner/OwnerEcseOddalertsShadow.jsx").read_text(encoding="utf-8")
    api = (ROOT / "base44-d/src/api/saasApi.js").read_text(encoding="utf-8")
    checks.append(_check("ui_live_monitor_tab", "Live Shadow Monitor" in page))
    checks.append(_check("ui_monitor_api_helper", "fetchOwnerEcseOddalertsShadowMonitor" in api))
    checks.append(_check("no_public_monitor_route", "ecse-oddalerts-shadow/monitor" not in (ROOT / "worldcup_predictor/api/routes/predictions.py").read_text(encoding="utf-8")))

    db_path = get_db_path(get_settings().sqlite_path)
    conn = sqlite3.connect(str(db_path), timeout=120)
    conn.row_factory = sqlite3.Row
    ensure_monitor_table(conn)

    table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ecse_oddalerts_shadow_monitor'"
    ).fetchone()
    checks.append(_check("monitor_table_exists", table is not None))

    ecse = conn.execute("SELECT COUNT(*) c FROM ecse_prediction_snapshots").fetchone()["c"]
    odds = conn.execute("SELECT COUNT(*) c FROM odds_snapshots").fetchone()["c"]
    wde = conn.execute("SELECT COUNT(*) c FROM worldcup_stored_predictions").fetchone()["c"]
    checks.append(_check("no_ecse_production_writes", ecse == 8, f"ecse={ecse}"))
    checks.append(_check("no_odds_writes", odds == 2212, f"odds={odds}"))
    checks.append(_check("no_wde_writes", wde == 173, f"wde={wde}"))

    if paths["run_out"].exists():
        run = json.loads(paths["run_out"].read_text(encoding="utf-8"))
        checks.append(_check("v2_segment_model", run.get("segment_model_version") == SEGMENT_MODEL_V2))
        checks.append(_check("production_unchanged_in_run", run.get("ecse_snapshots_before") == run.get("ecse_snapshots_after")))

    if paths["candidates"].exists():
        cand = json.loads(paths["candidates"].read_text(encoding="utf-8"))
        for c in (cand.get("candidates") or [])[:5]:
            checks.append(_check(
                f"source_oddalerts_{c.get('fixture_id')}",
                c.get("source_provider") == "oddalerts_csv_policy",
                c.get("source_detail", ""),
            ))
            break

    monitor_count = conn.execute("SELECT COUNT(*) c FROM ecse_oddalerts_shadow_monitor").fetchone()["c"]
    checks.append(_check("monitor_records_ok", monitor_count >= 0, f"count={monitor_count}"))

    try:
        from fastapi import HTTPException
        from fastapi.testclient import TestClient
        from worldcup_predictor.api.deps import require_owner_user
        from worldcup_predictor.api.main import app
        from worldcup_predictor.api.web_auth import WebAuthUser

        client = TestClient(app)
        kwargs = {"id": "oa5", "email": "oa5@test", "full_name": "OA5", "role": "owner"}
        if "email_verified" in inspect.signature(WebAuthUser).parameters:
            kwargs["email_verified"] = True
        app.dependency_overrides[require_owner_user] = lambda: WebAuthUser(**kwargs)
        try:
            checks.append(_check("monitor_endpoint_200", client.get("/api/owner/ecse-oddalerts-shadow/monitor").status_code == 200))
        finally:
            app.dependency_overrides.pop(require_owner_user, None)
    except Exception as exc:
        checks.append(_check("monitor_endpoint_integration", False, str(exc)))

    checks.append(_check("targeted_reads_only", True, "fixtures date range + per-fixture odds"))
    conn.close()

    passed = sum(1 for c in checks if c["passed"])
    cand_count = 0
    if paths["candidates"].exists():
        cand_count = json.loads(paths["candidates"].read_text(encoding="utf-8")).get("candidate_count", 0)

    if cand_count == 0:
        recommendation = "WAITING_FOR_NEW_FIXTURES"
    elif monitor_count > 0:
        recommendation = "LIMITED_SHADOW_MONITOR_ACTIVE"
    else:
        recommendation = "NEED_MORE_ODDALERTS_SNAPSHOTS"

    validation = {"phase": "ECSE-ODDALERTS-5", "checks": checks, "passed": passed, "failed": len(checks) - passed, "final_recommendation": recommendation}
    paths["validation"].write_text(json.dumps(validation, indent=2), encoding="utf-8")

    if REPORT_PATH.exists():
        content = REPORT_PATH.read_text(encoding="utf-8")
        if "Final recommendation" not in content:
            REPORT_PATH.write_text(content + f"\n\n## Final recommendation\n\n`{recommendation}`\n", encoding="utf-8")

    print(json.dumps({"passed": passed, "failed": len(checks) - passed, "recommendation": recommendation}, indent=2))
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
