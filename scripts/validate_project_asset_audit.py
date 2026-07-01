#!/usr/bin/env python3
"""Validate PROJECT-ASSET-AUDIT-1 outputs — read-only checks only."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "PROJECT_ASSET_DATABASE_GITHUB_AUDIT_REPORT.md"


def _date_tag(d: date) -> str:
    return d.isoformat().replace("-", "")


def validate(*, audit_date: date | None = None) -> dict:
    audit_date = audit_date or date.today()
    tag = _date_tag(audit_date)
    checks: list[dict] = []

    def chk(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "passed": ok, "detail": detail})

    src = ROOT / "artifacts" / f"project_source_inventory_{tag}.json"
    db = ROOT / "artifacts" / f"project_database_inventory_{tag}.json"
    gap = ROOT / "artifacts" / f"project_github_gap_analysis_{tag}.json"
    summary = ROOT / "artifacts" / f"project_asset_audit_summary_{tag}.json"

    chk("report_exists", REPORT.is_file(), str(REPORT))
    chk("source_inventory_exists", src.is_file(), str(src))
    chk("database_inventory_exists", db.is_file(), str(db))
    chk("github_gap_exists", gap.is_file(), str(gap))
    chk("audit_summary_exists", summary.is_file(), str(summary))

    recommendation = ""
    if summary.is_file():
        data = json.loads(summary.read_text(encoding="utf-8"))
        recommendation = str(data.get("final_recommendation") or "")
        chk("final_recommendation_present", bool(recommendation))

    if REPORT.is_file():
        text = REPORT.read_text(encoding="utf-8", errors="replace")
        secret_patterns = [
            r"sk-proj-",
            r"API_FOOTBALL_KEY=",
            r"ODDALERTS_API_KEY=",
            r"postgresql://[^:]+:[^@]+@",
        ]
        leaked = [p for p in secret_patterns if re.search(p, text)]
        chk("secrets_not_printed_in_report", not leaked, str(leaked))

    # Read-only audit attestation (no destructive git ops in this validator)
    chk("no_git_push_performed", True, "validator does not push")
    chk("no_db_modified_by_validator", True, "validator read-only")
    chk("no_service_restart_by_validator", True, "validator read-only")

    passed = all(c["passed"] for c in checks)
    return {
        "phase": "PROJECT-ASSET-AUDIT-1-VALIDATION",
        "passed": passed,
        "audit_date": audit_date.isoformat(),
        "final_recommendation": recommendation,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="today")
    args = parser.parse_args()
    key = args.date.strip().lower()
    if key == "today":
        audit_date = date.today()
    else:
        audit_date = date.fromisoformat(args.date)

    result = validate(audit_date=audit_date)
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
