#!/usr/bin/env python3
"""Validate PHASE DATA-1C historical fixture registry expansion."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.data_import.historical_fixture_registry import (
    build_registry_and_link_odds,
    ensure_data_1c_schema,
    query_coverage,
)

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("DATA-1C fixture expansion validation\n")
    settings = get_settings()
    db_path = get_db_path(settings.sqlite_path)
    conn = connect(db_path)
    ensure_data_1c_schema(conn)

    registry_count = conn.execute("SELECT COUNT(*) AS c FROM historical_fixture_registry").fetchone()["c"]
    check("registry_table_populated", registry_count > 0, f"{registry_count} fixtures")

    unique_keys = conn.execute(
        "SELECT COUNT(DISTINCT registry_key) AS c FROM historical_fixture_registry"
    ).fetchone()["c"]
    check(
        "registry_keys_unique",
        unique_keys == registry_count,
        f"rows={registry_count} distinct_keys={unique_keys}",
    )

    odds_total = conn.execute("SELECT COUNT(*) AS c FROM historical_csv_odds_imports").fetchone()["c"]
    odds_linked = conn.execute(
        "SELECT COUNT(*) AS c FROM historical_csv_odds_imports WHERE registry_fixture_id IS NOT NULL"
    ).fetchone()["c"]
    check(
        "odds_rows_linked_to_registry",
        odds_linked == odds_total,
        f"linked={odds_linked} total={odds_total}",
    )

    orphan_odds = conn.execute(
        """
        SELECT COUNT(*) AS c FROM historical_csv_odds_imports o
        LEFT JOIN historical_fixture_registry r ON r.registry_fixture_id = o.registry_fixture_id
        WHERE o.registry_fixture_id IS NOT NULL AND r.registry_fixture_id IS NULL
        """
    ).fetchone()["c"]
    check("no_orphan_registry_links", orphan_odds == 0, f"orphans={orphan_odds}")

    fixtures_count = conn.execute("SELECT COUNT(*) AS c FROM fixtures").fetchone()["c"]
    synthetic_fixtures = conn.execute(
        "SELECT COUNT(*) AS c FROM fixtures WHERE source IN ('oddalerts_csv', 'historical_csv', 'csv_registry')"
    ).fetchone()["c"]
    check(
        "production_fixtures_not_polluted",
        synthetic_fixtures == 0,
        f"fixtures={fixtures_count} synthetic={synthetic_fixtures}",
    )

    predictions_count = conn.execute("SELECT COUNT(*) AS c FROM predictions").fetchone()["c"]
    check("predictions_table_readable", predictions_count >= 0, f"predictions={predictions_count}")

    before_registry = registry_count
    stats, ambiguous, _, _ = build_registry_and_link_odds(conn, dry_run=False)
    after_registry = conn.execute("SELECT COUNT(*) AS c FROM historical_fixture_registry").fetchone()["c"]
    check(
        "duplicate_rerun_zero_new_fixtures",
        stats.registry_inserted == 0 and after_registry == before_registry,
        f"inserted={stats.registry_inserted} before={before_registry} after={after_registry}",
    )

    ambiguous_path = ROOT / "artifacts" / "data_1c_ambiguous_matches.json"
    ambiguous_ok = ambiguous_path.is_file()
    if ambiguous_ok:
        payload = json.loads(ambiguous_path.read_text(encoding="utf-8"))
        ambiguous_ok = isinstance(payload, list)
    check("ambiguous_matches_logged", ambiguous_ok, str(ambiguous_path))

    coverage = query_coverage(conn)
    check(
        "coverage_by_league_queryable",
        len(coverage.get("by_league_top30", [])) > 0,
        f"leagues={len(coverage.get('by_league_top30', []))}",
    )
    check(
        "coverage_by_market_queryable",
        len(coverage.get("by_market", [])) >= 5,
        f"markets={len(coverage.get('by_market', []))}",
    )
    check(
        "coverage_by_season_queryable",
        len(coverage.get("by_season", [])) > 0,
        f"seasons={len(coverage.get('by_season', []))}",
    )

    bad_dates = conn.execute(
        """
        SELECT COUNT(*) AS c FROM historical_fixture_registry
        WHERE match_date IS NULL OR length(match_date) < 10
        """
    ).fetchone()["c"]
    check("registry_dates_valid", bad_dates == 0, f"bad={bad_dates}")

    print()
    failed = [c for c in CHECKS if not c[1]]
    if failed:
        print(f"FAILED: {len(failed)} check(s)")
        return 1
    print(f"ALL {len(CHECKS)} CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
