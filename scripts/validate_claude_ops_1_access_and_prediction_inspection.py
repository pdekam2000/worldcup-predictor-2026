#!/usr/bin/env python3
"""CLAUDE-OPS-1 — Validate access docs and read-only prediction inspection."""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PHASE = "CLAUDE-OPS-1-VALIDATION"
FORBIDDEN_DOC_PATTERNS = [
    r"rm\s+data/football_intelligence\.db",
    r"copy.*local DB.*production",
    r"commit.*\.db",
    r"\.env",
    r"api keys",
]


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []

    checklist = ROOT / "CLAUDE_ACCESS_CHECKLIST.md"
    runbook = ROOT / "CLAUDE_PRODUCTION_RUNBOOK.md"
    script = ROOT / "scripts" / "show_owner_predictions.py"
    checks.append(_check("checklist_doc_exists", checklist.is_file()))
    checks.append(_check("runbook_doc_exists", runbook.is_file()))
    checks.append(_check("show_owner_predictions_exists", script.is_file()))

    # Imports
    try:
        from worldcup_predictor.owner.prediction_inspection import (  # noqa: F401
            inspect_owner_predictions,
        )

        checks.append(_check("inspection_module_imports", True))
    except Exception as exc:
        checks.append(_check("inspection_module_imports", False, str(exc)))

    # CLI argparse support
    try:
        src = script.read_text(encoding="utf-8")
        for flag in ("--date", "--scope", "--format", "--market", "--limit"):
            checks.append(_check(f"cli_supports_{flag.lstrip('-').replace('-', '_')}", flag in src))
    except Exception as exc:
        checks.append(_check("cli_argparse_scan", False, str(exc)))

    # Scope / format values in module
    try:
        from worldcup_predictor.owner import prediction_inspection as pi

        checks.append(_check("scope_stored", "stored" in str(pi.Scope)))
        checks.append(_check("scope_evaluated", "evaluated" in str(pi.Scope)))
        checks.append(_check("scope_pending", "pending" in str(pi.Scope)))
        checks.append(_check("scope_all", "all" in str(pi.Scope)))
    except Exception as exc:
        checks.append(_check("scope_literals", False, str(exc)))

    # Missing DB handling
    try:
        from worldcup_predictor.owner.prediction_inspection import (
            DB_MISSING_MSG,
            InspectionConfig,
            inspect_owner_predictions,
        )

        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope.db"
            r = inspect_owner_predictions(InspectionConfig(db_path=str(missing)))
            checks.append(
                _check(
                    "missing_db_clean_error",
                    r.get("error") == DB_MISSING_MSG,
                    str(r.get("error")),
                )
            )
    except Exception as exc:
        checks.append(_check("missing_db_clean_error", False, str(exc)))

    # No provider calls in inspection module
    try:
        mod_src = (ROOT / "worldcup_predictor" / "owner" / "prediction_inspection.py").read_text(
            encoding="utf-8"
        )
        provider_hits = [
            name
            for name in (
                "ApiFootballClient",
                "SportmonksProvider",
                "OddAlertsClient",
                "requests.get",
                "httpx.",
            )
            if name in mod_src
        ]
        checks.append(_check("no_provider_calls_in_inspection", not provider_hits, str(provider_hits)))
    except Exception as exc:
        checks.append(_check("no_provider_calls_in_inspection", False, str(exc)))

    # DB read-only — no writes in inspection module
    try:
        mod_src = (ROOT / "worldcup_predictor" / "owner" / "prediction_inspection.py").read_text(
            encoding="utf-8"
        )
        write_ops = [tok for tok in ("INSERT ", "UPDATE ", "DELETE ", "executemany") if tok in mod_src.upper()]
        checks.append(_check("inspection_no_db_mutations", not write_ops, str(write_ops)))
    except Exception as exc:
        checks.append(_check("inspection_no_db_mutations", False, str(exc)))

    # Secret redaction helper
    try:
        from worldcup_predictor.owner.prediction_inspection import sanitize_for_output

        sample = sanitize_for_output("API_KEY=supersecret12345")
        checks.append(
            _check(
                "no_secrets_in_sanitize",
                "supersecret" not in sample and "***" in sample,
                sample[:80],
            )
        )
    except Exception as exc:
        checks.append(_check("no_secrets_in_sanitize", False, str(exc)))

    # Empty predictions message
    try:
        from worldcup_predictor.owner.prediction_inspection import NO_PREDICTIONS_MSG

        checks.append(_check("empty_predictions_constant", bool(NO_PREDICTIONS_MSG)))
    except Exception as exc:
        checks.append(_check("empty_predictions_constant", False, str(exc)))

    # Dry-run documented
    runbook_text = runbook.read_text(encoding="utf-8") if runbook.is_file() else ""
    checks.append(
        _check(
            "pipeline_dry_run_documented",
            "run_production_prediction_pipeline.py --mode daily --dry-run" in runbook_text,
        )
    )

    # Forbidden actions documented
    for i, pattern in enumerate(FORBIDDEN_DOC_PATTERNS):
        checks.append(_check(f"forbidden_doc_{i}", bool(re.search(pattern, runbook_text, re.I))))

    # Optional admin endpoint
    endpoint_file = ROOT / "worldcup_predictor" / "api" / "routes" / "admin_owner_predictions.py"
    if endpoint_file.is_file():
        ep_src = endpoint_file.read_text(encoding="utf-8")
        checks.append(_check("endpoint_file_exists", True))
        checks.append(_check("endpoint_admin_only", "require_admin_user" in ep_src))
        checks.append(_check("endpoint_read_only", "inspect_owner_predictions" in ep_src))
        checks.append(
            _check(
                "endpoint_no_mutations",
                not any(x in ep_src.upper() for x in ("INSERT ", "UPDATE ", "DELETE ")),
            )
        )
        endpoint_added = "admin_owner_predictions_router" in (ROOT / "worldcup_predictor" / "api" / "main.py").read_text(
            encoding="utf-8"
        )
        checks.append(_check("endpoint_registered_in_main", endpoint_added))
    else:
        checks.append(_check("endpoint_skipped", True, "CLI only"))

    # Prediction engine unchanged — no edits to WDE core scoring files in this phase
    wde_scoring = ROOT / "worldcup_predictor" / "orchestration" / "predict_pipeline.py"
    checks.append(_check("wde_pipeline_file_exists", wde_scoring.is_file()))

    # show_project_version
    checks.append(_check("show_project_version_exists", (ROOT / "scripts" / "show_project_version.py").is_file()))

    # Local DB smoke if present
    db_path = ROOT / "data" / "football_intelligence.db"
    if db_path.is_file() and db_path.stat().st_size > 0:
        try:
            from worldcup_predictor.owner.prediction_inspection import InspectionConfig, inspect_owner_predictions

            r = inspect_owner_predictions(InspectionConfig(date_arg="today", limit=5))
            checks.append(
                _check(
                    "local_db_read_smoke",
                    r.get("status") in {"ok", "empty"},
                    f"status={r.get('status')} count={r.get('count', 0)}",
                )
            )
        except Exception as exc:
            checks.append(_check("local_db_read_smoke", False, str(exc)))
    else:
        checks.append(_check("local_db_read_smoke", True, "skipped_no_local_db"))

    # DB read-only — immutability on isolated temp DB
    try:
        from worldcup_predictor.owner.prediction_inspection import InspectionConfig, inspect_owner_predictions

        with tempfile.TemporaryDirectory() as tmp:
            tmp_db = Path(tmp) / "test.db"
            conn = sqlite3.connect(tmp_db)
            conn.execute(
                """
                CREATE TABLE worldcup_stored_predictions (
                    fixture_id INTEGER PRIMARY KEY,
                    competition_key TEXT,
                    kickoff_utc TEXT,
                    payload_json TEXT,
                    source TEXT,
                    predicted_at TEXT,
                    updated_at TEXT
                )
                """
            )
            conn.execute(
                """
                INSERT INTO worldcup_stored_predictions
                (fixture_id, competition_key, kickoff_utc, payload_json, source, predicted_at, updated_at)
                VALUES (1, 'world_cup_2026', '2026-07-03T18:00:00+00:00',
                '{"one_x_two":{"selection":"home_win"},"confidence_score":70}', 'test', '2026-07-02', '2026-07-02')
                """
            )
            conn.commit()
            conn.close()
            def _row_count() -> int:
                c = sqlite3.connect(tmp_db)
                try:
                    return int(c.execute("SELECT COUNT(*) FROM worldcup_stored_predictions").fetchone()[0])
                finally:
                    c.close()

            before_count = _row_count()
            inspect_owner_predictions(
                InspectionConfig(date_arg="2026-07-03", db_path=str(tmp_db), limit=5)
            )
            after_count = _row_count()
            checks.append(_check("db_rowcount_unchanged_after_read", before_count == after_count))
    except Exception as exc:
        checks.append(_check("db_rowcount_unchanged_after_read", False, str(exc)))

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    all_passed = passed == total

    if all_passed:
        recommendation = "CLAUDE_OPS_READY"
    elif endpoint_file.is_file():
        recommendation = "CLAUDE_OPS_VALIDATION_FAILED"
    else:
        recommendation = "CLAUDE_OPS_VALIDATION_FAILED"

    report = {
        "phase": PHASE,
        "passed": passed,
        "total": total,
        "all_passed": all_passed,
        "checks": checks,
        "recommendation": recommendation,
    }
    print(json.dumps(report, indent=2))
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
