#!/usr/bin/env python3
"""PHASE DATA-1G — Build clean pre-match odds dataset and re-run ROI backtest."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.data_import.historical_prematch_odds_clean import (
    CLEAN_JOIN_SQL,
    RAW_JOIN_SQL,
    STRATEGIES_AD,
    audit_clean_table,
    build_prematch_clean_dataset,
    run_ad_backtest,
    summarize_ad_backtest,
)

ARTIFACTS = ROOT / "artifacts"
SUMMARY_PATH = ARTIFACTS / "data_1g_clean_backtest_summary.json"
EXPECTED_SOURCE_ROWS = 2063334


def _backup_summary() -> None:
    if SUMMARY_PATH.is_file():
        backup_dir = ARTIFACTS / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SUMMARY_PATH, backup_dir / f"data_1g_clean_backtest_summary_{SUMMARY_PATH.stat().st_mtime_ns}.json")


def _prematch_report_md(build: dict, audit: dict, comparison: dict) -> str:
    lines = [
        "# DATA-1G Clean Pre-Match Odds Report",
        "",
        "## Build summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Source rows scanned | {build['source_rows_scanned']} |",
        f"| Clean rows inserted | {build['rows_inserted']} |",
        f"| Skipped (duplicate rerun) | {build['rows_skipped_duplicate']} |",
        f"| Retention % | {build['retention_pct']} |",
        f"| Excluded: closing after kickoff | {build['excluded_closing_after_kickoff']} |",
        f"| Excluded: opening after kickoff | {build['excluded_opening_after_kickoff']} |",
        f"| Excluded: peak after kickoff | {build['excluded_peak_after_kickoff']} |",
        f"| Excluded: missing kickoff unix | {build['excluded_missing_kickoff_unix']} |",
        f"| Build batch | `{build['build_batch']}` |",
        "",
        "## Integrity audit",
        "",
        f"- Source `historical_csv_odds_imports` rows: **{audit['source_rows_unchanged']}** (unchanged)",
        f"- Clean table rows: **{audit['clean_rows']}**",
        f"- `closing_unix > kickoff_unix` violations: **{audit['closing_after_kickoff_violations']}**",
        "",
        "## Filter rules",
        "",
        "- `closing_unix` and `kickoff_unix` required",
        "- `closing_unix <= kickoff_unix` (strict)",
        "- `opening_unix <= kickoff_unix` when present",
        "- `peak_unix <= kickoff_unix` when present",
        "- Valid `closing_odds >= 1.0`",
        "- Original import rows **not modified or deleted**",
        "",
        "## Raw vs clean ROI (strategy A)",
        "",
        f"| Dataset | Bets | ROI % | Hit % |",
        f"|---------|------|-------|-------|",
    ]
    raw_a = comparison["raw"]["strategies"]["A_all_selections"]
    clean_a = comparison["clean"]["strategies"]["A_all_selections"]
    lines.append(f"| Raw (closing+opening fallback) | {raw_a['bets']} | {raw_a['roi_pct']} | {raw_a['hit_rate_pct']} |")
    lines.append(f"| Clean pre-match closing only | {clean_a['bets']} | {clean_a['roi_pct']} | {clean_a['hit_rate_pct']} |")
    lines.extend(
        [
            "",
            "## Strategy C/D impact (clean)",
            "",
        ]
    )
    for sk, label in (
        ("C_odds_gte_3_5", "C ≥3.5"),
        ("D_odds_3_5_to_12", "D 3.5–12"),
    ):
        raw_m = comparison["raw"]["strategies"][sk]
        clean_m = comparison["clean"]["strategies"][sk]
        lines.append(
            f"- **{label}** — raw ROI {raw_m['roi_pct']}% ({raw_m['bets']} bets) → "
            f"clean ROI {clean_m['roi_pct']}% ({clean_m['bets']} bets)"
        )
    lines.append("")
    return "\n".join(lines)


def _roi_backtest_report_md(comparison: dict) -> str:
    lines = [
        "# DATA-1G Clean ROI Backtest Report",
        "",
        "## Strategy comparison (raw vs clean)",
        "",
        "| Strategy | Raw bets | Raw ROI % | Clean bets | Clean ROI % | Δ ROI |",
        "|----------|----------|-----------|------------|-------------|-------|",
    ]
    for s in STRATEGIES_AD:
        raw = comparison["raw"]["strategies"][s]
        clean = comparison["clean"]["strategies"][s]
        delta = None
        if raw.get("roi_pct") is not None and clean.get("roi_pct") is not None:
            delta = round(clean["roi_pct"] - raw["roi_pct"], 2)
        lines.append(
            f"| {s} | {raw['bets']} | {raw['roi_pct']} | {clean['bets']} | {clean['roi_pct']} | {delta} |"
        )

    lines.extend(
        [
            "",
            "## Clean dataset — ROI by market (strategy A)",
            "",
            "| Market | Bets | ROI % | Hit % |",
            "|--------|------|-------|-------|",
        ]
    )
    for market, strategies in sorted(comparison["clean"]["by_market"].items()):
        m = strategies.get("A_all_selections", {})
        lines.append(f"| {market} | {m.get('bets', 0)} | {m.get('roi_pct')} | {m.get('hit_rate_pct')} |")

    lines.extend(
        [
            "",
            "## Clean dataset — ROI by odds band (strategy A)",
            "",
            "| Band | Bets | ROI % |",
            "|------|------|-------|",
        ]
    )
    for band, strategies in sorted(comparison["clean"]["by_odds_band"].items()):
        m = strategies.get("A_all_selections", {})
        lines.append(f"| {band} | {m.get('bets', 0)} | {m.get('roi_pct')} |")

    lines.extend(
        [
            "",
            "## Clean dataset — top leagues (strategy A)",
            "",
            "| League | Bets | ROI % |",
            "|--------|------|-------|",
        ]
    )
    for league, strategies in comparison["clean"].get("by_league_top20", {}).items():
        m = strategies.get("A_all_selections", {})
        lines.append(f"| {league} | {m.get('bets', 0)} | {m.get('roi_pct')} |")

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="DATA-1G clean pre-match odds")
    parser.add_argument("--dry-run", action="store_true", help="Build stats only, no insert")
    parser.add_argument("--skip-build", action="store_true", help="Backtest only using existing clean table")
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args()

    settings = get_settings()
    conn = connect(get_db_path(args.db or settings.sqlite_path))

    build_stats: dict = {
        "source_rows_scanned": EXPECTED_SOURCE_ROWS,
        "rows_inserted": 0,
        "rows_skipped_duplicate": 0,
        "retention_pct": 0,
        "excluded_closing_after_kickoff": 0,
        "excluded_opening_after_kickoff": 0,
        "excluded_peak_after_kickoff": 0,
        "excluded_missing_kickoff_unix": 0,
        "build_batch": "skipped",
    }
    if not args.skip_build:
        print("Building clean pre-match dataset...")
        stats = build_prematch_clean_dataset(conn, dry_run=args.dry_run)
        build_stats = stats.to_dict()
        print(
            f"Clean rows: {build_stats['rows_inserted']} | "
            f"Excluded closing>kickoff: {build_stats['excluded_closing_after_kickoff']}"
        )
    elif SUMMARY_PATH.is_file():
        build_stats = json.loads(SUMMARY_PATH.read_text(encoding="utf-8")).get("build", build_stats)

    if args.dry_run:
        print("Dry-run complete.")
        return 0

    audit = audit_clean_table(conn)
    if build_stats.get("rows_inserted", 0) == 0 and audit["clean_rows"] > 0:
        build_stats["rows_inserted"] = audit["clean_rows"]
        build_stats["retention_pct"] = round(100.0 * audit["clean_rows"] / EXPECTED_SOURCE_ROWS, 4)

    print("Running raw backtest (A-D)...")
    raw_state = run_ad_backtest(conn, join_sql=RAW_JOIN_SQL, label="raw", closing_only=False)
    print("Running clean backtest (A-D, closing only)...")
    clean_state = run_ad_backtest(conn, join_sql=CLEAN_JOIN_SQL, label="clean", closing_only=True)

    comparison = {
        "generated_at": summarize_ad_backtest(raw_state).get("label"),
        "build": build_stats,
        "audit": audit,
        "raw": summarize_ad_backtest(raw_state),
        "clean": summarize_ad_backtest(clean_state),
    }
    from datetime import datetime, timezone

    comparison["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    _backup_summary()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    (ROOT / "DATA_1G_CLEAN_PREMATCH_ODDS_REPORT.md").write_text(
        _prematch_report_md(build_stats, audit, comparison), encoding="utf-8"
    )
    (ROOT / "DATA_1G_CLEAN_ROI_BACKTEST_REPORT.md").write_text(_roi_backtest_report_md(comparison), encoding="utf-8")

    raw_c = comparison["raw"]["strategies"]["C_odds_gte_3_5"]
    clean_c = comparison["clean"]["strategies"]["C_odds_gte_3_5"]
    print("\n=== DATA-1G ===")
    print(f"Clean rows: {audit['clean_rows']} | Violations: {audit['closing_after_kickoff_violations']}")
    print(f"Strategy C raw ROI: {raw_c['roi_pct']}% -> clean ROI: {clean_c['roi_pct']}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
