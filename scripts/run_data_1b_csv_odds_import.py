#!/usr/bin/env python3
"""PHASE DATA-1B — Import Cursor-downloaded OddAlerts CSV odds into SQLite."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.data_import.historical_csv_odds import (
    backup_database,
    catalog_all,
    import_csv_odds,
    is_schema_clear,
)

ARTIFACTS = ROOT / "artifacts"
BACKUP_DIR = ROOT / "data" / "backups"


def _write_json(name: str, payload: object) -> Path:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS / name
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _catalog_report_md(catalog: list[dict], schema_ok: bool, schema_reason: str) -> str:
    lines = [
        "# CSV Odds Catalog Report (DATA-1B)",
        "",
        f"**Files discovered:** {len(catalog)}",
        f"**Import-eligible (OddAlerts schema):** {sum(1 for e in catalog if e.get('row_count', 0) > 0 and set(e.get('columns') or []) >= {'ID', 'Kickoff', 'Home Team', 'Away Team'})}",
        f"**Schema clear:** {schema_ok} ({schema_reason})",
        "",
        "## Summary",
        "",
        "| File | Rows | Size (KB) | Market | Bookmaker | Date range | SHA256 (prefix) |",
        "|------|------|-----------|--------|-----------|------------|-----------------|",
    ]
    for e in sorted(catalog, key=lambda x: -x["row_count"]):
        bm = e.get("bookmaker")
        if isinstance(bm, list):
            bm = ", ".join(bm[:2])
        dr = ""
        if e.get("date_min"):
            dr = f"{e['date_min']} .. {e['date_max']}"
        lines.append(
            f"| `{e['filename']}` | {e['row_count']} | {e['size_bytes']//1024} | "
            f"{e['market_type']} | {bm or '-'} | {dr or '-'} | `{e['sha256'][:12]}…` |"
        )
    if catalog:
        cols = catalog[0].get("columns") or []
        lines.extend(["", "## Detected columns", "", "```", ", ".join(cols), "```"])
    return "\n".join(lines) + "\n"


def _import_report_md(stats: dict, backup_path: str | None) -> str:
    return "\n".join(
        [
            "# Historical CSV Odds Import Report (DATA-1B)",
            "",
            f"**Backup:** `{backup_path or 'none (dry-run)'}`",
            "",
            "## Results",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Files discovered | {stats['files_discovered']} |",
            f"| Files skipped (dup sha256) | {stats['files_skipped_dup_sha']} |",
            f"| Files skipped (empty) | {stats['files_skipped_empty']} |",
            f"| Rows parsed | {stats['rows_parsed']} |",
            f"| Rows inserted | {stats['rows_inserted']} |",
            f"| Rows skipped (duplicate) | {stats['rows_skipped_duplicate']} |",
            f"| Rows skipped (invalid) | {stats['rows_skipped_invalid']} |",
            f"| Rows matched to fixtures | {stats['rows_matched']} |",
            f"| Rows unmatched | {stats['rows_unmatched']} |",
            "",
            "## Rows by market",
            "",
        ]
        + [f"- **{k}:** {v}" for k, v in sorted(stats.get("markets", {}).items(), key=lambda x: -x[1])]
        + ["", "## Errors", ""]
        + ([f"- {e}" for e in stats.get("errors", [])] or ["- none"])
        + [""]
    )


def _matching_report_md(unmatched: list[dict], stats: dict) -> str:
    lines = [
        "# CSV to Fixture Matching Report (DATA-1B)",
        "",
        f"**Matched rows:** {stats['rows_matched']}",
        f"**Unmatched rows:** {stats['rows_unmatched']}",
        "",
        "## Matching strategy",
        "",
        "1. `kickoff[:10] + normalized home_team + normalized away_team` → `fixtures` table",
        "2. OddAlerts `ID` column stored as `oddalerts_row_id` (selection id, not API fixture id)",
        "",
        "## Unmatched sample (first 50)",
        "",
        "| Source file | Kickoff | Home | Away | Market | Selection |",
        "|-------------|---------|------|------|--------|-----------|",
    ]
    for u in unmatched[:50]:
        lines.append(
            f"| `{Path(u['source_file']).name}` | {u['kickoff'][:10]} | "
            f"{u['home_team'][:20]} | {u['away_team'][:20]} | {u['market']} | {u['selection']} |"
        )
    if len(unmatched) > 50:
        lines.append(f"\n*…and {len(unmatched) - 50} more unmatched rows.*")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="DATA-1B CSV odds import")
    parser.add_argument("--catalog-only", action="store_true", help="Build catalog only, no import")
    parser.add_argument("--dry-run", action="store_true", help="Parse and match without inserting")
    parser.add_argument("--no-backup", action="store_true", help="Skip DB backup (not recommended)")
    parser.add_argument("--db", type=Path, default=None, help="SQLite path override")
    args = parser.parse_args()

    settings = get_settings()
    db_path = get_db_path(args.db or settings.sqlite_path)
    conn = connect(db_path)

    catalog = catalog_all(ROOT)
    schema_ok, schema_reason = is_schema_clear(catalog)
    _write_json("data_1b_csv_catalog.json", catalog)

    (ROOT / "CSV_ODDS_CATALOG_REPORT.md").write_text(
        _catalog_report_md(catalog, schema_ok, schema_reason), encoding="utf-8"
    )

    if not schema_ok:
        review = ROOT / "CSV_ODDS_SCHEMA_REVIEW_REPORT.md"
        review.write_text(
            f"# CSV Odds Schema Review\n\nSchema unclear: **{schema_reason}**\n\nImport stopped.\n",
            encoding="utf-8",
        )
        print(f"Schema unclear ({schema_reason}). See CSV_ODDS_SCHEMA_REVIEW_REPORT.md")
        return 1

    if args.catalog_only:
        print(f"Catalog only: {len(catalog)} files. Schema OK.")
        return 0

    backup_path = None
    if not args.dry_run and not args.no_backup:
        backup_path = backup_database(db_path, BACKUP_DIR)
        print(f"DB backup: {backup_path}")

    catalog, stats, unmatched = import_csv_odds(conn, ROOT, dry_run=args.dry_run)
    stats_dict = stats.to_dict()
    _write_json("data_1b_import_stats.json", stats_dict)
    _write_json("data_1b_unmatched_rows.json", unmatched[:5000])

    (ROOT / "HISTORICAL_CSV_ODDS_IMPORT_REPORT.md").write_text(
        _import_report_md(stats_dict, str(backup_path) if backup_path else None),
        encoding="utf-8",
    )
    (ROOT / "CSV_TO_FIXTURE_MATCHING_REPORT.md").write_text(
        _matching_report_md(unmatched, stats_dict), encoding="utf-8"
    )

    mode = "DRY-RUN" if args.dry_run else "IMPORT"
    print(f"\n=== DATA-1B {mode} ===")
    print(f"Files: {stats.files_discovered} | Parsed rows: {stats.rows_parsed}")
    print(f"Inserted: {stats.rows_inserted} | Dup skipped: {stats.rows_skipped_duplicate}")
    print(f"Matched: {stats.rows_matched} | Unmatched: {stats.rows_unmatched}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
