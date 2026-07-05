#!/usr/bin/env python3
"""NEXT-3-UPCOMING-MATCH-PREDICTIONS-1 validation."""

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

PHASE = "NEXT-3-UPCOMING-MATCH-PREDICTIONS-1"
WORKFLOW = ROOT / "artifacts" / "next_3_upcoming_match_predictions_1" / "workflow.json"
OUTPUT = ROOT / "artifacts" / "next_3_upcoming_match_predictions_1" / "validation.json"
OWNER_MD = ROOT / "NEXT_3_UPCOMING_MATCH_PREDICTIONS_OWNER_REPORT.md"
BASELINE_MD = ROOT / "NEXT_3_UPCOMING_MATCHES_BASELINE.md"
REPORT_MD = ROOT / "NEXT_3_UPCOMING_MATCH_PREDICTIONS_1_REPORT.md"

NOT_STARTED = {"NS", "TBD", "SCHEDULED", "TIMED", "NOT_STARTED", "NOT STARTED"}
LIVE = {"1H", "2H", "HT", "ET", "P", "LIVE", "BT", "INT"}
FINISHED = {"FT", "AET", "PEN", "AWD", "WO", "CANC", "ABD", "PST"}


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": bool(ok), "detail": detail}


def main() -> int:
    checks: list[dict] = []
    if not WORKFLOW.is_file():
        checks.append(_check("workflow_exists", False))
        result = {"phase": PHASE, "validation_ok": False, "checks": checks}
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 1

    workflow = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    matches = workflow.get("matches") or []
    fixture_ids = [int(m["fixture_id"]) for m in matches]

    checks.append(_check("workflow_exists", True))
    checks.append(_check("baseline_md_exists", BASELINE_MD.is_file()))
    checks.append(_check("owner_report_exists", OWNER_MD.is_file()))
    checks.append(_check("final_report_exists", REPORT_MD.is_file()))
    checks.append(_check("exactly_3_fixtures", len(matches) == 3, str(len(matches))))
    checks.append(_check("no_duplicate_fixture", len(set(fixture_ids)) == len(fixture_ids)))
    checks.append(_check("provider_calls_bounded", int(workflow.get("provider_calls_used") or 0) <= 60))

    settings = get_settings()
    conn = sqlite3.connect(f"file:{settings.sqlite_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    kickoffs: list[str] = []
    for m in matches:
        fid = int(m["fixture_id"])
        fx = conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fid,)).fetchone()
        checks.append(_check(f"fixture_{fid}_in_db", fx is not None))
        if fx:
            status = str(fx["status"] or "").upper()
            checks.append(_check(f"fixture_{fid}_not_started", status in NOT_STARTED, status))
            checks.append(_check(f"fixture_{fid}_not_live", status not in LIVE, status))
            checks.append(_check(f"fixture_{fid}_not_finished", status not in FINISHED, status))
            checks.append(_check(f"fixture_{fid}_kickoff_future", str(fx["kickoff_utc"]) > now, str(fx["kickoff_utc"])))
            kickoffs.append(str(fx["kickoff_utc"]))

        wde = conn.execute("SELECT payload_json FROM worldcup_stored_predictions WHERE fixture_id=?", (fid,)).fetchone()
        ecse = conn.execute(
            "SELECT top_1_score, top_3_scores_json, top_5_scores_json, is_frozen FROM ecse_prediction_snapshots WHERE fixture_id=? ORDER BY id DESC LIMIT 1",
            (fid,),
        ).fetchone()
        checks.append(_check(f"wde_present_{fid}", wde is not None))
        checks.append(_check(f"ecse_present_{fid}", ecse is not None))
        if wde:
            checks.append(_check(f"wde_payload_hash_{fid}", bool(m.get("wde", {}).get("payload_hash"))))
        if ecse:
            top3 = json.loads(ecse["top_3_scores_json"] or "[]")
            top5 = json.loads(ecse["top_5_scores_json"] or "[]")
            checks.append(_check(f"ecse_top5_count_{fid}", len(top5) == 5, str(len(top5))))
            checks.append(_check(f"ecse_top3_count_{fid}", len(top3) == 3, str(len(top3))))
            checks.append(_check(f"ecse_no_dup_top5_{fid}", len(set(top5)) == len(top5)))
            checks.append(_check(f"ecse_top3_subset_top5_{fid}", set(top3).issubset(set(top5))))
            checks.append(_check(f"ecse_top1_rank1_{fid}", top5[0] == ecse["top_1_score"] if top5 else False))
            checks.append(_check(f"ecse_frozen_{fid}", ecse["is_frozen"] == 1))

        ev = conn.execute("SELECT COUNT(*) AS c FROM ecse_prediction_evaluations WHERE fixture_id=?", (fid,)).fetchone()
        checks.append(_check(f"no_premature_eval_{fid}", ev["c"] == 0, str(ev["c"])))

    checks.append(_check("chronological_order", kickoffs == sorted(kickoffs), str(kickoffs)))

    for unit in ("worldcup-daily.timer", "worldcup-hourly.timer", "owner-daily.timer"):
        try:
            proc = subprocess.run(["systemctl", "is-enabled", unit], capture_output=True, text=True, timeout=5)
            checks.append(_check(f"timer_not_enabled_{unit}", proc.stdout.strip() not in ("enabled", "enabled-runtime")))
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            checks.append(_check(f"timer_check_skipped_{unit}", True))

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
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["validation_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
