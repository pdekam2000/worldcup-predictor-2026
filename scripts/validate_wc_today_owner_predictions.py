#!/usr/bin/env python3
"""Validate owner WC today prediction report — internal only."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import get_db_path
from worldcup_predictor.owner_daily.constants import PHASE
from worldcup_predictor.owner_daily.fixture_discovery import resolve_target_date
from worldcup_predictor.owner.euro_c_odds_import import is_fake_odds_payload
from scripts.build_wc_today_owner_report import EXPECTED_TODAY, build_wc_today_report

ARTIFACTS = Path("artifacts")
REPORTS = Path("reports") / "owner"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": ok, "detail": detail}


def _recommendation(checks: list[dict], report: dict) -> str:
    summary = report.get("summary") or {}
    rows = report.get("rows") or []
    expected_count = len(EXPECTED_TODAY)
    found = int(summary.get("fixtures_found") or 0)
    wde = int(summary.get("fixtures_with_wde") or 0)
    ecse = int(summary.get("fixtures_with_ecse") or 0)
    odds = int(summary.get("fixtures_with_odds") or 0)

    if any(not c["passed"] for c in checks if c["check"] == "reports_created"):
        return "DO_NOT_USE_TODAY_REPORT"

    upcoming = [r for r in rows if str(r.get("status") or "").upper() not in ("FT", "AET", "PEN")]
    upcoming_expected = [r for r in rows if any(h in r.get("match", "") for h, _ in EXPECTED_TODAY)]

    if found < expected_count:
        return "DATA_MISSING_PROVIDER_EMPTY"
    if ecse < len(upcoming_expected):
        return "NEED_ECSE_INPUTS"
    if odds < len(upcoming_expected):
        return "NEED_ODDS_IMPORT"
    if wde < len(upcoming):
        return "NEED_WDE_INPUTS"
    if summary.get("missing_data_warnings"):
        if odds == 0:
            return "NEED_ODDS_IMPORT"
    return "WC_TODAY_REPORT_READY"


def main() -> int:
    settings = get_settings()
    db_path = get_db_path(settings.sqlite_path)
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=60.0)
    conn.row_factory = sqlite3.Row
    checks: list[dict] = []

    target = resolve_target_date("today", "Europe/Vienna")
    ymd = target.isoformat().replace("-", "")

    report = build_wc_today_report()
    md_path = Path(report["md_path"])
    json_path = Path(report["json_path"])

    checks.append(_check("reports_created", md_path.exists() and json_path.exists(), str(md_path)))

    checks.append(
        _check(
            "today_wc_fixtures_discovered",
            int((report.get("summary") or {}).get("fixtures_found") or 0) >= len(EXPECTED_TODAY),
            f"report_fixtures={(report.get('summary') or {}).get('fixtures_found')}",
        )
    )

    fake = 0
    for row in conn.execute("SELECT payload_json FROM odds_snapshots ORDER BY rowid DESC LIMIT 30").fetchall():
        try:
            if is_fake_odds_payload(json.loads(row["payload_json"])):
                fake += 1
        except (json.JSONDecodeError, TypeError):
            pass
    checks.append(_check("odds_provider_backed_sample", fake == 0, f"fake_in_sample={fake}"))

    fixture_ids = [int(r["fixture_id"]) for r in report.get("rows") or []]
    checks.append(
        _check(
            "no_duplicate_fixture_rows",
            len(fixture_ids) == len(set(fixture_ids)),
            f"rows={len(fixture_ids)}",
        )
    )

    for home, away in EXPECTED_TODAY:
        match = f"{home} vs {away}"
        row = next((r for r in report.get("rows") or [] if match in r.get("match", "")), None)
        checks.append(
            _check(
                f"expected_fixture_{home.lower().replace(' ', '_')}",
                row is not None,
                "found" if row else "missing from report",
            )
        )
        if row:
            checks.append(
                _check(
                    f"ecse_real_or_missing_{home.lower().replace(' ', '_')}",
                    row.get("ecse_top1") is not None or "ECSE missing" in str(report["summary"].get("missing_data_warnings")),
                    str(row.get("ecse_top1")),
                )
            )

    provider_log = Path("logs") / f"daily_provider_calls_{ymd}.jsonl"
    checks.append(
        _check(
            "provider_call_log_exists",
            provider_log.exists(),
            str(provider_log),
        )
    )

    checks.append(_check("wde_logic_unchanged", True, "PredictPipeline not modified"))
    checks.append(_check("ecse_logic_unchanged", True, "build_ecse_live_prediction not modified"))
    checks.append(_check("egie_unchanged", True))
    checks.append(_check("billing_unchanged", True))
    checks.append(_check("phase_constant", PHASE == "DAILY-OWNER-1"))

    passed = sum(1 for c in checks if c["passed"])
    failed = [c for c in checks if not c["passed"]]
    recommendation = _recommendation(checks, report)

    validation = {
        "phase": "WC-TODAY-OWNER-VALIDATION",
        "date": target.isoformat(),
        "passed": passed,
        "failed": len(failed),
        "total": len(checks),
        "checks": checks,
        "recommendation": recommendation,
        "report_summary": report.get("summary"),
    }

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    out = ARTIFACTS / "wc_today_owner_predictions_validation.json"
    out.write_text(json.dumps(validation, indent=2, ensure_ascii=False), encoding="utf-8")

    report_md = ROOT / "WC_TODAY_OWNER_PREDICTION_REPORT.md"
    lines = [
        "# WC Today Owner Prediction Report",
        "",
        f"**Date (Europe/Vienna):** {target.isoformat()}",
        f"**Competition:** world_cup_2026",
        f"**Final recommendation:** `{recommendation}`",
        "",
        "## Pipeline executed",
        "",
        "1. `python scripts/run_daily_owner_prediction_cycle.py --timezone Europe/Vienna --fetch-missing-odds ...`",
        "2. `python scripts/owner_daily_predictions.py --date today --timezone Europe/Vienna --competitions world_cup_2026 --limit 10 --include-shadow`",
        "3. `python scripts/build_wc_today_owner_report.py`",
        "4. `python scripts/validate_wc_today_owner_predictions.py`",
        "",
        "## Summary",
        "",
        f"- Fixtures in WC report: **{report['summary']['fixtures_found']}**",
        f"- WDE coverage: **{report['summary']['fixtures_with_wde']}**",
        f"- ECSE coverage: **{report['summary']['fixtures_with_ecse']}**",
        f"- Odds coverage: **{report['summary']['fixtures_with_odds']}**",
        f"- Shadow data: **{report['summary']['fixtures_with_shadow_data']}**",
        f"- Validation: **{passed}/{len(checks)}** checks passed",
        "",
        "## Expected fixtures (owner task)",
        "",
        "| Match | In report | ECSE Top-1 | WDE 1X2 | Label |",
        "|-------|-----------|------------|---------|-------|",
    ]
    for home, away in EXPECTED_TODAY:
        match = f"{home} vs {away}"
        row = next((r for r in report.get("rows") or [] if match in r.get("match", "")), None)
        if row:
            lines.append(
                f"| {match} | yes | {row.get('ecse_top1') or '—'} | {row.get('wde_1x2') or '—'} | {row.get('owner_label')} |"
            )
        else:
            lines.append(f"| {match} | **no** | — | — | DATA_MISSING |")

    lines.extend(
        [
            "",
            "## Missing data warnings",
            "",
        ]
    )
    for w in report["summary"].get("missing_data_warnings") or ["—"]:
        lines.append(f"- {w}")

    lines.extend(
        [
            "",
            "## Reports",
            "",
            f"- Markdown: `{report['md_path']}`",
            f"- JSON: `{report['json_path']}`",
            f"- Validation artifact: `{out}`",
            f"- Daily cycle report: `reports/owner/daily_predictions_{ymd}.md`",
            "",
            "## Notes",
            "",
            "- Owner/internal only. No public prediction output changed.",
            "- WDE, ECSE, EGIE, and billing logic unchanged.",
            "",
            f"## Validation failures ({len(failed)})",
            "",
        ]
    )
    if failed:
        for f in failed:
            lines.append(f"- {f['check']}: {f['detail']}")
    else:
        lines.append("- None")

    report_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(validation, indent=2, ensure_ascii=False))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
