"""Invariant tests for high-score tail shadow distributions."""

from __future__ import annotations

from worldcup_predictor.research.ecse_score_distribution import OTHER_SCORELINE, generate_score_distribution
from worldcup_predictor.research.ecse_tail_forensics.distributions import topn
from worldcup_predictor.research.high_score_tail_shadow.distributions import (
    dist_dynamic_grid,
    dist_low_score_specialist,
    dist_high_score_specialist,
    dynamic_max_goals,
    other_mass,
    tail_mass,
)
from worldcup_predictor.research.high_score_tail_shadow.regime_selector import select_regime
from worldcup_predictor.research.high_score_tail_shadow.constants import REGIME_HIGH, REGIME_LOW


def _sum_probs(dist) -> float:
    return sum(float(e["probability"]) for e in dist)


def test_probability_sum_after_generation():
    dist = generate_score_distribution(2.5, 1.2, max_goals=7)
    assert abs(_sum_probs(dist) - 1.0) < 1e-6


def test_other_mass_nonnegative():
    dist = generate_score_distribution(3.8, 1.5, max_goals=7)
    assert other_mass(dist) >= 0.0


def test_top5_are_largest_non_other():
    dist = generate_score_distribution(2.0, 1.0, max_goals=7)
    named = [e for e in dist if e["scoreline"] != OTHER_SCORELINE]
    named_sorted = sorted(named, key=lambda e: -float(e["probability"]))
    assert topn(dist, 5) == [e["scoreline"] for e in named_sorted[:5]]


def test_top10_extends_top5():
    dist = generate_score_distribution(2.2, 1.1, max_goals=7)
    t5, t10 = topn(dist, 5), topn(dist, 10)
    assert t10[:5] == t5


def test_no_duplicate_scorelines():
    dist = generate_score_distribution(1.8, 1.4, max_goals=8)
    labels = [e["scoreline"] for e in dist]
    assert len(labels) == len(set(labels))


def test_dynamic_grid_expands_with_expected_goals():
    assert dynamic_max_goals(1.0, 0.8) < dynamic_max_goals(3.0, 1.5)
    d_low = dist_dynamic_grid(1.0, 0.8)
    d_high = dist_dynamic_grid(3.2, 1.4)
    assert other_mass(d_high) <= other_mass(generate_score_distribution(3.2, 1.4, max_goals=7)) + 1e-9
    assert len([e for e in d_high if e["scoreline"] != OTHER_SCORELINE]) >= len(
        [e for e in d_low if e["scoreline"] != OTHER_SCORELINE]
    )


def test_specialists_deterministic():
    a = topn(dist_low_score_specialist(1.5, 1.1), 5)
    b = topn(dist_low_score_specialist(1.5, 1.1), 5)
    assert a == b
    c = topn(dist_high_score_specialist(2.8, 1.2, ou_prediction="over_2_5"), 5)
    d = topn(dist_high_score_specialist(2.8, 1.2, ou_prediction="over_2_5"), 5)
    assert c == d


def test_regime_selector_prematch_only():
    high = select_regime(lambda_home=2.2, lambda_away=1.2, ou_prediction="over_2_5")
    low = select_regime(lambda_home=0.9, lambda_away=0.8, ou_prediction="under_2_5")
    assert high["regime"] == REGIME_HIGH
    assert low["regime"] == REGIME_LOW
    assert high["rewrites_canonical"] is False


def test_tail_mass_increases_for_higher_lambda():
    low = tail_mass(generate_score_distribution(1.0, 0.8, max_goals=10), 4)
    high = tail_mass(generate_score_distribution(2.8, 1.5, max_goals=10), 4)
    assert high > low
