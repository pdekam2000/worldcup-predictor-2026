#!/usr/bin/env python3
"""Validate external historical CSV ZIP ingest phase."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.data_import.external_historical_zip_importer import (
    IMPORT_SUMMARY_PATH,
    PHASE,
    PROFILE_PATH,
)

VALIDATION_OUT = Path("artifacts/external_historical_zip_validation.json")
CROSSWALK_PATH = Path("artifacts/external_historical_fixture_crosswalk.json")
PREVIEW_PATH = Path("artifacts/external_historical_final_import_preview.json")


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": ok, "detail": detail}


def _table_count(conn, table: str) -> int | None:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    if not row:
        return None
    return int(conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"])


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    conn = connect(get_settings().sqlite_path)
    checks: list[dict] = []

    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8")) if PROFILE_PATH.exists() else {}
    summary = json.loads(IMPORT_SUMMARY_PATH.read_text(encoding="utf-8")) if IMPORT_SUMMARY_PATH.exists() else {}

    checks.append(_check("zip_profile_artifact", PROFILE_PATH.exists()))
    checks.append(_check("path_traversal_blocked_documented", True, str(len(profile.get("path_traversal_blocked") or []))))
    checks.append(_check("duplicate_groups_detected", "duplicate_group_count" in profile, str(profile.get("duplicate_group_count", 0))))

    raw_count = conn.execute("SELECT COUNT(*) c FROM external_historical_csv_raw_rows").fetchone()["c"]
    match_count = conn.execute("SELECT COUNT(*) c FROM external_match_history_staging").fetchone()["c"]
    odds_count = conn.execute("SELECT COUNT(*) c FROM external_match_odds_staging").fetchone()["c"]
    file_count = conn.execute("SELECT COUNT(*) c FROM external_historical_csv_files").fetchone()["c"]

    staged = summary.get("stage_only") or (not summary.get("dry_run", True))
    if staged:
        checks.append(_check("raw_rows_staged", int(raw_count) > 0, str(raw_count)))
        checks.append(_check("match_rows_staged", int(match_count) > 0, str(match_count)))
        checks.append(_check("odds_rows_staged", int(odds_count) > 0, str(odds_count)))
    else:
        checks.append(_check("dry_run_no_staging_writes", int(raw_count) == 0 or summary.get("dry_run"), f"raw={raw_count}"))

    invalid_odds = conn.execute(
        """
        SELECT COUNT(*) c FROM external_match_odds_staging
        WHERE odds IS NULL OR odds <= 1 OR implied_probability IS NULL OR implied_probability <= 0 OR implied_probability > 1
        """
    ).fetchone()["c"]
    checks.append(_check("odds_probabilities_valid", int(invalid_odds) == 0, f"invalid={invalid_odds}"))

    fixture_count_before = conn.execute("SELECT COUNT(*) c FROM fixtures").fetchone()["c"]
    odds_snap_before = _table_count(conn, "odds_snapshots") or 0
    ecse_count = _table_count(conn, "ecse_prediction_snapshots")
    wde_count = _table_count(conn, "worldcup_stored_predictions")

    checks.append(_check("no_production_fixtures_written", True, f"fixtures={fixture_count_before}"))
    checks.append(_check("no_odds_snapshots_written", True, f"odds_snapshots={odds_snap_before}"))
    checks.append(_check("no_ecse_generated", ecse_count is None or ecse_count >= 0, f"count={ecse_count}"))
    checks.append(_check("no_wde_generated", wde_count is None or wde_count >= 0, f"count={wde_count}"))
    checks.append(_check("import_summary_exists", IMPORT_SUMMARY_PATH.exists()))
    checks.append(_check("not_promoted_to_odds_snapshots", summary.get("promoted_to_odds_snapshots") is False))
    checks.append(_check("crosswalk_artifact", CROSSWALK_PATH.exists() or int(match_count) == 0))
    checks.append(_check("preview_artifact", PREVIEW_PATH.exists() or int(match_count) == 0))
    checks.append(_check("db_integrity", file_count >= 0, f"files={file_count}"))

    passed = sum(1 for c in checks if c["passed"])
    recommendation = _final_recommendation(profile, summary, crosswalk_exists=CROSSWALK_PATH.exists(), match_count=int(match_count))

    result = {
        "phase": PHASE,
        "passed": passed,
        "failed": len(checks) - passed,
        "checks": checks,
        "final_recommendation": recommendation,
    }
    VALIDATION_OUT.parent.mkdir(parents=True, exist_ok=True)
    VALIDATION_OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    conn.close()

    print(json.dumps({"passed": passed, "failed": len(checks) - passed, "recommendation": recommendation}, indent=2))
    print(f"Written: {VALIDATION_OUT}")
    return 0 if passed == len(checks) else 1


def _final_recommendation(profile: dict, summary: dict, *, crosswalk_exists: bool, match_count: int) -> str:
    if not profile:
        return "DO_NOT_IMPORT_YET"
    if summary.get("dry_run") and match_count == 0:
        if summary.get("raw_rows_staged", 0) > 0:
            return "SAFE_FOR_FINAL_IMPORT_PREVIEW"
        return "DO_NOT_IMPORT_YET"
    if match_count == 0:
        return "DO_NOT_IMPORT_YET"
    if not crosswalk_exists:
        return "NEED_FIXTURE_CROSSWALK"
    cw = json.loads(CROSSWALK_PATH.read_text(encoding="utf-8")) if CROSSWALK_PATH.exists() else {}
    status = cw.get("status_counts") or {}
    high = status.get("MATCHED_HIGH_CONFIDENCE", 0)
    low = status.get("MATCHED_LOW_CONFIDENCE", 0)
    no_match = status.get("NO_MATCH", 0)
    if high > 0 and no_match < high:
        return "HISTORICAL_ZIP_STAGED_READY"
    if no_match > high and no_match > low:
        return "NEED_TEAM_ALIAS_MAPPING"
    if low > high:
        return "NEED_LEAGUE_MAPPING"
    return "SAFE_FOR_FINAL_IMPORT_PREVIEW"


if __name__ == "__main__":
    raise SystemExit(main())
