#!/usr/bin/env python3
"""PHASE DATA-1D — Build historical result labels from OddAlerts CSV data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.data_import.historical_fixture_results import (
    backup_database_data1d,
    build_and_insert_historical_results,
    inspect_csv_result_fields,
    query_backtest_readiness,
)

ARTIFACTS = ROOT / "artifacts"
BACKUP_DIR = ROOT / "data" / "backups"


def _labels_report_md(
    stats: dict,
    field_audit: dict,
    backup_path: str | None,
    ambiguous_count: int,
    no_result_count: int,
) -> str:
    return "\n".join(
        [
            "# Historical Results Labels Report (DATA-1D)",
            "",
            f"**Backup:** `{backup_path or 'none (dry-run)'}`",
            "",
            "## CSV result field audit",
            "",
            f"- **Fields present:** {field_audit.get('present', False)}",
            f"- **Required columns:** Status, Home Goals, Away Goals",
            f"- **Optional columns used:** Corners, HT Score, Outcome",
            "",
            "## Schema reuse",
            "",
            "- Production `fixture_results` — not modified (API-Football fixtures only).",
            "- Staging `historical_fixture_results` — one row per `registry_fixture_id` + source.",
            "",
            "## Build results",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Registry fixtures | {stats['registry_total']} |",
            f"| Odds rows scanned | {stats['odds_rows_scanned']} |",
            f"| Settled fixtures with labels | {stats['settled_candidate_fixtures']} |",
            f"| Result rows inserted | {stats['results_inserted']} |",
            f"| Skipped (duplicate rerun) | {stats['results_skipped_duplicate']} |",
            f"| Skipped (unsettled) | {stats['results_skipped_unsettled']} |",
            f"| Skipped (no score) | {stats['results_skipped_no_score']} |",
            f"| Skipped (ambiguous tie) | {stats['results_skipped_ambiguous']} |",
            f"| Ambiguous score variants logged | {ambiguous_count} |",
            f"| No-result fixtures logged | {no_result_count} |",
            "",
            "## Settled statuses used",
            "",
            "`FT`, `FT_PEN`, `AET`, `AWARDED`",
            "",
            "## Derived labels",
            "",
            "- `result_1x2` — home / draw / away",
            "- `btts_actual` — both teams scored",
            "- `over_15_actual`, `over_25_actual`, `over_35_actual`",
            "- `corners_total`, `corners_over_85/95/105_actual` (when Corners in CSV)",
            "",
        ]
    )


def _readiness_report_md(readiness: dict) -> str:
    lines = [
        "# DATA-1D Backtest Readiness Report",
        "",
        f"**Registry fixtures:** {readiness['registry_fixtures']}",
        f"**Fixtures with result labels:** {readiness['fixtures_with_results']}",
        f"**Registry label coverage:** {readiness['registry_coverage_pct']}%",
        f"**Odds rows joinable to results:** {readiness['odds_rows_joinable_to_results']}",
        f"**Odds join coverage:** {readiness['odds_join_coverage_pct']}%",
        "",
        "## Result 1X2 distribution",
        "",
    ]
    for row in readiness.get("result_1x2_distribution", []):
        lines.append(f"- **{row.get('result_1x2')}:** {row.get('c', 0)}")

    lines.extend(
        [
            "",
            "## Market join coverage (odds + results)",
            "",
            "| Market | Odds rows | Fixtures with results |",
            "|--------|-----------|------------------------|",
        ]
    )
    for row in readiness.get("by_market", []):
        lines.append(
            f"| {row.get('market', '-')} | {row.get('odds_rows', 0)} | {row.get('fixtures_with_results', 0)} |"
        )
    lines.extend(
        [
            "",
            "## ECSE/EVME readiness",
            "",
            "- Historical odds can join: `historical_csv_odds_imports` → `historical_fixture_registry` → `historical_fixture_results`",
            "- No API calls required for labeled backtests on imported CSV coverage.",
            "- Production `fixtures` / `predictions` unchanged.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="DATA-1D historical results labels")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-backup", action="store_true")
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args()

    settings = get_settings()
    db_path = get_db_path(args.db or settings.sqlite_path)
    conn = connect(db_path)

    field_audit = inspect_csv_result_fields(conn)
    if not field_audit.get("present"):
        (ROOT / "HISTORICAL_RESULTS_LABELS_REPORT.md").write_text(
            f"# Historical Results Labels Report (DATA-1D)\n\n"
            f"**Stopped:** CSV result fields missing — {field_audit}\n\n"
            f"No labels created. External API would be required.\n",
            encoding="utf-8",
        )
        print(f"CSV result fields missing: {field_audit}")
        return 1

    backup_path = None
    if not args.dry_run and not args.no_backup:
        backup_path = backup_database_data1d(db_path, BACKUP_DIR)
        print(f"DB backup: {backup_path}")

    stats_obj, ambiguous, no_result, readiness = build_and_insert_historical_results(
        conn, dry_run=args.dry_run
    )
    stats = stats_obj.to_dict()

    if not args.dry_run:
        readiness = query_backtest_readiness(conn)

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "data_1d_results_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    (ARTIFACTS / "data_1d_field_audit.json").write_text(json.dumps(field_audit, indent=2), encoding="utf-8")
    (ARTIFACTS / "data_1d_ambiguous_results.json").write_text(
        json.dumps(ambiguous[:5000], indent=2), encoding="utf-8"
    )
    (ARTIFACTS / "data_1d_no_result_fixtures.json").write_text(
        json.dumps(no_result[:5000], indent=2), encoding="utf-8"
    )
    (ARTIFACTS / "data_1d_backtest_readiness.json").write_text(
        json.dumps(readiness, indent=2), encoding="utf-8"
    )

    (ROOT / "HISTORICAL_RESULTS_LABELS_REPORT.md").write_text(
        _labels_report_md(stats, field_audit, str(backup_path) if backup_path else None, len(ambiguous), len(no_result)),
        encoding="utf-8",
    )
    (ROOT / "DATA_1D_BACKTEST_READINESS_REPORT.md").write_text(_readiness_report_md(readiness), encoding="utf-8")

    mode = "DRY-RUN" if args.dry_run else "BUILD"
    print(f"\n=== DATA-1D {mode} ===")
    print(f"Labels built: {stats['settled_candidate_fixtures']} | Inserted: {stats['results_inserted']}")
    print(f"No-result fixtures: {len(no_result)} | Ambiguous logged: {len(ambiguous)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
