"""Unit tests for favorite-orientation normalization."""

from worldcup_predictor.research.ecse_market_prior.probability_space import (
    favorite_result,
    normalize_favorite_score,
    reorient_score_to_home_away,
    winning_margin,
)


def test_home_favorite_2_0():
    assert normalize_favorite_score(2, 0, "HOME") == "2-0"


def test_away_favorite_actual_0_2():
    assert normalize_favorite_score(0, 2, "AWAY") == "2-0"


def test_away_favorite_actual_1_2():
    assert normalize_favorite_score(1, 2, "AWAY") == "2-1"


def test_reorient_back_to_home_away():
    assert reorient_score_to_home_away("2-0", "AWAY") == "0-2"
    assert reorient_score_to_home_away("2-1", "HOME") == "2-1"


def test_favorite_result():
    assert favorite_result(2, 0, "HOME") == "WIN"
    assert favorite_result(1, 1, "HOME") == "DRAW"
    assert favorite_result(0, 2, "HOME") == "LOSS"


def test_winning_margin():
    assert winning_margin(2, 0, "HOME") == 2
    assert winning_margin(0, 2, "AWAY") == 2
