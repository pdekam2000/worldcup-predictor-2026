"""Regression: freeze Top5 must backfill probabilities from top10 when top5 omits them."""

from __future__ import annotations

from worldcup_predictor.forward_evaluation.freeze_service import _ecse_rank_rows


def test_backfills_null_top5_probabilities_from_top10():
    ecse = {
        "top_5_scores": [
            {"rank": 1, "scoreline": "1-0", "probability": None},
            {"rank": 2, "scoreline": "0-0", "probability": None},
            {"rank": 3, "scoreline": "1-1", "probability": None},
            {"rank": 4, "scoreline": "0-1", "probability": None},
            {"rank": 5, "scoreline": "2-0", "probability": None},
        ],
        "top_10_scorelines": [
            {"rank": 1, "scoreline": "1-0", "probability": 0.18},
            {"rank": 2, "scoreline": "0-0", "probability": 0.15},
            {"rank": 3, "scoreline": "1-1", "probability": 0.12},
            {"rank": 4, "scoreline": "0-1", "probability": 0.10},
            {"rank": 5, "scoreline": "2-0", "probability": 0.09},
            {"rank": 6, "scoreline": "2-1", "probability": 0.07},
        ],
    }
    rows = _ecse_rank_rows(ecse)
    assert len(rows) == 5
    assert [r["score"] for r in rows] == ["1-0", "0-0", "1-1", "0-1", "2-0"]
    assert [r["probability"] for r in rows] == [0.18, 0.15, 0.12, 0.10, 0.09]


def test_uses_top10_when_top5_missing():
    ecse = {
        "top_10_scorelines": [
            {"rank": 1, "scoreline": "2-1", "probability": 0.11},
            {"rank": 2, "scoreline": "1-1", "probability": 0.10},
            {"rank": 3, "scoreline": "2-0", "probability": 0.09},
            {"rank": 4, "scoreline": "1-0", "probability": 0.08},
            {"rank": 5, "scoreline": "0-0", "probability": 0.07},
        ]
    }
    rows = _ecse_rank_rows(ecse)
    assert len(rows) == 5
    assert rows[0]["score"] == "2-1"
    assert rows[0]["probability"] == 0.11


def test_preserves_existing_top5_probabilities():
    ecse = {
        "top_5_scores": [
            {"rank": 1, "scoreline": "1-0", "probability": 0.20},
            {"rank": 2, "scoreline": "0-0", "probability": 0.16},
            {"rank": 3, "scoreline": "1-1", "probability": 0.12},
            {"rank": 4, "scoreline": "0-1", "probability": 0.09},
            {"rank": 5, "scoreline": "2-0", "probability": 0.08},
        ],
        "top_10_scorelines": [
            {"rank": 1, "scoreline": "1-0", "probability": 0.99},
        ],
    }
    rows = _ecse_rank_rows(ecse)
    assert rows[0]["probability"] == 0.20
