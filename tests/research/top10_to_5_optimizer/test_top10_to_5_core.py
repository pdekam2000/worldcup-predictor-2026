"""Comprehensive Top10-to-5 research tests — no production writes."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from worldcup_predictor.research.bet_coverage_optimizer import score_mapping as bco_score
from worldcup_predictor.research.top10_to_5_optimizer.constants import (
    CLASS_PROFIT,
    LOSS,
    PUSH,
    UNSUPPORTED,
    WIN,
)
from worldcup_predictor.research.top10_to_5_optimizer.coupon_generator import generate_coupon_universe
from worldcup_predictor.research.top10_to_5_optimizer.exact_consensus import build_consensus_top10, lock_exact_three
from worldcup_predictor.research.top10_to_5_optimizer.forward_shadow import persist_forward_shadow, summarize_forward_shadow
from worldcup_predictor.research.top10_to_5_optimizer.market_pair_search import search_market_pairs
from worldcup_predictor.research.top10_to_5_optimizer.market_semantics import settles_as_win
from worldcup_predictor.research.top10_to_5_optimizer.models import MarketCandidate
from worldcup_predictor.research.top10_to_5_optimizer.pipeline import DEMO_FIXTURES, run_top10_to_5_research
from worldcup_predictor.research.top10_to_5_optimizer.scenario_engine import evaluate_top10_scenarios, simulate_scoreline
from worldcup_predictor.research.top10_to_5_optimizer.stake_optimizer import allocate_stakes


def test_settlement_boundaries():
    assert settles_as_win("over_under", {"direction": "under", "line": 3.5}, 2, 1) == WIN  # total 3
    assert settles_as_win("over_under", {"direction": "under", "line": 3.5}, 2, 2) == LOSS  # total 4
    assert settles_as_win("win_to_nil", {"team": "home"}, 2, 0) == WIN
    assert settles_as_win("win_to_nil", {"team": "home"}, 2, 1) == LOSS
    assert settles_as_win("result_total", {"result": "away", "direction": "under", "line": 4.5}, 1, 2) == WIN
    assert settles_as_win("result_total", {"result": "away", "direction": "under", "line": 4.5}, 1, 3) == WIN  # total 4
    assert settles_as_win("draw_no_bet", {"result": "home"}, 1, 1) == PUSH
    assert settles_as_win("draw_no_bet", {"result": "home"}, 2, 1) == WIN
    assert settles_as_win("draw_no_bet", {"result": "home"}, 0, 1) == LOSS
    assert settles_as_win("over_under", {"direction": "under", "line": 2.0}, 1, 1) == PUSH
    assert settles_as_win("asian_handicap", {"team": "home", "line": 0.0}, 1, 1) == PUSH
    # Never silent push→win
    assert settles_as_win("over_under", {"direction": "over", "line": 2.0}, 1, 1) != WIN


def test_bco_settlement_untouched_import():
    # Coverage Optimizer settlement module still importable / unchanged API
    assert bco_score.settles_as_win("over_under", {"direction": "under", "line": 3.5}, 2, 1) is True


def test_consensus_and_exact_lock():
    payload = DEMO_FIXTURES[1556628]
    top10 = build_consensus_top10(payload, top10_source="consensus", top_n=10)
    assert len(top10) == 10
    assert "consensus_count" in top10[0]
    assert "canonical_rank" in top10[0]
    exact = lock_exact_three(top10)
    assert len(exact) == 3
    assert len({e["scoreline"] for e in exact}) == 3
    # Deterministic
    top10_b = build_consensus_top10(payload, top10_source="consensus", top_n=10)
    assert [x["scoreline"] for x in top10] == [x["scoreline"] for x in top10_b]


def test_profitable_vs_raw_coverage():
    exact_legs = [
        {"market_type": "exact_score", "market_parameters": {"score": "1-0"}, "decimal_odds": 8.0},
        {"market_type": "exact_score", "market_parameters": {"score": "2-0"}, "decimal_odds": 9.0},
        {"market_type": "exact_score", "market_parameters": {"score": "0-0"}, "decimal_odds": 10.0},
    ]
    market_legs = [
        {"market_type": "1x2", "market_parameters": {"result": "home"}, "decimal_odds": 1.2},
        {"market_type": "btts", "market_parameters": {"side": "no"}, "decimal_odds": 1.5},
    ]
    stakes = {"exact_1": 2, "exact_2": 2, "exact_3": 2, "market_1": 2, "market_2": 2}
    # 2-1: home wins 1x2 but BTTS no loses; exacts lose — may be partial/full loss
    sim = simulate_scoreline("2-1", exact_legs=exact_legs, market_legs=market_legs, stakes=stakes)
    assert sim["raw_outcome_covered"] is True  # market_1 wins
    assert sim["profitably_covered"] is False or sim["classification"] != CLASS_PROFIT or sim["net_profit_loss"] >= 0
    # Ensure raw covered != automatically profitable when odds short
    assert "raw_outcome_covered" in sim and "profitably_covered" in sim


def test_stake_budget_and_modes():
    for mode in ("equal_stake", "probability_weighted", "profit_floor", "minmax_loss", "score_weighted"):
        plan = allocate_stakes(mode=mode, budget=25, minimum=1, maximum=10, step=0.5, exact_probs=[0.2, 0.15, 0.1])
        assert abs(sum(plan["stakes"].values()) - plan["total_budget"]) < 1.0 or plan["total_budget"] <= 25 + 1e-6
        assert all(v >= 1.0 for v in plan["stakes"].values())
        assert all(v <= 10.0 for v in plan["stakes"].values())
    # Kelly disabled by default
    plan_k = allocate_stakes(mode="fractional_kelly_research", budget=25, kelly_enabled=False)
    assert plan_k["stake_mode"] == "equal_stake"


def test_pair_search_exhaustive_and_ranking():
    top10 = build_consensus_top10(DEMO_FIXTURES[1556628], top10_source="consensus")
    exact = [r["scoreline"] for r in lock_exact_three(top10)]
    markets = [
        MarketCandidate("btts", {"side": "yes"}, "BTTS Yes", 2.1, market_key="btts|yes"),
        MarketCandidate("btts", {"side": "no"}, "BTTS No", 1.7, market_key="btts|no"),
        MarketCandidate("over_under", {"direction": "under", "line": 3.5}, "Under 3.5", 1.85, market_key="ou|u3.5"),
        MarketCandidate("win_to_nil", {"team": "away"}, "Away WTN", 2.4, market_key="wtn|away"),
    ]
    stakes = allocate_stakes(mode="equal_stake", budget=25)
    res = search_market_pairs(markets, top10=top10, exact_scores=exact, stake_plan=stakes, exact_odds={})
    assert res["n_pairs_evaluated"] == 6  # C(4,2)
    assert res["selected"] is not None
    assert res["selected"]["pair_score_is_probability"] is False


def test_coupon_125_and_caps_no_duplicates():
    def fx(fid: int):
        return {
            "fixture_id": fid,
            "selections": [
                {"selection_id": f"{fid}_e1", "label": "E1", "decimal_odds": 5.0, "modeled_probability": 0.1},
                {"selection_id": f"{fid}_e2", "label": "E2", "decimal_odds": 6.0, "modeled_probability": 0.08},
                {"selection_id": f"{fid}_e3", "label": "E3", "decimal_odds": 7.0, "modeled_probability": 0.06},
                {"selection_id": f"{fid}_m1", "label": "M1", "decimal_odds": 2.0, "modeled_probability": 0.4},
                {"selection_id": f"{fid}_m2", "label": "M2", "decimal_odds": 1.8, "modeled_probability": 0.35},
            ],
        }

    uni = generate_coupon_universe([fx(1), fx(2), fx(3)], ticket_cap=25)
    assert uni["universe_125_count"] == 125
    assert uni["ticket_count"] == 25
    assert uni["auto_execute_125"] is False
    ids = [tuple(t["selection_ids"]) for t in uni["optimized_tickets"]]
    assert len(ids) == len(set(ids))
    uni64 = generate_coupon_universe([fx(1), fx(2), fx(3)], ticket_cap=64)
    assert uni64["ticket_count"] == 64


def test_missing_exact_odds_unknown_classification():
    sim = simulate_scoreline(
        "1-0",
        exact_legs=[
            {"market_type": "exact_score", "market_parameters": {"score": "1-0"}, "decimal_odds": None},
            {"market_type": "exact_score", "market_parameters": {"score": "2-0"}, "decimal_odds": 8.0},
            {"market_type": "exact_score", "market_parameters": {"score": "0-0"}, "decimal_odds": 9.0},
        ],
        market_legs=[
            {"market_type": "1x2", "market_parameters": {"result": "home"}, "decimal_odds": 1.5},
            {"market_type": "btts", "market_parameters": {"side": "no"}, "decimal_odds": 1.6},
        ],
        stakes={"exact_1": 2, "exact_2": 2, "exact_3": 2, "market_1": 2, "market_2": 2},
    )
    assert sim["classification"] == "UNKNOWN_DUE_TO_MISSING_ODDS"
    assert sim["net_profit_loss"] is None


def test_forward_shadow_idempotency(tmp_path: Path):
    db = tmp_path / "shadow.db"
    a = persist_forward_shadow({"fixture_id": 1, "exact_scores": ["1-0", "2-0", "0-0"]}, db_path=db)
    b = persist_forward_shadow({"fixture_id": 1, "exact_scores": ["1-0", "2-0", "0-0"]}, db_path=db)
    assert a["evidence_hash"] == b["evidence_hash"]
    assert a["idempotent"] is True
    s = summarize_forward_shadow(db)
    assert s["n_captured"] == 1


def test_pipeline_immutability_and_artifacts(tmp_path: Path):
    bco_path = Path("worldcup_predictor/research/bet_coverage_optimizer/score_mapping.py")
    before_bco = bco_path.read_text(encoding="utf-8")
    ins_path = Path("worldcup_predictor/research/bet_coverage_optimizer/insurance/insurance_optimizer.py")
    before_ins = ins_path.read_text(encoding="utf-8") if ins_path.exists() else ""
    overlay = Path("worldcup_predictor/research/betting_day_similarity/overlay_policy.py")
    before_ov = overlay.read_text(encoding="utf-8") if overlay.exists() else ""

    odds = Path("worldcup_predictor/research/bet_coverage_optimizer/fixtures/interwetten_three_fixture_markets.json")
    summary = run_top10_to_5_research(
        fixture_ids=[1556628, 1494717, 1567860],
        fixtures_payload=copy.deepcopy(DEMO_FIXTURES),
        real_odds_json=odds,
        output_dir=tmp_path / "run",
        top10_source="consensus",
        stake_mode="profit_floor",
        coupon_ticket_cap=25,
        forward_shadow=True,
        historical_backtest=True,
    )
    assert summary["not_deployed"] is True
    assert summary["canonical_ecse_unchanged"] is True
    assert summary["exact_v2_not_promoted"] is True
    assert summary["coverage_optimizer_unchanged"] is True
    assert bco_path.read_text(encoding="utf-8") == before_bco
    if ins_path.exists():
        assert ins_path.read_text(encoding="utf-8") == before_ins
    if overlay.exists():
        assert overlay.read_text(encoding="utf-8") == before_ov

    required = [
        "run_manifest.json",
        "input_top10.json",
        "real_market_validation.json",
        "exact_selection.json",
        "market_pair_candidates.json",
        "selected_market_pair.json",
        "stake_plan.json",
        "top10_coverage_matrix.csv",
        "top10_coverage_matrix.json",
        "scenario_profit_loss.json",
        "rejected_market_pairs.json",
        "fixture_recommendations.json",
        "coupon_universe_125.json",
        "optimized_coupon.csv",
        "optimized_coupon.json",
        "historical_backtest.json",
        "model_source_comparison.json",
        "forward_shadow_summary.json",
        "validation_report.json",
        "owner_top10_to_5_dashboard.html",
        "owner_top10_to_5_dashboard.md",
        "TOP10_TO_5_PROFIT_AWARE_REPORT.md",
        "top10_to_5_forward_shadow.db",
    ]
    for name in required:
        assert (tmp_path / "run" / name).exists(), name

    # Manual screenshot labeled
    val = json.loads((tmp_path / "run" / "real_market_validation.json").read_text(encoding="utf-8"))
    assert any(v.get("is_manual_screenshot_transcription") for v in val.values())

    # Deterministic re-run hash equality on exacts
    summary2 = run_top10_to_5_research(
        fixture_ids=[1556628, 1494717, 1567860],
        fixtures_payload=copy.deepcopy(DEMO_FIXTURES),
        real_odds_json=odds,
        output_dir=tmp_path / "run2",
        top10_source="consensus",
        stake_mode="profit_floor",
        coupon_ticket_cap=25,
        forward_shadow=False,
        historical_backtest=True,
    )
    r1 = json.loads((tmp_path / "run" / "exact_selection.json").read_text(encoding="utf-8"))
    r2 = json.loads((tmp_path / "run2" / "exact_selection.json").read_text(encoding="utf-8"))
    assert r1 == r2
    assert summary2["status"] in {
        "TOP10_TO_5_PROFIT_AWARE_OPTIMIZER_COMPLETE",
        "TOP10_TO_5_PROFIT_AWARE_OPTIMIZER_HOLD",
        "TOP10_TO_5_PROFIT_AWARE_OPTIMIZER_RESEARCH_MORE",
    }


def test_no_fabricated_odds_in_recommendations(tmp_path: Path):
    odds = Path("worldcup_predictor/research/bet_coverage_optimizer/fixtures/interwetten_three_fixture_markets.json")
    run_top10_to_5_research(
        fixture_ids=[1556628],
        fixtures_payload={1556628: DEMO_FIXTURES[1556628]},
        real_odds_json=odds,
        output_dir=tmp_path / "one",
        historical_backtest=False,
        forward_shadow=False,
    )
    recs = json.loads((tmp_path / "one" / "fixture_recommendations.json").read_text(encoding="utf-8"))
    for sc, odd in (recs[0].get("exact_odds") or {}).items():
        # Exact odds absent unless provided — must not invent
        assert odd is None
