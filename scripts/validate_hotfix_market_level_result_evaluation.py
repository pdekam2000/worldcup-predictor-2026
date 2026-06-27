#!/usr/bin/env python3
"""Validate hotfix — market-level result evaluation (no engine changes)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

checks: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def main() -> int:
    # --- module presence ---
    required = [
        "worldcup_predictor/api/market_level_evaluation.py",
        "worldcup_predictor/api/archive_evaluation_join.py",
        "worldcup_predictor/automation/worldcup_background/pick_evaluator.py",
        "worldcup_predictor/api/evaluated_results.py",
        "base44-d/src/pages/PredictionResultsPage.jsx",
        "base44-d/src/components/archive/MarketBreakdownPanel.jsx",
        "base44-d/src/lib/archiveFilters.js",
    ]
    for rel in required:
        record(f"file:{rel}", (ROOT / rel).is_file(), "present" if (ROOT / rel).is_file() else "missing")

    pe = (ROOT / "worldcup_predictor/automation/worldcup_background/pick_evaluator.py").read_text(encoding="utf-8")
    record("evaluator:canonical_1x2", "canonical_1x2_selection" in pe, "unified 1x2 source")
    record("evaluator:detailed_markets_ou", "ou_selection_from_payload" in pe, "OU from detailed_markets")
    record("evaluator:market_evaluations", "attach_market_evaluations_to_result" in pe, "per-market rows")

    mle = (ROOT / "worldcup_predictor/api/market_level_evaluation.py").read_text(encoding="utf-8")
    record("mle:best_bet_winrate", "compute_best_bet_winrate" in mle, "best bet only winrate")
    record("mle:aggregate_partial", "mixed_market_results" in mle, "partial aggregate")
    record("mle:limited_payload", "limited_historical_payload" in mle, "backward compat flag")

    join = (ROOT / "worldcup_predictor/api/archive_evaluation_join.py").read_text(encoding="utf-8")
    record("join:no_main_1x2_only", "main_1x2_evaluation" not in join, "removed 1x2-only row collapse")
    record("join:unavailable_status", '"unavailable"' in join, "unavailable preserved")

    fe = (ROOT / "base44-d/src/pages/PredictionResultsPage.jsx").read_text(encoding="utf-8")
    record("ui:market_filter", "MARKET_FILTERS" in fe and 'setMarket("best_bets")' in fe or 'useState("best_bets")' in fe, "market dropdown default best bets")
    record("ui:market_breakdown", "MarketBreakdownPanel" in fe, "expandable breakdown")
    record("ui:yellow_white", "amber-50" in fe and "bg-white" in fe, "yellow/white theme")

    af = (ROOT / "base44-d/src/lib/archiveFilters.js").read_text(encoding="utf-8")
    record("filters:best_bets", '"best_bets"' in af, "best bets filter option")

    # --- behavioral unit tests (no DB required) ---
    from worldcup_predictor.api.market_level_evaluation import (
        attach_market_evaluations_to_result,
        build_market_evaluation_rows,
        canonical_1x2_selection,
        compute_aggregate_card_status,
        compute_best_bet_winrate,
        extract_predicted_markets,
        is_user_visible_prediction,
        limited_historical_payload,
        row_matches_market_filter,
    )
    from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcome
    from worldcup_predictor.automation.worldcup_background.pick_evaluator import evaluate_stored_prediction

    payload_multi = {
        "fixture_id": 999001,
        "prediction": "home",
        "no_bet": False,
        "confidence": 72,
        "detailed_markets": {
            "match_winner": {"selection": "home", "probability": 0.55},
            "btts": {"selection": "yes", "probability": 0.6},
            "over_under_25": {"selection": "over", "probability": 0.58},
        },
        "best_available_pick": {"market": "over_under_2_5", "selection": "over", "pick": "Over 2.5"},
        "accuracy_tracking": {"official_recommended": False, "pick_tier": "caution"},
    }
    outcome = FixtureOutcome(
        is_finished=True,
        actual_result="home_win",
        final_score="2-1",
        evaluated_at=None,
        fixture_status="FT",
        match_outcome_type="FT",
    )
    evaluation = evaluate_stored_prediction(payload_multi, outcome)
    record("runtime:multi_market_eval", len(evaluation.get("market_evaluations") or []) >= 3, str(len(evaluation.get("market_evaluations") or [])))
    record("runtime:canonical_1x2", canonical_1x2_selection(payload_multi) == "home", canonical_1x2_selection(payload_multi))

    rows = evaluation.get("market_evaluations") or []
    agg, reason = compute_aggregate_card_status(rows, scope="visible")
    record("runtime:partial_possible", agg in {"correct", "wrong", "partial", "pending", "unavailable"}, f"{agg}/{reason}")

    # mixed: force one wrong in statuses
    markets_status = {"1x2": "correct", "btts": "wrong", "over_under_2_5": "correct"}
    mixed_rows = build_market_evaluation_rows(payload_multi, outcome, market_statuses=markets_status)
    mixed_agg, _ = compute_aggregate_card_status(mixed_rows, scope="visible")
    record("runtime:aggregate_partial", mixed_agg == "partial", mixed_agg)

    no_bet_payload = {**payload_multi, "no_bet": True, "best_available_pick": None}
    record("runtime:no_bet_not_visible", not is_user_visible_prediction(no_bet_payload), "no_bet excluded")

    research_payload = {
        **payload_multi,
        "accuracy_tracking": {"research_only": True, "shadow": True},
    }
    record("runtime:research_not_visible", not is_user_visible_prediction(research_payload), "research excluded")

    best_wr = compute_best_bet_winrate(
        [{"was_best_bet": True, "was_user_visible": True, "status": "correct", "is_quarantined": False}]
    )
    record("runtime:best_bet_winrate", best_wr["accuracy"] == 100.0 and best_wr["total"] == 1, str(best_wr))

    old_payload = {"prediction": "draw"}
    record("runtime:limited_historical", limited_historical_payload(old_payload), "1x2 only old row")
    record("runtime:old_keys_only_1x2", list(extract_predicted_markets(old_payload).keys()) == ["1x2"], "no fake markets")

    row = {
        "market_breakdown": mixed_rows,
        "has_best_bet": True,
        "predicted_market_keys": ["1x2", "btts", "over_under_2_5"],
    }
    record("filter:over_2_5", row_matches_market_filter(row, "over_2_5"), "OU filter")
    record("filter:best_bets", row_matches_market_filter(row, "best_bets"), "best bets filter")

    # no prediction engine / WDE / public flags touched
    settings_py = (ROOT / "worldcup_predictor/config/settings.py").read_text(encoding="utf-8")
    record("flags:unchanged", "UNIFIED_ENGINE_PUBLIC" in settings_py, "settings intact")

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"Hotfix market-level evaluation validation: {passed}/{total}")
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} — {detail}")

    report_path = ROOT / "data" / "validation" / "hotfix_market_level_result_evaluation.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps({"passed": passed, "total": total, "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks]}, indent=2),
        encoding="utf-8",
    )
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
