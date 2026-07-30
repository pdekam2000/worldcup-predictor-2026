"""Unit tests for market settlement mapping."""

from __future__ import annotations

import pytest

from worldcup_predictor.research.bet_coverage_optimizer.score_mapping import settles_as_win


@pytest.mark.parametrize(
    "hg,ag,side,expected",
    [
        (1, 0, "1x", True),
        (1, 1, "1x", True),
        (0, 1, "1x", False),
        (0, 1, "x2", True),
        (1, 1, "x2", True),
        (1, 0, "x2", False),
        (1, 0, "12", True),
        (0, 1, "12", True),
        (1, 1, "12", False),
    ],
)
def test_double_chance_boundaries(hg, ag, side, expected):
    assert settles_as_win("double_chance", {"side": side}, hg, ag) is expected


@pytest.mark.parametrize(
    "hg,ag,direction,line,expected",
    [
        (1, 1, "under", 2.5, True),
        (2, 1, "under", 2.5, False),
        (2, 1, "over", 2.5, True),
        (1, 1, "over", 2.5, False),
        (2, 2, "under", 4.5, True),
        (3, 2, "under", 4.5, False),
        (2, 2, "under", 4.0, "unsupported"),  # push on whole line
    ],
)
def test_over_under_boundaries(hg, ag, direction, line, expected):
    assert settles_as_win("over_under", {"direction": direction, "line": line}, hg, ag) is expected


@pytest.mark.parametrize(
    "hg,ag,side,expected",
    [
        (1, 1, "yes", True),
        (1, 0, "yes", False),
        (1, 0, "no", True),
        (2, 1, "no", False),
    ],
)
def test_btts(hg, ag, side, expected):
    assert settles_as_win("btts", {"side": side}, hg, ag) is expected


@pytest.mark.parametrize(
    "hg,ag,expected",
    [
        (0, 1, True),
        (0, 2, True),
        (0, 3, True),
        (1, 2, True),
        (1, 3, True),
        (1, 1, False),
        (2, 2, False),
        (0, 0, False),
        (2, 0, False),
        (1, 4, False),  # over 4.5 total? 5 goals → under 4.5 false; away win true but OU fails
    ],
)
def test_rangers_win_under_4_5(hg, ag, expected):
    assert (
        settles_as_win(
            "result_total",
            {"result": "away", "direction": "under", "line": 4.5},
            hg,
            ag,
        )
        is expected
    )


def test_dc_total_x2_under_4_5():
    assert settles_as_win("dc_total", {"side": "x2", "direction": "under", "line": 4.5}, 0, 1) is True
    assert settles_as_win("dc_total", {"side": "x2", "direction": "under", "line": 4.5}, 1, 1) is True
    assert settles_as_win("dc_total", {"side": "x2", "direction": "under", "line": 4.5}, 3, 2) is False
    assert settles_as_win("dc_total", {"side": "x2", "direction": "under", "line": 4.5}, 2, 0) is False


def test_team_total_and_win_to_nil():
    assert settles_as_win("team_total", {"team": "home", "direction": "over", "line": 2.5}, 3, 0) is True
    assert settles_as_win("team_total", {"team": "home", "direction": "over", "line": 2.5}, 2, 0) is False
    assert settles_as_win("win_to_nil", {"team": "home"}, 2, 0) is True
    assert settles_as_win("win_to_nil", {"team": "home"}, 2, 1) is False


def test_goal_parity_and_exact_team_goals():
    assert settles_as_win("goal_parity", {"parity": "odd"}, 1, 0) is True
    assert settles_as_win("goal_parity", {"parity": "even"}, 1, 1) is True
    assert settles_as_win("exact_team_goals", {"team": "home", "goals": 2}, 2, 1) is True
    assert settles_as_win("exact_team_goals", {"team": "away", "goals": 0}, 2, 0) is True


def test_winning_margin_boundaries():
    assert settles_as_win("winning_margin", {"selection": "home_by_1"}, 2, 1) is True
    assert settles_as_win("winning_margin", {"selection": "home_by_1"}, 3, 1) is False
    assert settles_as_win("winning_margin", {"selection": "away_3_plus"}, 0, 4) is True
    assert settles_as_win("winning_margin", {"selection": "draw"}, 1, 1) is True


def test_asian_and_european_handicap():
    assert settles_as_win("asian_handicap", {"team": "home", "line": -1.5}, 2, 0) is True
    assert settles_as_win("asian_handicap", {"team": "home", "line": -1.5}, 1, 0) is False
    assert settles_as_win("asian_handicap", {"team": "home", "line": -1.0}, 1, 0) is "unsupported"  # push
    assert settles_as_win("european_handicap", {"team": "home", "line": -1}, 2, 0) is True
    assert settles_as_win("european_handicap", {"team": "home", "line": -1}, 1, 0) is False


def test_unknown_market_unsupported():
    assert settles_as_win("made_up_market", {}, 1, 0) == "unsupported"
