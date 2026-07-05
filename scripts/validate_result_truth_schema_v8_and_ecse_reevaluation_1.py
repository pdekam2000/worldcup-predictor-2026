#!/usr/bin/env python3
"""Validate RESULT-TRUTH-SCHEMA-V8-AND-ECSE-REEVALUATION-1."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ART = ROOT / "artifacts" / "result_truth_schema_v8_and_ecse_reevaluation_1"
PHASE = "RESULT-TRUTH-SCHEMA-V8-AND-ECSE-REEVALUATION-1"
ELIGIBLE = [
    1562344, 1565176, 1562345, 1564789, 1565177, 1567306, 1567307, 1567308,
    1562586, 1567311, 1567309, 1567312, 1565178, 1565179, 1567310, 1567824,
]
AET = {1567308, 1565179}


def _check(name, ok, detail=""):
    return {"check": name, "passed": bool(ok), "detail": detail}


def main() -> int:
    checks = []
    for fn in (
        "schema_forensic.json",
        "migration_result.json",
        "result_truth_backfill.jsonl",
        "aet_pen_audit.json",
        "ecse_before_after.json",
        "wde_evaluation_impact.json",
        "local_production_parity.json",
        "historical_replay_result_truth_contract.json",
        "workflow.json",
    ):
        checks.append(_check(f"artifact_{fn}", (ART / fn).is_file()))

    checks.extend([
        _check("report", Path("RESULT_TRUTH_SCHEMA_V8_AND_ECSE_REEVALUATION_1_REPORT.md").is_file()),
        _check("owner_report", Path("RESULT_TRUTH_SCHEMA_V8_OWNER_REPORT.md").is_file()),
        _check("ecse_owner", Path("ECSE_REEVALUATION_BEFORE_AFTER_OWNER_REPORT.md").is_file()),
    ])

    wf = json.loads((ART / "workflow.json").read_text(encoding="utf-8"))
    rec = wf.get("final_recommendation")
    checks.append(_check("recommendation_valid", rec in {
        "RESULT_TRUTH_V8_DEPLOYED_EVALUATIONS_CORRECTED",
        "RESULT_TRUTH_V8_DEPLOYED_NO_METRIC_CHANGES",
        "RESULT_TRUTH_V8_BLOCKED_BY_MISSING_REGULATION_DATA",
        "RESULT_TRUTH_DATA_INTEGRITY_ISSUE_FOUND",
    }, str(rec)))

    mig = json.loads((ART / "migration_result.json").read_text(encoding="utf-8"))
    checks.append(_check("migration_applied", mig.get("schema_after", 0) >= 8))
    checks.append(_check("no_destructive_migration", mig.get("destructive") is False))

    aet = json.loads((ART / "aet_pen_audit.json").read_text(encoding="utf-8"))
    for row in aet:
        fid = row["fixture_id"]
        checks.append(_check(
            f"aet_{fid}_regulation_explicit",
            row.get("regulation_explicit") and row.get("regulation_score") not in (None, row.get("final_match_score")),
            row.get("regulation_score"),
        ))

    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.outcomes.evaluation_score_policy import regulation_score_for_evaluation

    conn = sqlite3.connect(get_settings().sqlite_path)
    conn.row_factory = sqlite3.Row
    eligible_n = 0
    for fid in ELIGIBLE:
        fr = conn.execute("SELECT * FROM fixture_results WHERE fixture_id=?", (fid,)).fetchone()
        fx = conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fid,)).fetchone()
        snap = conn.execute("SELECT generated_at FROM ecse_prediction_snapshots WHERE fixture_id=? AND is_frozen=1 LIMIT 1", (fid,)).fetchone()
        if fr and fx and snap and str(fx["status"]).upper() in ("FT", "AET", "PEN"):
            eligible_n += 1
        if fid in AET:
            _, _, reg, basis = regulation_score_for_evaluation(dict(fr), dict(fx))
            final = f"{fr['home_goals']}-{fr['away_goals']}"
            checks.append(_check(f"aet_{fid}_ecse_uses_regulation", reg != final, f"reg={reg} final={final} basis={basis}"))

    checks.append(_check("eligible_fixtures_16", eligible_n == 16, str(eligible_n)))

    parity = json.loads((ART / "local_production_parity.json").read_text(encoding="utf-8"))
    if parity and "error" not in str(parity[0]):
        mism = [p for p in parity if p.get("status") != "OK"]
        checks.append(_check("local_prod_parity", len(mism) == 0, f"mismatches={len(mism)}"))
    else:
        checks.append(_check("local_prod_parity", False, "prod probe failed"))

    passed = sum(1 for c in checks if c["passed"])
    result = {"phase": PHASE, "checks_passed": passed, "checks_total": len(checks), "validation_ok": passed == len(checks), "checks": checks, "final_recommendation": rec}
    (ART / "validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["validation_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
