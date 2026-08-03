"""Tests for O/U 2.5 regime mining (read-only research)."""

from __future__ import annotations

from worldcup_predictor.research.ou25_regime_mining.ledger import ecse_ou_features
from worldcup_predictor.research.ou25_regime_mining.metrics import (
    config_hash,
    goals_to_ou,
    lambda_bucket,
    norm_ou,
    priced_performance,
    prob_bucket,
    remove_one_win_sensitivity,
)
from worldcup_predictor.research.ou25_regime_mining.mining import (
    Rule,
    evaluate_rule,
    leaderboard,
    raw_split,
    walk_forward,
)


def test_ou_settlement():
    assert goals_to_ou(2, 1) == "over_2_5"
    assert goals_to_ou(1, 1) == "under_2_5"
    assert norm_ou("over_25") == "over_2_5"
    assert norm_ou("under") == "under_2_5"


def test_over_under_denominator_separation():
    rows = [
        {"selected_side": "over_2_5", "hit": True, "confidence": 0.6, "ou_odds_class": "UNPRICED"},
        {"selected_side": "over_2_5", "hit": False, "confidence": 0.55, "ou_odds_class": "UNPRICED"},
        {"selected_side": "under_2_5", "hit": True, "confidence": 0.7, "ou_odds_class": "UNPRICED"},
    ]
    split = raw_split(rows)
    assert split["over_only"]["n"] == 2
    assert split["under_only"]["n"] == 1
    assert split["all"]["n"] == 3


def test_lambda_and_prob_buckets():
    assert lambda_bucket(1.5) == "<1.6"
    assert lambda_bucket(2.7) == "2.5-2.79"
    assert lambda_bucket(3.6) == ">=3.6"
    assert prob_bucket(0.62) == "60-64.99%"
    assert prob_bucket(72) == "70-74.99%"


def test_ecse_over_under_mass():
    ranks = [
        {"rank": 1, "score": "2-1", "probability": 0.2},
        {"rank": 2, "score": "1-1", "probability": 0.15},
        {"rank": 3, "score": "2-0", "probability": 0.12},
        {"rank": 4, "score": "0-0", "probability": 0.1},
        {"rank": 5, "score": "3-1", "probability": 0.08},
    ]
    feat = ecse_ou_features(ranks)
    # totals: 3,2,2,0,4 → over(>2)=2, under=3
    assert feat["top5_over_count"] == 2
    assert feat["top5_under_count"] == 3
    assert feat["top5_majority"] == "under"


def test_chrono_walk_forward_order():
    rows = [
        {"fixture_id": 3, "kickoff": "2026-07-03T12:00:00+00:00"},
        {"fixture_id": 1, "kickoff": "2026-07-01T12:00:00+00:00"},
        {"fixture_id": 2, "kickoff": "2026-07-02T12:00:00+00:00"},
        {"fixture_id": 4, "kickoff": "2026-07-04T12:00:00+00:00"},
        {"fixture_id": 5, "kickoff": "2026-07-05T12:00:00+00:00"},
        {"fixture_id": 6, "kickoff": "2026-07-06T12:00:00+00:00"},
    ]
    folds = walk_forward(rows, 3)
    assert len(folds) == 3
    assert folds[0][0]["fixture_id"] == 1


def test_rule_determinism_and_dedup_hash():
    r1 = Rule("over_2_5", "x", ("a",), lambda r: True)
    r2 = Rule("over_2_5", "x", ("a",), lambda r: False)
    assert r1.hash == r2.hash
    assert config_hash({"a": 1, "b": 2}) == config_hash({"b": 2, "a": 1})


def test_sample_size_gates():
    results = [
        {"n": 12, "accuracy": 0.9, "coverage": 0.1, "name": "tiny"},
        {"n": 40, "accuracy": 0.7, "coverage": 0.2, "name": "ok"},
    ]
    assert len(leaderboard(results, 30)) == 1
    assert leaderboard(results, 30)[0]["name"] == "ok"


def test_priced_unpriced_separation():
    rows = [
        {
            "selected_side": "over_2_5",
            "hit": True,
            "confidence": 0.6,
            "ou_odds_class": "OFFICIAL_PRICED",
            "ou_odds_over": 1.9,
            "ou_odds_under": 2.0,
        },
        {
            "selected_side": "over_2_5",
            "hit": True,
            "confidence": 0.6,
            "ou_odds_class": "UNPRICED",
            "ou_odds_over": None,
            "ou_odds_under": None,
        },
    ]
    split = raw_split(rows)
    assert split["all"]["priced"]["priced_n"] == 1


def test_remove_one_win_sensitivity():
    hits = [True, True, False, False, True]
    sens = remove_one_win_sensitivity(hits)
    assert sens["base_accuracy"] == 0.6
    assert sens["min_after_remove_1"] is not None


def test_evaluate_rule_basic():
    rows = []
    for i in range(40):
        rows.append(
            {
                "fixture_id": i,
                "kickoff": f"2026-07-{(i % 28) + 1:02d}T12:00:00+00:00",
                "selected_side": "under_2_5",
                "under_probability": 0.7,
                "total_lambda": 2.0,
                "hit": i % 3 != 0,
                "ou_odds_class": "UNPRICED",
                "league": "test",
                "top5_under_count": 4,
                "ecse_under_mass_top5": 0.5,
                "btts_prediction": "no",
                "entropy": 1.5,
            }
        )
    rule = Rule(
        "under_2_5",
        "t",
        ("under_probability>=0.65",),
        lambda r: r.get("selected_side") == "under_2_5" and float(r["under_probability"]) >= 0.65,
    )
    ev = evaluate_rule(rule, rows, len(rows))
    assert ev["n"] == 40
    assert ev["config_hash"]
    assert "wilson_95" in ev


def test_roi_unit_stake():
    p = priced_performance([{"hit": True, "odds": 2.0, "side": "over_2_5"}, {"hit": False, "odds": 1.8, "side": "under_2_5"}])
    assert p["priced_n"] == 2
    assert abs(p["net_profit"] - (2.0 + 0.0 - 2.0)) < 1e-9
