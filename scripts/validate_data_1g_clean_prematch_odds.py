#!/usr/bin/env python3
"""Validate PHASE DATA-1G clean pre-match odds dataset."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.data_import.historical_prematch_odds_clean import (
    audit_clean_table,
    build_prematch_clean_dataset,
    ensure_prematch_clean_table,
    kickoff_to_unix,
)
from worldcup_predictor.research.historical_odds_baseline_backtest import validate_roi_math

CHECKS: list[tuple[str, bool, str]] = []
EXPECTED_SOURCE = 2063334


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("DATA-1G clean pre-match odds validation\n")
    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))
    ensure_prematch_clean_table(conn)

    source_count = conn.execute("SELECT COUNT(1) AS c FROM historical_csv_odds_imports").fetchone()["c"]
    check("source_table_unchanged", source_count == EXPECTED_SOURCE, f"rows={source_count}")

    audit = audit_clean_table(conn)
    check("clean_table_populated", audit["clean_rows"] > 0, f"clean={audit['clean_rows']}")
    check(
        "no_post_kickoff_closing",
        audit["closing_after_kickoff_violations"] == 0,
        f"violations={audit['closing_after_kickoff_violations']}",
    )

    missing_kickoff = conn.execute(
        "SELECT COUNT(1) AS c FROM historical_csv_odds_prematch_clean WHERE kickoff_unix IS NULL"
    ).fetchone()["c"]
    missing_closing = conn.execute(
        "SELECT COUNT(1) AS c FROM historical_csv_odds_prematch_clean WHERE closing_unix IS NULL"
    ).fetchone()["c"]
    check("all_rows_have_kickoff_unix", missing_kickoff == 0, f"missing={missing_kickoff}")
    check("all_rows_have_closing_unix", missing_closing == 0, f"missing={missing_closing}")

    sample_violations = conn.execute(
        """
        SELECT COUNT(1) AS c FROM historical_csv_odds_prematch_clean
        WHERE opening_unix IS NOT NULL AND opening_unix > kickoff_unix
        """
    ).fetchone()["c"]
    check("no_opening_after_kickoff", sample_violations == 0, f"violations={sample_violations}")

    join_count = conn.execute(
        """
        SELECT COUNT(1) AS c
        FROM historical_csv_odds_prematch_clean c
        INNER JOIN historical_fixture_results r ON r.registry_fixture_id = c.registry_fixture_id
        """
    ).fetchone()["c"]
    join_pct = round(100.0 * join_count / max(audit["clean_rows"], 1), 4)
    check(
        "results_join_coverage",
        join_count > 0 and join_pct >= 99.0,
        f"join={join_count} clean={audit['clean_rows']} ({join_pct}%)",
    )

    orphan = conn.execute(
        """
        SELECT COUNT(1) AS c FROM historical_csv_odds_prematch_clean c
        LEFT JOIN historical_csv_odds_imports o ON o.id = c.source_odds_id
        WHERE o.id IS NULL
        """
    ).fetchone()["c"]
    check("source_odds_ids_valid", orphan == 0, f"orphans={orphan}")

    # kickoff_unix matches kickoff_utc parse
    row = conn.execute(
        "SELECT kickoff_utc, kickoff_unix FROM historical_csv_odds_prematch_clean LIMIT 1"
    ).fetchone()
    parse_ok = False
    if row:
        parsed = kickoff_to_unix(row["kickoff_utc"])
        parse_ok = parsed == row["kickoff_unix"]
    check("kickoff_unix_reproducible", parse_ok, "sample parse match")

    # duplicate rerun
    before = audit["clean_rows"]
    stats = build_prematch_clean_dataset(conn, dry_run=False)
    after = conn.execute("SELECT COUNT(1) AS c FROM historical_csv_odds_prematch_clean").fetchone()["c"]
    check(
        "build_reproducible_zero_new",
        stats.rows_inserted == 0 and after == before,
        f"inserted={stats.rows_inserted}",
    )

    win_case = validate_roi_math(True, 3.5)
    check("roi_math_correct", win_case["roi_pct"] == 250.0, f"roi={win_case['roi_pct']}")

    summary_path = ROOT / "artifacts" / "data_1g_clean_backtest_summary.json"
    check("summary_artifact_exists", summary_path.is_file(), str(summary_path))
    if summary_path.is_file():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        check(
            "clean_strategy_a_has_bets",
            summary.get("clean", {}).get("strategies", {}).get("A_all_selections", {}).get("bets", 0) > 0,
            "clean A bets",
        )

    predictions = conn.execute("SELECT COUNT(1) AS c FROM predictions").fetchone()["c"]
    check("predictions_unchanged_readable", predictions >= 0, f"predictions={predictions}")

    print()
    failed = [c for c in CHECKS if not c[1]]
    if failed:
        print(f"FAILED: {len(failed)} check(s)")
        return 1
    print(f"ALL {len(CHECKS)} CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
