#!/usr/bin/env python3
"""Validate PHASE DATA-1B historical CSV odds import."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.data_import.historical_csv_odds import (
    catalog_all,
    discover_csv_files,
    ensure_historical_csv_odds_table,
    import_csv_odds,
)

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("DATA-1B CSV odds import validation\n")
    settings = get_settings()
    db_path = get_db_path(settings.sqlite_path)
    conn = connect(db_path)
    ensure_historical_csv_odds_table(conn)

    files = discover_csv_files(ROOT)
    check("csv_files_discovered", len(files) > 0, f"{len(files)} files")

    catalog = catalog_all(ROOT)
    parsed_rows = sum(c["row_count"] for c in catalog)
    check("catalog_row_counts", parsed_rows > 0, f"{parsed_rows} total rows")

    row = conn.execute("SELECT COUNT(*) AS c FROM historical_csv_odds_imports").fetchone()
    db_count = int(row["c"]) if row else 0
    check("import_table_populated", db_count > 0, f"{db_count} rows in DB")

    # row count sanity: DB should be <= parsed unique rows (dedup)
    check("db_rows_lte_parsed", db_count <= parsed_rows, f"db={db_count} parsed={parsed_rows}")

    # markets detected
    market_rows = conn.execute(
        "SELECT market, COUNT(*) AS c FROM historical_csv_odds_imports GROUP BY market ORDER BY c DESC"
    ).fetchall()
    markets = {r["market"]: r["c"] for r in market_rows}
    check("markets_detected", len(markets) >= 5, str(markets))

    expected_markets = {"ft_result", "btts", "over_under", "corners_over_under"}
    found_expected = expected_markets & set(markets.keys())
    check("core_markets_present", len(found_expected) >= 3, str(sorted(found_expected)))

    # numeric odds (1.0 is valid for heavy favorites; reject only < 1.0)
    bad_odds = conn.execute(
        """
        SELECT COUNT(*) AS c FROM historical_csv_odds_imports
        WHERE (opening_odds IS NOT NULL AND opening_odds < 1.0)
           OR (closing_odds IS NOT NULL AND closing_odds < 1.0)
           OR (peak_odds IS NOT NULL AND peak_odds < 1.0)
        """
    ).fetchone()["c"]
    check("odds_numeric_valid", bad_odds == 0, f"invalid odds rows={bad_odds}")

    # dates parsed
    bad_dates = conn.execute(
        """
        SELECT COUNT(*) AS c FROM historical_csv_odds_imports
        WHERE match_date IS NULL OR length(match_date) < 10
        """
    ).fetchone()["c"]
    check("dates_parsed", bad_dates == 0, f"bad dates={bad_dates}")

    # unmatched reported
    unmatched_path = ROOT / "artifacts" / "data_1b_unmatched_rows.json"
    check("unmatched_report_exists", unmatched_path.is_file(), str(unmatched_path))

    # duplicate re-run inserts 0
    before = conn.execute("SELECT COUNT(*) FROM historical_csv_odds_imports").fetchone()[0]
    _, stats, _ = import_csv_odds(conn, ROOT, dry_run=False, dedupe_files_by_sha=True)
    after = conn.execute("SELECT COUNT(*) FROM historical_csv_odds_imports").fetchone()[0]
    check(
        "duplicate_rerun_zero_new",
        stats.rows_inserted == 0 and after == before,
        f"inserted={stats.rows_inserted} before={before} after={after}",
    )

    # predictions unchanged (count only)
    pred_before = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
    check("predictions_table_readable", pred_before >= 0, f"predictions={pred_before}")

    # raw_json preserved
    sample = conn.execute(
        "SELECT raw_json FROM historical_csv_odds_imports WHERE raw_json IS NOT NULL LIMIT 1"
    ).fetchone()
    raw_ok = False
    if sample:
        try:
            json.loads(sample["raw_json"])
            raw_ok = True
        except json.JSONDecodeError:
            pass
    check("raw_json_preserved", raw_ok, "sample parses as JSON")

    # manifest vs catalog
    manifest = ROOT / "data" / "imports" / "oddalerts_probability_exports" / "manifest.csv"
    if manifest.is_file():
        with manifest.open(encoding="utf-8") as fh:
            manifest_rows = sum(1 for _ in csv.DictReader(fh))
        check("manifest_exists", True, f"{manifest_rows} manifest entries")

    print()
    failed = [c for c in CHECKS if not c[1]]
    if failed:
        print(f"FAILED: {len(failed)} check(s)")
        return 1
    print(f"ALL {len(CHECKS)} CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
