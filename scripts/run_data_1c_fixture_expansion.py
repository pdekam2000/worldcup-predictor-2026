#!/usr/bin/env python3
"""PHASE DATA-1C — Build historical fixture registry and link CSV odds."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.data_import.historical_fixture_registry import (
    backup_database_data1c,
    build_registry_and_link_odds,
    query_coverage,
)

ARTIFACTS = ROOT / "artifacts"
BACKUP_DIR = ROOT / "data" / "backups"


def _registry_report_md(stats: dict, backup_path: str | None, schema_note: str) -> str:
    return "\n".join(
        [
            "# Historical Fixture Registry Report (DATA-1C)",
            "",
            f"**Backup:** `{backup_path or 'none (dry-run)'}`",
            "",
            "## Schema reuse audit",
            "",
            schema_note,
            "",
            "## Registry build",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Odds rows total | {stats['odds_rows_total']} |",
            f"| Registry candidates (unique match keys) | {stats['registry_candidates']} |",
            f"| Registry rows inserted | {stats['registry_inserted']} |",
            f"| Registry skipped (duplicate rerun) | {stats['registry_skipped_duplicate']} |",
            f"| Production pre-linked (from DATA-1B) | {stats['production_already_linked']} |",
            f"| Production linked (date+teams) | {stats['production_linked']} |",
            f"| Ambiguous production matches | {stats['ambiguous_production']} |",
            f"| Duplicate team name flags | {stats['duplicate_team_flags']} |",
            f"| Team name spelling variants merged | {stats['team_name_variants']} |",
            "",
            "## Errors",
            "",
        ]
        + ([f"- {e}" for e in stats.get("errors", [])] or ["- none"])
        + [""]
    )


def _matching_report_md(stats: dict, ambiguous: list[dict]) -> str:
    lines = [
        "# Historical Odds Matching Report (DATA-1C)",
        "",
        f"**Odds rows linked to registry:** {stats['odds_linked_to_registry']}",
        f"**Registry keys set on odds rows:** {stats['odds_registry_keys_set']}",
        "",
        "## Matching strategy",
        "",
        "1. Registry key = `sha256(match_date | league_normalized | home_norm | away_norm)`",
        "2. One `historical_fixture_registry` row per unique registry key",
        "3. Production `fixtures` table is read-only — links stored as optional `internal_fixture_id`",
        "4. Ambiguous production matches (multiple fixtures same date+teams) are logged, not forced",
        "",
        "## Ambiguous / variant sample (first 40)",
        "",
        "| Type | Date | League / Teams | Detail |",
        "|------|------|----------------|--------|",
    ]
    for item in ambiguous[:40]:
        if "home_variants" in item:
            detail = f"home={list(item['home_variants'].keys())[:2]} away={list(item['away_variants'].keys())[:2]}"
            lines.append(
                f"| team_spelling | {item.get('match_date', '')} | {str(item.get('league', ''))[:24]} | {detail} |"
            )
        else:
            lines.append(
                f"| production_ambiguous | {item.get('match_date', '')} | "
                f"{item.get('home_team', '')[:12]} vs {item.get('away_team', '')[:12]} | "
                f"{item.get('reason', '')} |"
            )
    if len(ambiguous) > 40:
        lines.append(f"\n*…and {len(ambiguous) - 40} more logged in artifacts.*")
    return "\n".join(lines) + "\n"


def _coverage_report_md(coverage: dict) -> str:
    lines = [
        "# DATA-1C Coverage Report",
        "",
        f"**Registry fixtures:** {coverage['registry_fixtures_total']}",
        f"**Odds rows linked:** {coverage['odds_rows_linked']}",
        f"**Production fixtures (unchanged count):** {coverage['production_fixtures_count_unchanged']}",
        "",
        "## Coverage by league (top 30)",
        "",
        "| League | Registry fixtures | Odds rows (aggregated) |",
        "|--------|-------------------|------------------------|",
    ]
    for row in coverage.get("by_league_top30", []):
        lines.append(f"| {row.get('league', '-')} | {row.get('fixtures', 0)} | {row.get('odds_rows', 0)} |")

    lines.extend(["", "## Coverage by season", "", "| Season | Fixtures | Odds rows |", "|--------|----------|-----------|"])
    for row in coverage.get("by_season", []):
        lines.append(f"| {row.get('season', '-')} | {row.get('fixtures', 0)} | {row.get('odds_rows', 0)} |")

    lines.extend(
        [
            "",
            "## Coverage by market",
            "",
            "| Market | Odds rows linked | Distinct registry fixtures |",
            "|--------|------------------|----------------------------|",
        ]
    )
    for row in coverage.get("by_market", []):
        lines.append(
            f"| {row.get('market', '-')} | {row.get('odds_rows', 0)} | {row.get('registry_fixtures', 0)} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="DATA-1C fixture registry expansion")
    parser.add_argument("--dry-run", action="store_true", help="Analyze without writing")
    parser.add_argument("--no-backup", action="store_true", help="Skip DB backup")
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args()

    schema_note = (
        "- Reused production `fixtures` for optional read-only linking (no inserts).\n"
        "- Reused `historical_csv_odds_imports` (DATA-1B) — extended with `registry_key` + `registry_fixture_id`.\n"
        "- Did **not** reuse `oddalerts_fixture_map` (API fixture IDs; CSV uses selection row IDs).\n"
        "- Created staging `historical_fixture_registry` (one row per unique CSV match identity)."
    )

    settings = get_settings()
    db_path = get_db_path(args.db or settings.sqlite_path)
    conn = connect(db_path)

    fixtures_before = conn.execute("SELECT COUNT(*) AS c FROM fixtures").fetchone()["c"]

    backup_path = None
    if not args.dry_run and not args.no_backup:
        backup_path = backup_database_data1c(db_path, BACKUP_DIR)
        print(f"DB backup: {backup_path}")

    stats_obj, ambiguous, _variants, coverage = build_registry_and_link_odds(conn, dry_run=args.dry_run)
    stats = stats_obj.to_dict()

    fixtures_after = conn.execute("SELECT COUNT(*) AS c FROM fixtures").fetchone()["c"]
    stats["production_fixtures_before"] = fixtures_before
    stats["production_fixtures_after"] = fixtures_after

    if not args.dry_run:
        coverage = query_coverage(conn)

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "data_1c_registry_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    (ARTIFACTS / "data_1c_ambiguous_matches.json").write_text(
        json.dumps(ambiguous[:5000], indent=2), encoding="utf-8"
    )
    (ARTIFACTS / "data_1c_coverage.json").write_text(json.dumps(coverage, indent=2), encoding="utf-8")

    (ROOT / "HISTORICAL_FIXTURE_REGISTRY_REPORT.md").write_text(
        _registry_report_md(stats, str(backup_path) if backup_path else None, schema_note),
        encoding="utf-8",
    )
    (ROOT / "HISTORICAL_ODDS_MATCHING_REPORT.md").write_text(_matching_report_md(stats, ambiguous), encoding="utf-8")
    (ROOT / "DATA_1C_COVERAGE_REPORT.md").write_text(_coverage_report_md(coverage), encoding="utf-8")

    mode = "DRY-RUN" if args.dry_run else "IMPORT"
    print(f"\n=== DATA-1C {mode} ===")
    print(f"Registry candidates: {stats['registry_candidates']} | Inserted: {stats['registry_inserted']}")
    print(f"Odds linked: {stats['odds_linked_to_registry']} | Production fixtures: {fixtures_before} -> {fixtures_after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
