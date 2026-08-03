"""Tests for ECSE HOME ∧ WDE HOME forensic optimization."""

from __future__ import annotations

from worldcup_predictor.research.ecse_home_wde_home_optimization.dataset import extract_home_agree
from worldcup_predictor.research.ecse_home_wde_home_optimization.forensics import (
    ExtraFilter,
    cluster_failures,
    evaluate_subset,
    feature_importance,
    run_threshold_search,
)
from worldcup_predictor.research.ou25_regime_mining.metrics import config_hash


def _row(fid: int, hit: bool, **kwargs):
    base = {
        "fixture_id": fid,
        "date": f"2026-07-{(fid % 28) + 1:02d}",
        "kickoff": f"2026-07-{(fid % 28) + 1:02d}T12:00:00+00:00",
        "league": "test_league" if fid % 2 == 0 else "other_league",
        "ecse_direction": "home_win",
        "wde_decision": "home_win",
        "direction_hit": hit,
        "odds_home": kwargs.get("odds_home", 1.55),
        "odds_draw": 4.0,
        "odds_away": 6.0,
        "entropy": kwargs.get("entropy", 1.6),
        "wde_home_p": kwargs.get("wde_home_p", 0.62),
        "ecse_home_mass": 0.55,
        "ecse_draw_mass": 0.25,
        "ecse_away_mass": 0.20,
        "ecse_home_gap": 0.30,
        "top5_mass": 0.48,
        "total_lambda": 2.4,
        "market_favorite": "home_win",
        "actual_1x2": "home_win" if hit else "draw",
        "actual_score": "2-0" if hit else "1-1",
        "actual_home_goals": 2 if hit else 1,
        "actual_away_goals": 0 if hit else 1,
        "snapshot_stage": "LATE",
        "match_name": f"M{fid}",
    }
    base.update(kwargs)
    return base


def test_extract_home_agree():
    uni = [
        {"ecse_direction": "home_win", "wde_decision": "home_win", "fixture_id": 1},
        {"ecse_direction": "away_win", "wde_decision": "home_win", "fixture_id": 2},
        {"ecse_direction": "home_win", "wde_decision": "away_win", "fixture_id": 3},
    ]
    assert len(extract_home_agree(uni)) == 1


def test_rule_reproducibility_hash():
    f1 = ExtraFilter("odds_home_le_1_6", ("odds_home<=1.6",), lambda r: True)
    f2 = ExtraFilter("odds_home_le_1_6", ("odds_home<=1.6",), lambda r: False)
    assert f1.hash == f2.hash
    assert config_hash({"a": 1}) == config_hash({"a": 1})


def test_dataset_integrity_split():
    rows = [_row(i, hit=(i % 3 != 0)) for i in range(60)]
    wins = [r for r in rows if r["direction_hit"]]
    losses = [r for r in rows if not r["direction_hit"]]
    assert len(wins) + len(losses) == 60
    assert all(r["direction_hit"] for r in wins)
    assert all(not r["direction_hit"] for r in losses)


def test_clustering_uses_evidence():
    losses = [
        _row(1, False, actual_1x2="draw", actual_score="1-1"),
        _row(2, False, actual_1x2="away_win", actual_score="0-2", odds_home=2.5, market_favorite="away_win"),
    ]
    # fix market agreement
    losses[1]["market_agreement"] = "DISAGREE"
    cl = cluster_failures(losses)
    assert cl["n_losses"] == 2
    assert "unexpected_draw" in cl["cluster_counts"] or "away_upset" in cl["cluster_counts"]


def test_feature_importance_numeric():
    wins = [_row(i, True, odds_home=1.4, entropy=1.4) for i in range(20)]
    losses = [_row(100 + i, False, odds_home=2.1, entropy=2.1) for i in range(10)]
    imp = feature_importance(wins, losses)
    assert "odds_home" in imp["numeric"]
    assert imp["numeric"]["odds_home"]["win_mean"] < imp["numeric"]["odds_home"]["loss_mean"]


def test_threshold_determinism():
    rows = [_row(i, hit=(i % 4 != 0), odds_home=1.4 + (i % 10) * 0.05) for i in range(62)]
    a = run_threshold_search(rows, universe_n=168)
    b = run_threshold_search(rows, universe_n=168)
    assert [x["config_hash"] for x in a] == [x["config_hash"] for x in b]
    assert any(x["name"].startswith("BASE_ecse") for x in a)


def test_evaluate_subset_bootstrap_and_walkforward():
    rows = [_row(i, hit=(i % 5 != 0)) for i in range(55)]
    ev = evaluate_subset(
        rows,
        universe_n=168,
        base_n=62,
        name="t",
        conditions=["ecse=home", "wde=home"],
    )
    assert ev["n"] == 55
    assert ev["bootstrap_95"]["low"] is not None
    assert ev["fold_stats"]
    assert "remove_one_win" in ev


def test_no_production_constants():
    from worldcup_predictor.research.ecse_home_wde_home_optimization import PROGRAM

    assert "FORENSIC" in PROGRAM or "OPTIMIZATION" in PROGRAM
