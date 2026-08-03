"""Tests for next-15 strongest 1X2 selection scoring."""

from __future__ import annotations

from worldcup_predictor.research.next_15_strongest_1x2.select import score_candidate, select_top15


def _pred(**kwargs):
    base = {
        "fixture_id": kwargs.get("fixture_id", 1),
        "home_team": "Home",
        "away_team": "Away",
        "league": "Test",
        "league_country": "X",
        "kickoff_utc": "2026-08-10T18:00:00+00:00",
        "kickoff_vienna": "2026-08-10 20:00 CEST",
        "odds": {"home": 1.7, "draw": 3.8, "away": 4.5, "complete": True, "freshness_status": "ODDS_FRESH"},
        "wde": {
            "decision": kwargs.get("wde", "home_win"),
            "home_probability": 60,
            "draw_probability": 22,
            "away_probability": 18,
            "confidence": kwargs.get("conf", 60),
        },
        "ecse": {
            "direction": kwargs.get("ecse", "home"),
            "top5_mass": kwargs.get("t5", 0.55),
            "entropy": kwargs.get("ent", 1.5),
            "lambda_home": 1.8,
            "lambda_away": 0.9,
            "top5": [{"score": "1-0", "probability": 0.2}, {"score": "2-0", "probability": 0.15}],
        },
        "btts": {"prediction": "no"},
        "ou25": {"prediction": "under_2_5"},
        "no_bet": kwargs.get("no_bet", False),
        "main_risk": kwargs.get("risk"),
        "prediction_complete": True,
        "data_quality": "HIGH",
    }
    return base


def test_home_home_outranks_conflict():
    a = score_candidate(_pred(fixture_id=1, wde="home_win", ecse="home", conf=55))
    b = score_candidate(_pred(fixture_id=2, wde="home_win", ecse="away", conf=80))
    assert a["tier_priority"] == 1
    assert b["tier_priority"] > a["tier_priority"]
    assert a["research_score"] > b["research_score"]


def test_no_bet_not_rejected():
    r = score_candidate(_pred(no_bet=True, wde="home_win", ecse="home", conf=60))
    assert r["classification"] in {"STRONG", "MEDIUM", "WATCHLIST", "AVOID"}
    assert r["no_bet"] is True


def test_select_top15_length():
    scored = [
        score_candidate(_pred(fixture_id=i, wde="home_win", ecse="home", conf=50 + i))
        for i in range(20)
    ]
    top = select_top15(scored)
    assert len(top) == 15
    assert top[0]["rank"] == 1
