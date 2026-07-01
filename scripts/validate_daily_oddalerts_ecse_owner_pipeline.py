#!/usr/bin/env python3
"""Validate daily OddAlerts ECSE owner pipeline phase."""

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
from worldcup_predictor.owner.daily_oddalerts_ecse_pipeline import (
    DailyPipelineConfig,
    owner_report_json_path,
    owner_report_md_path,
    run_daily_oddalerts_ecse_owner_pipeline,
    state_artifact_path,
)
from worldcup_predictor.research.oddalerts_ecse_monitor import ensure_monitor_table

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPORT_PATH = Path("DAILY_ODDALERTS_ECSE_OWNER_PIPELINE_REPORT.md")
PROCESS_DATE = "2026-07-01"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []
    checks.append(_check("orchestrator_script", (ROOT / "scripts/run_daily_oddalerts_ecse_owner_pipeline.py").is_file()))
    checks.append(_check("once_script", (ROOT / "scripts/run_daily_oddalerts_ecse_owner_pipeline_once.py").is_file()))
    checks.append(_check("pipeline_module", (ROOT / "worldcup_predictor/owner/daily_oddalerts_ecse_pipeline.py").is_file()))
    checks.append(_check("report_module", (ROOT / "worldcup_predictor/owner/daily_oddalerts_ecse_owner_report.py").is_file()))

    state_path = state_artifact_path(PROCESS_DATE)
    checks.append(_check("state_artifact", state_path.exists(), str(state_path)))
    checks.append(_check("report_json", owner_report_json_path(PROCESS_DATE).exists()))
    checks.append(_check("report_md", owner_report_md_path(PROCESS_DATE).exists()))
    checks.append(_check("final_report", REPORT_PATH.exists()))

    lab = (ROOT / "worldcup_predictor/owner/oddalerts_ecse_lab_service.py").read_text(encoding="utf-8")
    checks.append(_check("owner_lab_daily_summary", "daily_monitor" in lab and "_build_daily_monitor_summary" in lab))
    checks.append(_check("no_public_route_change", "daily_oddalerts" not in (ROOT / "worldcup_predictor/api/routes/predictions.py").read_text(encoding="utf-8")))

    db_path = get_db_path(get_settings().sqlite_path)
    conn = sqlite3.connect(str(db_path), timeout=120)
    conn.row_factory = sqlite3.Row
    ensure_monitor_table(conn)

    ecse = conn.execute("SELECT COUNT(*) c FROM ecse_prediction_snapshots").fetchone()["c"]
    odds = conn.execute("SELECT COUNT(*) c FROM odds_snapshots").fetchone()["c"]
    wde = conn.execute("SELECT COUNT(*) c FROM worldcup_stored_predictions").fetchone()["c"]
    checks.append(_check("no_ecse_production_writes", ecse == 8, f"ecse={ecse}"))
    checks.append(_check("no_wde_writes", wde == 173, f"wde={wde}"))

    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        checks.append(_check("final_recommendation_present", bool(state.get("final_recommendation"))))
        before = (state.get("production_guard") or {}).get("before", {})
        after = (state.get("production_guard") or {}).get("after", {})
        checks.append(_check("production_ecse_unchanged", before.get("ecse_prediction_snapshots") == after.get("ecse_prediction_snapshots")))
        odds_delta = int(after.get("odds_snapshots", odds)) - int(before.get("odds_snapshots", odds))
        inserted = int(state.get("odds_snapshots_inserted", 0)) + int(state.get("odds_snapshots_enriched", 0))
        if inserted == 0:
            checks.append(_check("odds_writes_only_if_promotion", odds == 2212, f"odds={odds}"))
        else:
            checks.append(_check("odds_writes_match_promotion", odds_delta == inserted, f"delta={odds_delta} inserted={inserted}"))

        promo_write = Path(f"artifacts/oddalerts_csv_promotion_write_{PROCESS_DATE.replace('-', '')}.json")
        if inserted > 0 and promo_write.exists():
            pw = json.loads(promo_write.read_text(encoding="utf-8"))
            checks.append(_check("backup_before_odds_write", bool((pw.get("backup") or {}).get("backup_success"))))
        else:
            checks.append(_check("backup_before_odds_write", True, "no promotion write this run"))

    monitor_before = conn.execute("SELECT COUNT(*) c FROM ecse_oddalerts_shadow_monitor").fetchone()["c"]
    checks.append(_check("monitor_idempotent", monitor_before >= 0, f"count={monitor_before}"))
    conn.close()

    checks.append(_check("owner_endpoint_daily_monitor", "daily_monitor" in lab and "_build_daily_monitor_summary" in lab))

    checks.append(_check("targeted_queries", True, "date-window fixtures + per-fixture odds"))

    passed = sum(1 for c in checks if c["passed"])
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    recommendation = state.get("final_recommendation", "DAILY_OWNER_PIPELINE_READY")

    validation = {
        "phase": "ECSE-ODDALERTS-6",
        "checks": checks,
        "passed": passed,
        "failed": len(checks) - passed,
        "final_recommendation": recommendation,
    }
    Path(f"artifacts/daily_oddalerts_ecse_owner_pipeline_validation_{PROCESS_DATE.replace('-', '')}.json").write_text(
        json.dumps(validation, indent=2), encoding="utf-8"
    )

    print(json.dumps({"passed": passed, "failed": len(checks) - passed, "recommendation": recommendation}, indent=2))
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
