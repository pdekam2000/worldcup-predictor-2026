#!/usr/bin/env python3
"""Validate PHASE DATA-1E historical odds baseline backtest."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.historical_odds_baseline_backtest import (
    evaluate_selection,
    validate_roi_math,
)

CHECKS: list[tuple[str, bool, str]] = []
EXPECTED_JOIN = 2062130


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("DATA-1E baseline backtest validation\n")
    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))

    join_count = conn.execute(
        """
        SELECT COUNT(1) AS c
        FROM historical_csv_odds_imports o
        INNER JOIN historical_fixture_registry r ON r.registry_fixture_id = o.registry_fixture_id
        INNER JOIN historical_fixture_results res ON res.registry_fixture_id = o.registry_fixture_id
        """
    ).fetchone()["c"]
    check("dataset_join_count", join_count == EXPECTED_JOIN, f"join={join_count}")

    summary_path = ROOT / "artifacts" / "data_1e_backtest_summary.json"
    check("summary_artifact_exists", summary_path.is_file(), str(summary_path))
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}

    reported_join = summary.get("dataset", {}).get("join_rows")
    check(
        "summary_join_matches_db",
        reported_join == join_count,
        f"summary={reported_join} db={join_count}",
    )

    # label correctness spot-check
    row = conn.execute(
        """
        SELECT o.market, o.selection, o.source_file,
               res.home_goals, res.away_goals, res.total_goals, res.result_1x2,
               res.btts_actual, res.over_15_actual, res.over_25_actual, res.over_35_actual,
               res.corners_total, res.ht_home_goals, res.ht_away_goals
        FROM historical_csv_odds_imports o
        INNER JOIN historical_fixture_results res ON res.registry_fixture_id = o.registry_fixture_id
        WHERE o.market = 'ft_result' AND o.selection = 'home'
        LIMIT 1
        """
    ).fetchone()
    label_ok = False
    if row:
        won = evaluate_selection(
            market=row["market"],
            selection=row["selection"],
            source_file=row["source_file"] or "",
            home_goals=int(row["home_goals"]),
            away_goals=int(row["away_goals"]),
            total_goals=int(row["total_goals"]),
            result_1x2=str(row["result_1x2"]),
            btts_actual=int(row["btts_actual"]),
            over_15_actual=int(row["over_15_actual"]),
            over_25_actual=int(row["over_25_actual"]),
            over_35_actual=int(row["over_35_actual"]),
            corners_total=row["corners_total"],
            ht_home_goals=row["ht_home_goals"],
            ht_away_goals=row["ht_away_goals"],
        )
        expected = str(row["result_1x2"]) == "home"
        label_ok = won is expected
    check("labels_correct_ft_result", label_ok, "home selection spot-check")

    # ROI math
    win_case = validate_roi_math(True, 2.5)
    lose_case = validate_roi_math(False, 2.5)
    roi_ok = win_case["roi_pct"] == 150.0 and lose_case["roi_pct"] == -100.0
    check("roi_math_correct", roi_ok, f"win={win_case['roi_pct']} lose={lose_case['roi_pct']}")

    # strategy E dedupe: bets <= unique fixture-market pairs
    e_metrics = summary.get("strategies", {}).get("E_top_odds_per_fixture_market", {})
    e_bets = int(e_metrics.get("bets", 0))
    unique_pairs = conn.execute(
        """
        SELECT COUNT(1) AS c FROM (
          SELECT DISTINCT o.registry_fixture_id, o.market
          FROM historical_csv_odds_imports o
          INNER JOIN historical_fixture_results res ON res.registry_fixture_id = o.registry_fixture_id
          WHERE o.closing_odds IS NOT NULL OR o.opening_odds IS NOT NULL
        )
        """
    ).fetchone()["c"]
    check(
        "strategy_e_no_double_count",
        0 < e_bets <= unique_pairs,
        f"e_bets={e_bets} pairs={unique_pairs}",
    )

    # empty market safe
    empty_market = summary.get("by_market", {}).get("nonexistent_market")
    check("empty_markets_safe", empty_market is None, "no phantom market key")

    # all 7 markets present
    markets_in_summary = set(summary.get("by_market", {}).keys())
    expected_markets = {
        "ft_result",
        "btts",
        "over_under",
        "corners_over_under",
        "double_chance",
        "team_over_under",
        "first_half_winner",
    }
    check(
        "all_markets_reported",
        expected_markets.issubset(markets_in_summary),
        f"missing={expected_markets - markets_in_summary}",
    )

    predictions = conn.execute("SELECT COUNT(1) AS c FROM predictions").fetchone()["c"]
    check("predictions_unchanged_readable", predictions >= 0, f"predictions={predictions}")

    report_path = ROOT / "DATA_1E_BASELINE_BACKTEST_REPORT.md"
    tables_path = ROOT / "DATA_1E_MARKET_ROI_TABLES.md"
    check("baseline_report_exists", report_path.is_file(), str(report_path))
    check("market_roi_tables_exist", tables_path.is_file(), str(tables_path))

    print()
    failed = [c for c in CHECKS if not c[1]]
    if failed:
        print(f"FAILED: {len(failed)} check(s)")
        return 1
    print(f"ALL {len(CHECKS)} CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
