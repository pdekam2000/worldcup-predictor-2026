"""Regression tests for Phase 5 report ranking/decision display fixes."""

from __future__ import annotations

import math

from worldcup_predictor.research.ecse_score_distribution import generate_score_distribution
from worldcup_predictor.research.football_strength_foundation.score_v2 import dist_dc
from worldcup_predictor.research.infra_l2f_forward.research_preview import (
    CANONICAL_ECSE_RANKING_FIELD,
    EXACT_V2_RANKING_FIELD,
    _canonical_poisson_dist,
    _tops_from_ranked_entries,
    _tops_with_probs,
    build_top_comparison,
)


def test_canonical_poisson_not_dixon_coles_for_same_lambdas():
    lh, la = 0.485341, 1.712969
    poisson = generate_score_distribution(lh, la, use_dixon_coles=False)
    dc = dist_dc(lh, la)
    # For Dundee-like lambdas, Top1 differs across ranking fields.
    assert poisson[0]["scoreline"] == "0-1"
    assert dc[0]["scoreline"] == "0-2"
    assert poisson[0]["scoreline"] != dc[0]["scoreline"]


def test_canonical_tops_descending_on_ranking_field():
    lh, la = 0.485341, 1.712969
    dist = _canonical_poisson_dist(lh, la)
    tops = _tops_from_ranked_entries(dist, 5)
    probs = [float(t["probability"]) for t in tops]
    assert probs == sorted(probs, reverse=True)
    assert tops[0]["ranking_field"] == CANONICAL_ECSE_RANKING_FIELD
    # Displayed probability corresponds to same score row (no cross-join).
    pmap = {e["scoreline"]: e["probability"] for e in dist}
    for t in tops:
        assert math.isclose(t["probability"], pmap[t["score"]], rel_tol=0, abs_tol=1e-6)


def test_cross_join_dc_onto_poisson_ranks_is_inconsistent():
    """Documents the Phase 5 bug: DC probs on Poisson order are not descending."""
    lh, la = 1.045087, 0.874073
    poisson = generate_score_distribution(lh, la, use_dixon_coles=False)
    dc = dist_dc(lh, la)
    dc_map = {e["scoreline"]: float(e["probability"]) for e in dc if e["scoreline"] != "OTHER"}
    joined = [dc_map[e["scoreline"]] for e in poisson[:5]]
    assert joined != sorted(joined, reverse=True)


def test_exact_v2_tops_use_dc_ranking_field():
    lh, la = 0.695, 2.452
    tops = _tops_with_probs(dist_dc(lh, la), 5)
    probs = [float(t["probability"]) for t in tops]
    assert probs == sorted(probs, reverse=True)
    assert tops[0]["ranking_field"] == EXACT_V2_RANKING_FIELD


def test_wde_argmax_helper():
    from worldcup_predictor.gpt_actions.bridge_semantics import extract_wde_semantics

    sem = extract_wde_semantics(
        {
            "prediction": "draw",
            "no_bet": True,
            "probabilities": {"home_win": 25.8, "draw": 25.6, "away_win": 48.6},
            "detailed_markets": {
                "match_winner": {
                    "selection": "draw",
                    "probabilities": {"home_win": 25.8, "draw": 25.6, "away_win": 48.6},
                }
            },
        }
    )
    assert sem["probability_argmax"] == "away_win"
    assert sem["decision_pick"] == "draw"


def test_top_comparison_preserves_row_pairing():
    c = [
        {"score": "0-1", "probability": 0.190},
        {"score": "0-2", "probability": 0.163},
        {"score": "0-0", "probability": 0.111},
    ]
    e = [
        {"score": "0-2", "probability": 0.129},
        {"score": "0-3", "probability": 0.106},
        {"score": "1-2", "probability": 0.090},
    ]
    cmp = build_top_comparison(c, e)
    assert cmp["side_by_side"][0]["canonical_score"] == "0-1"
    assert cmp["side_by_side"][0]["canonical_probability"] == 0.190
    assert cmp["side_by_side"][0]["exact_v2_score"] == "0-2"
    assert cmp["top1_agreement"] is False
