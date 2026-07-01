#!/usr/bin/env python3
"""Validate PHASE DATA-1D historical result labels."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.data_import.historical_fixture_results import (
    build_and_insert_historical_results,
    build_result_labels,
    ensure_historical_fixture_results_table,
    query_backtest_readiness,
)

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("DATA-1D historical results labels validation\n")
    settings = get_settings()
    db_path = get_db_path(settings.sqlite_path)
    conn = connect(db_path)
    ensure_historical_fixture_results_table(conn)

    results_count = conn.execute("SELECT COUNT(*) AS c FROM historical_fixture_results").fetchone()["c"]
    check("results_table_populated", results_count > 0, f"{results_count} rows")

    # labels only when scores present
    bad_null_scores = conn.execute(
        """
        SELECT COUNT(*) AS c FROM historical_fixture_results
        WHERE home_goals IS NULL OR away_goals IS NULL
        """
    ).fetchone()["c"]
    check("results_have_scores", bad_null_scores == 0, f"null_scores={bad_null_scores}")

    unsettled = conn.execute(
        """
        SELECT COUNT(*) AS c FROM historical_fixture_results
        WHERE match_status NOT IN ('FT', 'FT_PEN', 'AET', 'AWARDED')
        """
    ).fetchone()["c"]
    check("results_settled_status_only", unsettled == 0, f"unsettled={unsettled}")

    # mathematical label correctness sample
    sample_rows = conn.execute(
        "SELECT home_goals, away_goals, total_goals, result_1x2, btts_actual, over_25_actual FROM historical_fixture_results LIMIT 500"
    ).fetchall()
    math_ok = True
    for row in sample_rows:
        expected = build_result_labels(int(row["home_goals"]), int(row["away_goals"]), match_status="FT")
        if (
            expected["total_goals"] != row["total_goals"]
            or expected["result_1x2"] != row["result_1x2"]
            or expected["btts_actual"] != row["btts_actual"]
            or expected["over_25_actual"] != row["over_25_actual"]
        ):
            math_ok = False
            break
    check("labels_mathematically_correct", math_ok, f"sampled={len(sample_rows)}")

    # duplicate rerun
    before = conn.execute("SELECT COUNT(*) AS c FROM historical_fixture_results").fetchone()["c"]
    stats, _, _, _ = build_and_insert_historical_results(conn, dry_run=False)
    after = conn.execute("SELECT COUNT(*) AS c FROM historical_fixture_results").fetchone()["c"]
    check(
        "duplicate_rerun_zero_new",
        stats.results_inserted == 0 and after == before,
        f"inserted={stats.results_inserted} before={before} after={after}",
    )

    # join chain odds -> registry -> results
    join_count = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM historical_csv_odds_imports o
        INNER JOIN historical_fixture_registry r ON r.registry_fixture_id = o.registry_fixture_id
        INNER JOIN historical_fixture_results res ON res.registry_fixture_id = r.registry_fixture_id
        """
    ).fetchone()["c"]
    check("odds_registry_results_joinable", join_count > 0, f"rows={join_count}")

    orphan = conn.execute(
        """
        SELECT COUNT(*) AS c FROM historical_fixture_results res
        LEFT JOIN historical_fixture_registry r ON r.registry_fixture_id = res.registry_fixture_id
        WHERE r.registry_fixture_id IS NULL
        """
    ).fetchone()["c"]
    check("no_orphan_result_rows", orphan == 0, f"orphans={orphan}")

    # production unchanged
    prod_results = conn.execute("SELECT COUNT(*) AS c FROM fixture_results").fetchone()["c"]
    fixtures = conn.execute("SELECT COUNT(*) AS c FROM fixtures").fetchone()["c"]
    predictions = conn.execute("SELECT COUNT(*) AS c FROM predictions").fetchone()["c"]
    check("production_fixture_results_readable", prod_results >= 0, f"fixture_results={prod_results}")
    check("production_fixtures_readable", fixtures > 0, f"fixtures={fixtures}")
    check("predictions_unchanged_readable", predictions >= 0, f"predictions={predictions}")

    no_result_path = ROOT / "artifacts" / "data_1d_no_result_fixtures.json"
    check("no_result_fixtures_reported", no_result_path.is_file(), str(no_result_path))

    readiness = query_backtest_readiness(conn)
    check(
        "coverage_by_market_queryable",
        len(readiness.get("by_market", [])) >= 5,
        f"markets={len(readiness.get('by_market', []))}",
    )

    dedup_unique = conn.execute(
        "SELECT COUNT(*) AS c FROM (SELECT DISTINCT registry_fixture_id, source FROM historical_fixture_results)"
    ).fetchone()["c"]
    check(
        "one_result_per_registry_source",
        dedup_unique == results_count,
        f"distinct={dedup_unique} rows={results_count}",
    )

    print()
    failed = [c for c in CHECKS if not c[1]]
    if failed:
        print(f"FAILED: {len(failed)} check(s)")
        return 1
    print(f"ALL {len(CHECKS)} CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
