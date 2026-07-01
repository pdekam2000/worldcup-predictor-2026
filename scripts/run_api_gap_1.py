#!/usr/bin/env python3
"""PHASE API-GAP-1 — Audit gaps, targeted harvest, coverage report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.api_gap_api_football_harvest import run_api_football_harvest
from worldcup_predictor.research.api_gap_audit import audit_markdown, run_api_gap_audit
from worldcup_predictor.research.api_gap_oddalerts_harvest import harvest_oddalerts_missing_markets
from worldcup_predictor.research.api_gap_sportmonks_harvest import run_sportmonks_harvest
from worldcup_predictor.research.api_gap_staging import ensure_api_gap_tables, harvest_log_summary

AUDIT_REPORT = ROOT / "API_GAP_1_AUDIT_REPORT.md"
SM_REPORT = ROOT / "API_GAP_1_SPORTMONKS_HARVEST_REPORT.md"
OA_REPORT = ROOT / "API_GAP_1_ODDALERTS_HARVEST_REPORT.md"
AF_REPORT = ROOT / "API_GAP_1_API_FOOTBALL_HARVEST_REPORT.md"
FINAL_REPORT = ROOT / "API_GAP_1_FINAL_COVERAGE_REPORT.md"
SUMMARY_JSON = ROOT / "artifacts" / "api_gap_1_summary.json"


def _harvest_md(title: str, payload: dict) -> str:
    lines = [f"# {title}", "", f"```json\n{json.dumps(payload, indent=2)}\n```", ""]
    return "\n".join(lines)


def _coverage_md(before: dict, after: dict, harvest: dict) -> str:
    b_odds = before["odds_gaps"]
    a_odds = after["odds_gaps"]
    b_xg = before["xg_gaps"]
    a_xg = after["xg_gaps"]
    lines = [
        "# API-GAP-1 — Final Coverage Report",
        "",
        "## Before vs after",
        "",
        "| Metric | Before | After | Δ |",
        "|--------|--------|-------|---|",
        f"| xg_snapshots rows | {b_xg['xg_snapshots_rows']} | {a_xg['xg_snapshots_rows']} | "
        f"{a_xg['xg_snapshots_rows'] - b_xg['xg_snapshots_rows']:+d} |",
        f"| prematch ft_draw rows | {b_odds['prematch_ft_draw_rows']} | {a_odds['prematch_ft_draw_rows']} | "
        f"{a_odds['prematch_ft_draw_rows'] - b_odds['prematch_ft_draw_rows']:+d} |",
        f"| oddalerts draw rows | {before['oddalerts_gaps'].get('draw_rows', 0)} | "
        f"{after['oddalerts_gaps'].get('draw_rows', 0)} | "
        f"{after['oddalerts_gaps'].get('draw_rows', 0) - before['oddalerts_gaps'].get('draw_rows', 0):+d} |",
        f"| ECSE missing ft_draw | {b_odds['missing_ft_draw_closing']:,} | {a_odds['missing_ft_draw_closing']:,} | "
        f"{a_odds['missing_ft_draw_closing'] - b_odds['missing_ft_draw_closing']:+,} |",
        "",
        "## ECSE tables (must be unchanged)",
        "",
    ]
    for t in before["ecse_table_fingerprints"]:
        bv = before["ecse_table_fingerprints"][t]
        av = after["ecse_table_fingerprints"].get(t, bv)
        flag = "OK" if bv == av else "CHANGED"
        lines.append(f"- `{t}`: {bv:,} → {av:,} **{flag}**")
    lines.extend(["", "## Harvest summary", "", f"```json\n{json.dumps(harvest, indent=2)}\n```"])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="API-GAP-1 targeted ECSE gap harvest")
    parser.add_argument("--audit-only", action="store_true", help="Gap audit only (default step 1)")
    parser.add_argument("--harvest", action="store_true", help="Run targeted harvest after audit")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-api-calls", type=int, default=30)
    parser.add_argument("--skip-sportmonks-api", action="store_true")
    parser.add_argument("--skip-oddalerts", action="store_true")
    parser.add_argument("--skip-api-football-live", action="store_true", default=True)
    args = parser.parse_args()

    if not args.harvest:
        args.audit_only = True

    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))
    ensure_api_gap_tables(conn)

    print("API-GAP-1 — gap audit (no API)\n")
    audit_before = run_api_gap_audit(conn)
    conn.close()

    AUDIT_REPORT.write_text(audit_markdown(audit_before), encoding="utf-8")
    print(f"Audit report: {AUDIT_REPORT}")

    harvest_results: dict = {}
    if args.audit_only and not args.harvest:
        payload = {"phase": "API-GAP-1", "audit": audit_before, "harvest": None}
        SUMMARY_JSON.parent.mkdir(parents=True, exist_ok=True)
        SUMMARY_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Summary: {SUMMARY_JSON}")
        print("\nAudit complete. Re-run with --harvest to fetch missing data.")
        return 0

    print("\nTargeted harvest (cache-first)...\n")

    sm = run_sportmonks_harvest(
        settings=settings,
        dry_run=args.dry_run,
        max_api_calls=args.max_api_calls,
        use_api=not args.skip_sportmonks_api,
    )
    harvest_results["sportmonks"] = sm
    SM_REPORT.write_text(_harvest_md("API-GAP-1 — Sportmonks Harvest Report", sm), encoding="utf-8")

    oa: dict = {}
    if not args.skip_oddalerts:
        oa = harvest_oddalerts_missing_markets(
            settings=settings,
            dry_run=args.dry_run,
            max_api_calls=args.max_api_calls,
        )
    harvest_results["oddalerts"] = oa
    OA_REPORT.write_text(_harvest_md("API-GAP-1 — OddAlerts Harvest Report", oa), encoding="utf-8")

    af = run_api_football_harvest(
        settings=settings,
        dry_run=args.dry_run,
        max_api_calls=args.max_api_calls,
        use_live_api=not args.skip_api_football_live,
    )
    harvest_results["api_football"] = af
    AF_REPORT.write_text(_harvest_md("API-GAP-1 — API-Football Harvest Report", af), encoding="utf-8")

    conn = connect(get_db_path(settings.sqlite_path))
    audit_after = run_api_gap_audit(conn)
    log_summary = harvest_log_summary(conn)
    predictions_count = conn.execute("SELECT COUNT(1) FROM predictions").fetchone()[0]
    conn.close()

    FINAL_REPORT.write_text(_coverage_md(audit_before, audit_after, harvest_results), encoding="utf-8")
    payload = {
        "phase": "API-GAP-1",
        "dry_run": args.dry_run,
        "audit_before": audit_before,
        "audit_after": audit_after,
        "harvest": harvest_results,
        "harvest_log": log_summary,
        "predictions_count_unchanged_check": predictions_count,
    }
    SUMMARY_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"\nFinal coverage: {FINAL_REPORT}")
    print(f"Summary: {SUMMARY_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
