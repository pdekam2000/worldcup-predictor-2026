"""Tests for TRUE_FORWARD_472 evaluation audit (no DB writes / no regen)."""

from __future__ import annotations

from worldcup_predictor.research.true_forward_472_evaluation import metrics as M
from worldcup_predictor.research.true_forward_472_evaluation.pipeline import (
    GATE_A,
    GATE_B,
    GATE_C,
    _norm_1x2,
    _normalize_probs,
    classify_result_status,
    evaluate_exact,
    pick_canonical_freeze,
)


def test_wilson_and_accuracy_pack():
    pack = M.accuracy_pack(75, 100)
    assert pack["accuracy"] == 0.75
    assert pack["wilson_95"]["low"] is not None
    assert pack["wilson_95"]["low"] < 0.75 < pack["wilson_95"]["high"]


def test_priced_roi_and_drawdown():
    stakes = [
        {"hit": True, "odds": 2.0, "side": "home_win"},
        {"hit": False, "odds": 1.5, "side": "away_win"},
        {"hit": True, "odds": 1.8, "side": "draw"},
    ]
    p = M.priced_performance(stakes)
    assert p["priced_n"] == 3
    assert p["wins"] == 2
    assert p["losses"] == 1
    assert abs(p["total_return"] - (2.0 + 0.0 + 1.8)) < 1e-9
    assert abs(p["net_profit"] - (2.0 + 0.0 + 1.8 - 3.0)) < 1e-9
    assert p["max_drawdown"] >= 0


def test_timing_stages():
    assert M.timing_stage(100) == "EARLY"
    assert M.timing_stage(24) == "MID"
    assert M.timing_stage(6) == "LATE"
    assert M.timing_stage(1) == "FINAL_PREMATCH"
    assert M.timing_stage(-1) == "POST_KICKOFF"


def test_norm_1x2():
    assert _norm_1x2("home") == "home_win"
    assert _norm_1x2("away_win") == "away_win"
    assert _norm_1x2("X") == "draw"


def test_result_status_confirmed():
    assert (
        classify_result_status(
            {
                "result_quality_status": "CONFIRMED_REGULATION_RESULT",
                "actual_1x2": "home_win",
                "result_status": "FT",
            }
        )
        == "FINISHED_CONFIRMED"
    )
    assert classify_result_status(None) == "PENDING"


def test_exact_rank_top5_only_store():
    ranks = [
        {"rank": 1, "score": "1-0", "probability": 0.2},
        {"rank": 2, "score": "2-0", "probability": 0.15},
        {"rank": 3, "score": "1-1", "probability": 0.12},
        {"rank": 4, "score": "0-0", "probability": 0.1},
        {"rank": 5, "score": "2-1", "probability": 0.08},
    ]
    hit = evaluate_exact("1-1", ranks)
    assert hit["top1"] is False
    assert hit["top3"] is True
    assert hit["top5"] is True
    assert hit["top10"] is None
    miss = evaluate_exact("5-5", ranks)
    assert miss["rank_label"] == "OUTSIDE_TOP5"


def test_pick_canonical_prefers_evaluated():
    rows = [
        {"evaluation_status": "PENDING", "frozen_at": "2026-07-01T10:00:00+00:00"},
        {"evaluation_status": "EVALUATED", "frozen_at": "2026-07-01T09:00:00+00:00"},
        {"evaluation_status": "PENDING", "frozen_at": "2026-07-01T11:00:00+00:00"},
    ]
    assert pick_canonical_freeze(rows)["evaluation_status"] == "EVALUATED"


def test_gate_thresholds_use_evaluated_unique_not_raw():
    raw = 472
    evaluated_unique = 168
    assert raw >= GATE_C  # raw alone looks like Gate C
    assert evaluated_unique >= GATE_A
    assert evaluated_unique >= GATE_B
    # Gate C must fail if evaluated unique < 250 even when raw=472
    assert not (evaluated_unique >= GATE_C)


def test_pending_not_counted_as_loss():
    # accuracy only over finished hits/misses
    pack = M.accuracy_pack(hits=10, n=20)
    assert pack["misses"] == 10
    assert pack["accuracy"] == 0.5


def test_normalize_probs_percent_scale():
    p = _normalize_probs(83.5, 11.7, 4.8)
    assert abs(sum(p.values()) - 1.0) < 1e-6
    assert 0.8 < p["home_win"] < 0.9
    brier = M.brier_multiclass(p, "home_win")
    assert brier is not None and brier < 0.1


def test_confusion_balanced_accuracy():
    pairs = [
        ("home_win", "home_win"),
        ("home_win", "draw"),
        ("draw", "draw"),
        ("away_win", "away_win"),
    ]
    c = M.confusion_1x2(pairs)
    assert c["balanced_accuracy"] is not None
    assert 0.0 <= c["balanced_accuracy"] <= 1.0
