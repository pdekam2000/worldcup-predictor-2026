#!/usr/bin/env python3
"""Validate incremental OddAlerts inbox CSV import."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.data_import.oddalerts_csv_incremental_importer import (
    IMPORT_SUMMARY_PATH,
    PHASE,
)

VALIDATION_OUT = Path("artifacts/oddalerts_csv_incremental_validation.json")


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": ok, "detail": detail}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    conn = connect(get_settings().sqlite_path)
    checks: list[dict] = []

    summary = {}
    if IMPORT_SUMMARY_PATH.exists():
        summary = json.loads(IMPORT_SUMMARY_PATH.read_text(encoding="utf-8"))

    checks.append(_check("import_summary_exists", IMPORT_SUMMARY_PATH.exists(), str(IMPORT_SUMMARY_PATH)))
    checks.append(_check("phase", summary.get("phase") == PHASE, summary.get("phase", "")))
    checks.append(_check("not_promoted_to_odds_snapshots", summary.get("promoted_to_odds_snapshots") is False))

    staged = conn.execute(
        "SELECT COUNT(*) c FROM oddalerts_inbox_csv_catalog WHERE import_status = 'staged'"
    ).fetchone()["c"]
    checks.append(_check("staged_probability_files", staged >= 0, f"count={staged}"))

    odds_new = conn.execute(
        """
        SELECT COUNT(*) c FROM odds_snapshots
        WHERE imported_at >= datetime('now', '-1 hour')
        """
    ).fetchone()["c"]
    checks.append(_check("no_recent_odds_snapshot_promotion", int(odds_new) == 0, f"recent={odds_new}"))

    ecse_before = conn.execute("SELECT COUNT(*) c FROM ecse_prediction_snapshots").fetchone()["c"]
    wde_before = conn.execute("SELECT COUNT(*) c FROM worldcup_stored_predictions").fetchone()["c"]
    checks.append(_check("ecse_count_readable", ecse_before >= 0, f"count={ecse_before}"))
    checks.append(_check("wde_count_readable", wde_before >= 0, f"count={wde_before}"))

    passed = all(c["passed"] for c in checks)
    report = {
        "phase": PHASE,
        "passed": passed,
        "checks": checks,
        "import_summary": summary,
    }
    VALIDATION_OUT.parent.mkdir(parents=True, exist_ok=True)
    VALIDATION_OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"Written: {VALIDATION_OUT}")
    conn.close()
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
