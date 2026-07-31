"""Bet Portfolio Manager research tests."""

from __future__ import annotations

import json
from pathlib import Path

from worldcup_predictor.research.bet_portfolio_manager.capital_allocation import allocate_capital
from worldcup_predictor.research.bet_portfolio_manager.correlation import analyze_diversification
from worldcup_predictor.research.bet_portfolio_manager.daily_score import compute_daily_portfolio_score
from worldcup_predictor.research.bet_portfolio_manager.fixture_ranking import rank_fixtures
from worldcup_predictor.research.bet_portfolio_manager.historical_validation import (
    run_historical_portfolio_validation,
)
from worldcup_predictor.research.bet_portfolio_manager.input_adapter import normalize_fixture
from worldcup_predictor.research.bet_portfolio_manager.no_bet import decide_no_bet
from worldcup_predictor.research.bet_portfolio_manager.pipeline import evaluate_day, run_portfolio_manager


def _raw(i: int, *, league: str = "L1", conf: float = 0.7, ent: float = 2.0, hit: bool = True) -> dict:
    actual = "1-0" if hit else "0-2"
    return {
        "fixture_id": 2000 + i,
        "match_name": f"Match {i}",
        "league": league,
        "kickoff": f"2026-06-{(i % 28) + 1:02d}",
        "confidence": conf,
        "entropy": ent,
        "top5_mass": conf,
        "coverage_ratio_primary": 0.75,
        "coverage_ratio_with_insurance": 0.88,
        "residual_mass": 0.12,
        "incremental_uncovered_mass": 0.10,
        "odds_home": 1.95,
        "main_market_family": "over_under",
        "insurance_market_family": "btts",
        "main_market_label": "Under 3.5",
        "insurance_market_label": "BTTS Yes",
        "insurance_odds": 1.90,
        "exact3": ["1-0", "2-0", "2-1"],
        "main_coverage_scores": ["0-0", "3-0"],
        "insurance_scores": ["1-1"],
        "actual_score": actual,
        "top_n_scores": [
            {"score": "1-0", "probability": 0.18},
            {"score": "2-0", "probability": 0.14},
            {"score": "2-1", "probability": 0.11},
            {"score": "0-0", "probability": 0.10},
            {"score": "1-1", "probability": 0.09},
        ],
    }


def test_normalize_does_not_invent_predictions():
    raw = _raw(1)
    fx = normalize_fixture(raw)
    assert fx["fixture_id"] == 2001
    assert fx["confidence"] == 0.7
    assert "exact3" in fx


def test_daily_score_deterministic():
    rows = [normalize_fixture(_raw(i)) for i in range(3)]
    a = compute_daily_portfolio_score(rows)
    b = compute_daily_portfolio_score(rows)
    assert a == b
    assert a["grade"] in {"S", "A", "B", "C", "D", "F"}
    assert a["recommendation"] in {"BET", "SMALL BET", "WATCH", "SKIP"}
    assert a["predictions_unchanged"] is True


def test_no_bet_can_skip_bad_days():
    rows = [normalize_fixture(_raw(i, conf=0.2, ent=3.5, hit=False)) for i in range(4)]
    daily = compute_daily_portfolio_score(rows)
    ranking = rank_fixtures(rows)
    div = analyze_diversification(rows)
    decision = decide_no_bet(daily, ranking, div)
    assert decision["action"] in {"WATCH", "SKIP", "SMALL BET", "BET"}
    # low quality should not be strong BET
    assert not (decision["action"] == "BET" and daily["daily_portfolio_score"] < 70)


def test_capital_allocation_respects_caps():
    rows = [normalize_fixture(_raw(i)) for i in range(3)]
    ranking = rank_fixtures(rows)
    selected = ranking["rankings"][:2]
    by_id = {int(r["fixture_id"]): r for r in rows}
    # attach ids on ranking rows already
    alloc = allocate_capital(bankroll=100.0, selected=selected, fixtures_by_id=by_id, mode="equal")
    assert alloc["allocated_eur"] <= 100.0 * 0.60 + 1e-6
    for a in alloc["allocations"]:
        assert a["stake_eur"] <= 100.0 * 0.35 + 1e-6


def test_historical_managed_can_skip():
    fixtures = []
    for i in range(90):
        # alternate good and bad days via kickoff grouping of 3
        good = (i // 3) % 2 == 0
        fixtures.append(
            _raw(
                i,
                league="A" if i % 2 == 0 else "B",
                conf=0.75 if good else 0.25,
                ent=1.9 if good else 3.4,
                hit=good,
            )
        )
    hv = run_historical_portfolio_validation(fixtures, bankroll=1000.0, mode="score_weighted")
    assert hv["n_days"] >= 20
    assert "roi" in hv["always_bet"]
    assert "roi" in hv["portfolio_managed"]
    assert hv["portfolio_managed"]["skipped_days"] >= 0
    assert "grade_distribution" in hv["portfolio_managed"]


def test_evaluate_day_end_to_end():
    raw = [_raw(i) for i in range(3)]
    ev = evaluate_day(raw, bankroll=250.0, mode="score_weighted")
    assert "daily" in ev and "decision" in ev and "allocation" in ev
    assert ev["daily"]["predictions_unchanged"] is True


def test_pipeline_smoke(tmp_path: Path):
    # Prefer fast synthetic fixtures to keep CI light; still exercises full writer path
    fixtures = [_raw(i, conf=0.7 if i % 5 else 0.3, ent=2.0 if i % 5 else 3.3, hit=bool(i % 5)) for i in range(120)]
    result = run_portfolio_manager(
        bankroll=500.0,
        mode="score_weighted",
        fixtures=fixtures,
        output_dir=tmp_path / "bpm",
    )
    assert result["status"] == "BET_PORTFOLIO_MANAGER_RESEARCH_COMPLETE"
    out = Path(result["output_dir"])
    for name in (
        "portfolio_score.json",
        "fixture_portfolio_ranking.json",
        "capital_allocation.json",
        "no_bet_analysis.json",
        "diversification_report.json",
        "portfolio_risk.json",
        "historical_portfolio_validation.json",
        "forward_portfolio_shadow.json",
        "owner_portfolio_dashboard.html",
        "owner_portfolio_dashboard.md",
        "validation_report.json",
    ):
        assert (out / name).exists(), name
    hist = json.loads((out / "historical_portfolio_validation.json").read_text(encoding="utf-8"))
    assert "improvement" in hist
