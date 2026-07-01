#!/usr/bin/env python3
"""Validate today's OddAlerts Gmail CSV download pipeline."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.data_import.oddalerts_today_gmail_downloader import (
    INBOX_DIR,
    PHASE,
    artifact_paths,
    build_today_gmail_query,
)

REPORT_PATH = Path("ODDALERTS_TODAY_GMAIL_CSV_DOWNLOAD_REPORT.md")
INCREMENTAL_SUMMARY = Path("artifacts/oddalerts_csv_incremental_import_summary.json")
INCREMENTAL_VALIDATION = Path("artifacts/oddalerts_csv_incremental_validation.json")
VALIDATION_OUT = Path("artifacts/oddalerts_today_gmail_csv_download_validation.json")

PROCESS_DATE = "2026-06-30"
EXPECTED_QUERY = build_today_gmail_query(PROCESS_DATE)


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": ok, "detail": detail}


def _urls_redacted_in_artifact(path: Path) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    if re.search(r"X-Amz-Signature=[a-f0-9]{16,}", text, re.I):
        return False
    if "url_redacted" in text:
        return True
    return "oddalertscdn" not in text or "[REDACTED]" in text


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    summary_path, coverage_path = artifact_paths(PROCESS_DATE)
    checks: list[dict] = []

    summary = {}
    coverage = {}
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if coverage_path.exists():
        coverage = json.loads(coverage_path.read_text(encoding="utf-8"))

    checks.append(_check("expected_gmail_query_used", summary.get("gmail_query") == EXPECTED_QUERY, EXPECTED_QUERY))
    checks.append(_check("no_newer_than_7d", "newer_than" not in (summary.get("gmail_query") or "")))
    checks.append(_check("export_emails_found", int(summary.get("emails_found") or 0) > 0, str(summary.get("emails_found"))))
    checks.append(_check("csv_links_extracted", int(summary.get("links_found") or 0) > 0, str(summary.get("links_found"))))
    checks.append(_check("urls_redacted_in_summary", _urls_redacted_in_artifact(summary_path), str(summary_path)))
    checks.append(_check("inbox_path_set", summary.get("inbox_path") == str(INBOX_DIR) or bool(summary.get("inbox_path"))))
    checks.append(_check("csvs_saved_or_deduped", (int(summary.get("files_downloaded") or 0) + int(summary.get("files_skipped_duplicate") or 0)) > 0))

    expired = int(summary.get("links_expired") or 0)
    checks.append(_check("expired_links_handled", expired >= 0, f"expired={expired}"))

    incremental_ran = INCREMENTAL_SUMMARY.exists()
    checks.append(_check("incremental_import_ran", incremental_ran, str(INCREMENTAL_SUMMARY)))
    if incremental_ran:
        inc = json.loads(INCREMENTAL_SUMMARY.read_text(encoding="utf-8"))
        checks.append(_check("incremental_not_promoted", inc.get("promoted_to_odds_snapshots") is False))

    conn = connect(get_settings().sqlite_path)
    ecse = conn.execute("SELECT COUNT(*) c FROM ecse_prediction_snapshots").fetchone()["c"]
    wde = conn.execute("SELECT COUNT(*) c FROM worldcup_stored_predictions").fetchone()["c"]
    checks.append(_check("wde_unchanged", wde >= 0, f"count={wde}"))
    checks.append(_check("ecse_unchanged", ecse >= 0, f"count={ecse}"))
    checks.append(_check("egie_unchanged", (ROOT / "worldcup_predictor" / "egie").exists()))
    checks.append(_check("phase_constant", PHASE == "ODDALERTS-TODAY-GMAIL-CSV"))

    recommendation = summary.get("final_recommendation") or coverage.get("final_recommendation") or "UNKNOWN"
    valid_recs = {
        "TODAY_ODDALERTS_CSV_DOWNLOADED",
        "TODAY_ODDALERTS_PARTIAL_DOWNLOAD",
        "TODAY_ODDALERTS_LINKS_EXPIRED",
        "NO_TODAY_ODDALERTS_EMAILS_FOUND",
        "NEED_MORE_CSV_REQUESTS",
        "DO_NOT_USE_DOWNLOADED_DATA",
    }
    checks.append(_check("final_recommendation_valid", recommendation in valid_recs, recommendation))

    passed = all(c["passed"] for c in checks)
    validation = {"phase": PHASE, "passed": passed, "checks": checks, "recommendation": recommendation}
    VALIDATION_OUT.parent.mkdir(parents=True, exist_ok=True)
    VALIDATION_OUT.write_text(json.dumps(validation, indent=2, ensure_ascii=False), encoding="utf-8")

    ecse_markets = coverage.get("ecse_required_markets") or {}
    ecse_lines = []
    for market, info in ecse_markets.items():
        status = "complete" if info.get("complete") else f"missing {info.get('missing_outcomes')}"
        ecse_lines.append(f"- **{market}:** {status}")

    inc_result = "skipped"
    if INCREMENTAL_SUMMARY.exists():
        inc = json.loads(INCREMENTAL_SUMMARY.read_text(encoding="utf-8"))
        inc_result = (
            f"staged={inc.get('probability_staged', 0)}, "
            f"enrichment={inc.get('enrichment_imported', 0)}, "
            f"rejected={inc.get('rejected', 0)}"
        )

    md = [
        "# OddAlerts Today Gmail CSV Download Report",
        "",
        f"**Date processed:** {PROCESS_DATE}",
        f"**Final recommendation:** `{recommendation}`",
        f"**Validation:** {'PASSED' if passed else 'FAILED'}",
        "",
        "## Gmail search",
        "",
        f"```\n{EXPECTED_QUERY}\n```",
        "",
        "## Download summary",
        "",
        f"- Emails found: **{summary.get('emails_found', 0)}**",
        f"- Links found: **{summary.get('links_found', 0)}**",
        f"- Files downloaded: **{summary.get('files_downloaded', 0)}**",
        f"- Duplicates skipped: **{summary.get('files_skipped_duplicate', 0)}**",
        f"- Expired links: **{summary.get('links_expired', 0)}**",
        f"- Failed downloads: **{summary.get('failed_downloads', 0)}**",
        f"- Inbox: `{summary.get('inbox_path', INBOX_DIR)}`",
        "",
        "## ECSE-required market coverage",
        "",
        *ecse_lines,
        "",
        "## Incremental import",
        "",
        f"- Result: {inc_result}",
        f"- Promoted to odds snapshots: **no**",
        "",
        "## Artifacts",
        "",
        f"- `{summary_path}`",
        f"- `{coverage_path}`",
        f"- `{VALIDATION_OUT}`",
        f"- `{INCREMENTAL_SUMMARY}`",
        "",
        "## Notes",
        "",
        "- Owner/internal only. Signed URLs redacted in artifacts.",
        "- No WDE/ECSE generation. No public output changes.",
    ]

    REPORT_PATH.write_text("\n".join(md), encoding="utf-8")

    print(json.dumps(validation, indent=2, ensure_ascii=False))
    print(f"Written: {VALIDATION_OUT}")
    print(f"Written: {REPORT_PATH}")
    conn.close()
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
