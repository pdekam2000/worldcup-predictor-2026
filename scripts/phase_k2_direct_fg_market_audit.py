#!/usr/bin/env python3
"""Phase K2 — direct first-goal market audit."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACTS = ROOT / "artifacts"
MAPPING_PATH = ARTIFACTS / "uefa_fixture_mapping.json"


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    mapping = json.loads(MAPPING_PATH.read_text(encoding="utf-8")) if MAPPING_PATH.is_file() else {"fixtures": []}
    fixtures = mapping.get("fixtures") or []

    from worldcup_predictor.egie.uefa_club.first_goal_market_audit import (
        analyze_bookmaker_fg_accuracy,
        audit_first_goal_coverage,
        audit_first_goal_market_inventory,
        rank_k2_signals,
        run_k2_backtest,
    )

    inventory = audit_first_goal_market_inventory()
    (ARTIFACTS / "first_goal_market_inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    print("STEP 1 inventory written")

    coverage = audit_first_goal_coverage()
    (ARTIFACTS / "first_goal_market_coverage.json").write_text(json.dumps(coverage, indent=2), encoding="utf-8")
    print("STEP 2 coverage written")

    backtest = run_k2_backtest(fixtures)
    (ARTIFACTS / "first_goal_market_backtest.json").write_text(json.dumps(backtest, indent=2), encoding="utf-8")
    print("STEP 3 backtest written")

    books = analyze_bookmaker_fg_accuracy(fixtures)
    (ARTIFACTS / "first_goal_bookmaker_ranking.json").write_text(json.dumps(books, indent=2), encoding="utf-8")
    print("STEP 4 bookmaker analysis written")

    ranking = rank_k2_signals(backtest, books)
    (ARTIFACTS / "first_goal_signal_ranking.json").write_text(json.dumps(ranking, indent=2), encoding="utf-8")
    print("STEP 5 ranking written")

    from scripts._write_phase_k2_report import write_report

    write_report(
        inventory=inventory,
        coverage=coverage,
        backtest=backtest,
        books=books,
        ranking=ranking,
    )
    print("STEP 6 report written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
