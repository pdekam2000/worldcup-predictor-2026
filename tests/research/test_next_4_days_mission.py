"""Smoke tests for next-4-days mission helpers (no production writes)."""

from __future__ import annotations

from scripts.run_next_4_days_complete_prediction_scan import (
    DEFAULT_DATES,
    classify_mission_agreement,
    side_by_side_top10,
)


def test_default_dates_are_aug_1_to_4():
    assert DEFAULT_DATES == ["2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04"]


def test_side_by_side_ten_rows():
    ecse = {"scores": [{"rank": i, "score": f"{i}-0", "probability": 0.1} for i in range(1, 11)]}
    rows = side_by_side_top10(ecse, [], [])
    assert len(rows) == 10
    assert rows[0]["canonical_ecse"] == "1-0"


def test_agreement_tags_transparent():
    p = {
        "wde": {"decision": "home", "execution_status": "OK"},
        "ecse": {"entropy": 1.5, "total_lambda": 2.0},
        "no_bet": False,
        "consensus": "HIGH_AGREEMENT",
    }
    ecse10 = {
        "scores": [{"score": "1-0"}, {"score": "2-0"}, {"score": "2-1"}],
        "full_mass_1x2": {"home": 0.6, "draw": 0.2, "away": 0.1},
        "tail_4plus_mass": 0.05,
        "lambda_total": 2.0,
    }
    ev = {"dna": {"top5": ["1-0", "2-0", "0-0"], "avg_goals": 2.1}, "exact_v2_top10": []}
    ag = classify_mission_agreement(p, ecse10, ev)
    assert ag["portfolio_similarity_ood_used_for_selection"] is False
    assert "primary" in ag
