"""Tests for Tier B competition normalization."""

from __future__ import annotations

import pytest

from worldcup_predictor.gpt_actions.competition_normalize import (
    is_friendly_competition,
    is_tier_b_shadow,
    normalize_competition_key,
)
from worldcup_predictor.gpt_actions.tier_b_shadow_registry import TIER_B_SHADOW_DOMAINS


@pytest.mark.parametrize(
    "league_id,canonical",
    [
        (113, "allsvenskan"),
        (114, "superettan"),
        (362, "a_lyga"),
        (361, "one_lyga"),
        (365, "virsliga"),
        (164, "urvalsdeild"),
        (165, "one_deild"),
        (103, "eliteserien"),
        (244, "veikkausliiga"),
        (140, "la_liga"),
        (135, "serie_a"),
        (61, "ligue_1"),
    ],
)
def test_league_id_normalization(league_id: int, canonical: str) -> None:
    assert normalize_competition_key(f"league_{league_id}") == canonical
    assert is_tier_b_shadow(f"league_{league_id}") is True


def test_exactly_twelve_tier_b_domains() -> None:
    assert len(TIER_B_SHADOW_DOMAINS) == 12


def test_friendlies_blocked() -> None:
    assert is_friendly_competition("league_667") is True
    assert is_tier_b_shadow("league_667") is False


def test_unrelated_league_not_normalized() -> None:
    assert normalize_competition_key("league_999") == "league_999"
    assert is_tier_b_shadow("league_999") is False
