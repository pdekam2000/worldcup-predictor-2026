#!/usr/bin/env python3
"""Phase API-K — UEFA odds intelligence deep audit."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACTS = ROOT / "artifacts"
MAPPING_PATH = ARTIFACTS / "uefa_fixture_mapping.json"
BACKTEST_API_J = ARTIFACTS / "uefa_club_backtest.json"


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    if BACKTEST_API_J.is_file() and not (ARTIFACTS / "uefa_club_backtest_api_j_before.json").is_file():
        shutil.copy2(BACKTEST_API_J, ARTIFACTS / "uefa_club_backtest_api_j_before.json")

    mapping = json.loads(MAPPING_PATH.read_text(encoding="utf-8")) if MAPPING_PATH.is_file() else {"fixtures": []}
    fixtures = mapping.get("fixtures") or []

    from worldcup_predictor.egie.uefa_club.odds_intelligence import (
        analyze_market_efficiency,
        analyze_odds_movement,
        analyze_sharp_vs_soft,
        audit_odds_inventory,
        compute_odds_attribution,
        rank_odds_signals,
    )
    from worldcup_predictor.egie.uefa_club.odds_backtest_runner import UefaOddsBacktestRunner, save_backtest

    # STEP 1
    inventory = audit_odds_inventory()
    (ARTIFACTS / "odds_inventory_audit.json").write_text(json.dumps(inventory, indent=2, default=str), encoding="utf-8")
    print("STEP 1 odds inventory written")

    # STEP 2
    attribution = compute_odds_attribution(fixtures)
    (ARTIFACTS / "odds_feature_attribution.json").write_text(json.dumps(attribution, indent=2, default=str), encoding="utf-8")
    print("STEP 2 attribution written")

    # STEP 4-6
    market_eff = analyze_market_efficiency(fixtures)
    (ARTIFACTS / "market_efficiency_analysis.json").write_text(json.dumps(market_eff, indent=2, default=str), encoding="utf-8")
    sharp_soft = analyze_sharp_vs_soft(fixtures)
    (ARTIFACTS / "sharp_vs_soft_book_analysis.json").write_text(json.dumps(sharp_soft, indent=2, default=str), encoding="utf-8")
    movement = analyze_odds_movement(fixtures)
    (ARTIFACTS / "odds_movement_intelligence.json").write_text(json.dumps(movement, indent=2, default=str), encoding="utf-8")
    print("STEP 4-6 market/sharp/movement written")

    # STEP 7
    backtest = UefaOddsBacktestRunner().run(fixtures)
    save_backtest(backtest, ARTIFACTS / "uefa_odds_backtest.json")
    print("STEP 7 odds backtest written")

    # STEP 8
    ranking = rank_odds_signals(attribution, backtest)
    (ARTIFACTS / "odds_signal_ranking.json").write_text(json.dumps(ranking, indent=2, default=str), encoding="utf-8")
    print("STEP 8 signal ranking written")

    api_j = {}
    if BACKTEST_API_J.is_file():
        api_j = json.loads(BACKTEST_API_J.read_text(encoding="utf-8"))

    from scripts._write_phase_api_k_report import write_report

    write_report(
        inventory=inventory,
        attribution=attribution,
        market_eff=market_eff,
        sharp_soft=sharp_soft,
        movement=movement,
        backtest={k: v for k, v in backtest.items() if k != "per_strategy_results"},
        ranking=ranking,
        api_j_backtest=api_j,
    )
    print("STEP 10 report written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
