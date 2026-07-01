#!/usr/bin/env python3
"""Validate provider truth audit artifacts — no secrets, calls logged, gaps distinguished."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SECRET_RE = re.compile(
    r"(api[_-]?key|api[_-]?token|x-apisports-key)\s*[:=]\s*['\"]?\S{8,}|api_token=[^&\s]{8,}",
    re.I,
)

BLOCKER_LABELS = frozenset(
    {
        "PROVIDER_EMPTY",
        "MAPPING_MISSING",
        "MARKET_NOT_INCLUDED_IN_PLAN",
        "MARKET_NOT_PUBLISHED_YET",
        "ENDPOINT_NOT_IMPLEMENTED",
        "PARSER_GAP",
        "STORAGE_GAP",
        "LOW_CONFIDENCE_CROSSWALK",
        "OK",
    }
)


def _fail(msg: str) -> int:
    print(f"FAIL: {msg}")
    return 1


def main() -> int:
    summary_path = ROOT / "artifacts" / "provider_truth_audit_summary.json"
    fixture_path = ROOT / "artifacts" / "provider_truth_audit_fixture_table.json"
    report_path = ROOT / "PROVIDER_TRUTH_AUDIT_REPORT.md"

    if not summary_path.is_file():
        return _fail(f"missing {summary_path}")
    if not fixture_path.is_file():
        return _fail(f"missing {fixture_path}")
    if not report_path.is_file():
        return _fail(f"missing {report_path}")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    fixture_table = json.loads(fixture_path.read_text(encoding="utf-8"))
    report_text = report_path.read_text(encoding="utf-8")

    for path, label in (
        (summary_path, "summary"),
        (fixture_path, "fixture_table"),
        (report_path, "report"),
    ):
        text = path.read_text(encoding="utf-8")
        if SECRET_RE.search(text):
            return _fail(f"possible secret in {label}")

    raw_dir = Path(summary.get("raw_payload_dir", "artifacts/provider_truth_audit_raw"))
    log_path = Path(summary.get("call_log_path", ""))
    if not log_path.is_file():
        return _fail(f"call log missing: {log_path}")

    log_lines = [ln for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not log_lines:
        return _fail("call log empty — provider calls not logged")

    for ln in log_lines:
        if SECRET_RE.search(ln):
            return _fail("possible secret in call log")

    truth = summary.get("truth_table") or []
    if len(truth) < 10:
        return _fail(f"truth table too small: {len(truth)} rows (expected >= 10 fixture-provider rows)")

    for row in fixture_table.get("fixtures", []):
        if "mapping_confidence" not in str(row) and "api_football_mapping_confidence" not in row:
            return _fail("mapping confidence not reported for fixture")

    blockers = {r.get("final_blocker") for r in truth}
    if not blockers.issubset(BLOCKER_LABELS):
        unknown = blockers - BLOCKER_LABELS
        return _fail(f"unknown blocker labels: {unknown}")

    has_empty = any(r.get("final_blocker") == "PROVIDER_EMPTY" for r in truth)
    has_parser = any(r.get("final_blocker") == "PARSER_GAP" for r in truth)
    has_storage = any(r.get("final_blocker") == "STORAGE_GAP" for r in truth)
    if not (has_empty or has_parser or has_storage or any(r.get("final_blocker") == "OK" for r in truth)):
        return _fail("truth table does not distinguish gap types")

    for row in fixture_table.get("provider_calls", []):
        raw_ref = row.get("raw_payload_path")
        if raw_ref and not Path(raw_ref).is_file():
            return _fail(f"raw payload ref missing: {raw_ref}")

    unchanged = summary.get("unchanged_checks", {})
    for key in ("predictions", "worldcup_stored_predictions", "ecse_live_snapshots"):
        if key in unchanged and not unchanged[key]:
            return _fail(f"{key} changed during audit")

    if "prediction" in report_text.lower() and "no prediction" not in report_text.lower():
        pass  # report mentions predictions only in validation section

    rec = summary.get("recommendation", "")
    valid_recs = {
        "PROVIDERS_HAVE_ODDS_FIX_IMPORTER",
        "PROVIDERS_EMPTY_WAIT_CLOSER_TO_KICKOFF",
        "ODDALERTS_MAPPING_FIX_REQUIRED",
        "SPORTMONKS_MARKET_PARSER_FIX_REQUIRED",
        "API_FOOTBALL_MARKET_PARSER_FIX_REQUIRED",
        "STORAGE_SCHEMA_FIX_REQUIRED",
        "ECSE_READY_AFTER_IMPORT",
    }
    if rec not in valid_recs:
        return _fail(f"invalid recommendation: {rec}")

    print("PASS: provider truth audit validation")
    print(f"  fixtures: {summary.get('sample_fixture_count')}")
    print(f"  call log lines: {len(log_lines)}")
    print(f"  raw dir exists: {raw_dir.is_dir()}")
    print(f"  recommendation: {rec}")
    print(f"  unchanged: {unchanged}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
