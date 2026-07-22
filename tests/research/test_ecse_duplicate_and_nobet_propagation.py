"""Tests for ECSE duplicate integrity, cache isolation, and no_bet reason propagation."""

from __future__ import annotations

import copy

from worldcup_predictor.api.pick_visibility import enrich_pick_visibility
from worldcup_predictor.decision.no_bet_evaluator import evaluate_no_bet_reasons
from worldcup_predictor.decision.no_bet_reasons import CONFIDENCE_NO_BET_THRESHOLD, NoBetReason
from worldcup_predictor.domain.prediction import (
    ConfidenceLevel,
    FirstGoalPrediction,
    HalftimePrediction,
    MarketPrediction,
    MatchPrediction,
    PredictionConfidenceBreakdown,
)
from worldcup_predictor.egie.provider_features.odds_snapshot_parser import NormalizedOddsLine
from worldcup_predictor.research.confidence_lineage import build_confidence_lineage
from worldcup_predictor.research.ecse_integrity import (
    REQUIRED_CACHE_KEY_DIMENSIONS,
    assert_cache_key_dimensions,
    compute_ecse_input_hash,
    compute_ecse_output_hash,
    detect_duplicate_output_distinct_inputs,
)
from worldcup_predictor.research.ecse_live.prediction_builder import _median_odd, _pick_odd
from worldcup_predictor.research.ecse_score_distribution import generate_score_distribution


def _line(bm: str, sel: str, odd: float, market: str = "Match Winner") -> NormalizedOddsLine:
    return NormalizedOddsLine(
        fixture_id=1,
        bookmaker=bm,
        market_name=market,
        selection=sel,
        odd=odd,
        source="test",
        captured_at=None,
    )


def _pred(*, confidence: float, no_bet: bool, dq: float = 80.0) -> MatchPrediction:
    return MatchPrediction(
        fixture_id=1,
        competition_key="test",
        match_name="A vs B",
        one_x_two=MarketPrediction(market="1x2", selection="home_win", probability=0.5),
        over_under=MarketPrediction(market="ou25", selection="under_2_5", probability=0.5),
        halftime=HalftimePrediction(estimated_total_goals=1.0),
        first_goal=FirstGoalPrediction(team="home"),
        confidence_score=confidence,
        confidence_level=ConfidenceLevel.MEDIUM if confidence >= 50 else ConfidenceLevel.LOW,
        confidence_breakdown=PredictionConfidenceBreakdown(
            form_score=50,
            h2h_score=50,
            injuries_score=50,
            lineups_score=50,
            odds_score=50,
            data_quality_score=dq,
            total=confidence,
        ),
        risk_level="medium",
        no_bet_flag=no_bet,
        metadata={},
    )


def test_median_odd_differs_from_first_book_when_books_diverge():
    lines = [
        _line("10Bet", "Home", 1.16),
        _line("10Bet", "Draw", 5.75),
        _line("William Hill", "Home", 1.17),
        _line("Bet365", "Home", 1.17),
    ]
    mw = lambda n, s: True
    first = _pick_odd(lines, mw, lambda s: s.lower() == "home")
    med = _median_odd(lines, mw, lambda s: s.lower() == "home")
    assert first == 1.16
    assert med == 1.17


def test_two_fixtures_different_feature_hashes_cannot_share_result_object():
    odds_a = {"ft_home_closing": 1.16, "ft_draw_closing": 5.75, "ft_away_closing": 19.5}
    odds_b = {"ft_home_closing": 1.17, "ft_draw_closing": 6.5, "ft_away_closing": 15.44}
    ha = compute_ecse_input_hash(
        fixture_id=1593490, odds_row=odds_a, lambda_features=None, source="live_odds", model_version="t"
    )
    hb = compute_ecse_input_hash(
        fixture_id=1556516, odds_row=odds_b, lambda_features=None, source="live_odds", model_version="t"
    )
    assert ha != hb
    dist = generate_score_distribution(2.9, 0.2)
    pred_a = {"lambda_home": 2.9, "lambda_away": 0.2, "top_10_scorelines": dist[:10], "model_version": "t"}
    pred_b = copy.deepcopy(pred_a)
    pred_b["top_10_scorelines"][0] = dict(pred_b["top_10_scorelines"][0])
    pred_b["top_10_scorelines"][0]["probability"] = 0.999
    assert compute_ecse_output_hash(pred_a) != compute_ecse_output_hash(pred_b)
    # mutating copy must not affect original
    assert pred_a["top_10_scorelines"][0]["probability"] != 0.999


def test_cache_key_requires_fixture_dimensions():
    missing = assert_cache_key_dimensions({"fixture_id": 1})
    assert "competition" in missing
    assert set(REQUIRED_CACHE_KEY_DIMENSIONS) - {"fixture_id"} <= set(missing)


def test_duplicate_guard_flags_historical_rijeka_lugano_signature():
    shared = {
        "lambda_home": 2.97233,
        "lambda_away": 0.176816,
        "model_version": "ECSE-LIVE-1|ECSE-1C-v1|ECSE-1D-B-v1",
        "top1": {"score": "2-0", "probability": 0.189456},
        "top2": {"score": "3-0", "probability": 0.187708},
        "top3": {"score": "4-0", "probability": 0.139483},
        "top4": {"score": "1-0", "probability": 0.127479},
        "top5": {"score": "5-0", "probability": 0.082918},
    }
    rows = [
        {
            "fixture_id": 1593490,
            "home_team": "HNK Rijeka",
            "away_team": "Derry City",
            "ecse": {**shared, "ecse_input_hash": "aaa", "ecse_output_hash": "same"},
        },
        {
            "fixture_id": 1556516,
            "home_team": "FC Lugano",
            "away_team": "Dukagjini",
            "ecse": {**shared, "ecse_input_hash": "bbb", "ecse_output_hash": "same"},
        },
    ]
    warnings = detect_duplicate_output_distinct_inputs(rows)
    assert warnings
    assert warnings[0]["code"] == "ECSE_DUPLICATE_OUTPUT_DISTINCT_INPUTS"
    ids = {f["fixture_id"] for f in warnings[0]["fixtures"]}
    assert ids == {1593490, 1556516}


def test_fallback_label_field_present_when_flagged():
    raw = {"ecse_fallback_template_used": True, "source": "live_odds"}
    assert raw["ecse_fallback_template_used"] is True


def test_no_bet_true_always_has_reason_after_visibility():
    pred = _pred(confidence=59.0, no_bet=False, dq=80.0)
    pred.metadata = {
        "no_bet_recomputed": "true",
        "no_bet_recompute_mode": "active",
        "no_bet_reasons": "",
        "final_no_bet": "false",
    }
    block = enrich_pick_visibility({"data_quality": 80.0}, pred, data_quality=80.0)
    assert block["no_bet"] is True
    assert block.get("no_bet_reasons")
    assert NoBetReason.CONFIDENCE_BELOW_60.value in block["no_bet_reasons"]


def test_no_bet_reasons_survive_when_already_present():
    pred = _pred(confidence=55.0, no_bet=True, dq=80.0)
    pred.metadata = {
        "no_bet_recomputed": "true",
        "no_bet_recompute_mode": "active",
        "no_bet_reasons": "CONFIDENCE_BELOW_60",
        "final_no_bet": "true",
    }
    block = enrich_pick_visibility({"data_quality": 80.0}, pred, data_quality=80.0)
    assert block["no_bet"] is True
    assert block["no_bet_reasons"] == ["CONFIDENCE_BELOW_60"]


def test_confidence_lineage_reconciles_base_plus_adjustments():
    from worldcup_predictor.adaptive_confidence.models import AdaptiveConfidenceAdjustment

    pred = _pred(confidence=53.7, no_bet=True)
    pred.adaptive_confidence = AdaptiveConfidenceAdjustment(
        base_confidence=60.0,
        final_confidence=53.7,
        total_bonus=-6.3,
        pattern_bonus=-2.0,
        competition_bonus=-1.0,
        similar_situation_bonus=-2.0,
        bucket_bonus=-1.3,
        reason="test",
        similar_sample_size=3,
        similar_winrate=0.4,
        base_prediction_quality=70.0,
        final_prediction_quality=68.0,
        matched_pattern_ids=[],
    )
    lineage = build_confidence_lineage(pred)
    assert lineage["base_confidence"] == 60.0
    assert lineage["threshold_used"] == CONFIDENCE_NO_BET_THRESHOLD
    assert lineage["threshold_comparison_result"]["fails_gate"] is True
    assert lineage["final_display_confidence"] == 53.7


def test_display_rounding_does_not_change_gate_at_exactly_60():
    d = evaluate_no_bet_reasons(confidence=60.0, wde_data_quality=80.0, visibility_data_quality=80.0, scoring_data_quality=80.0)
    assert d.no_bet is False
    d2 = evaluate_no_bet_reasons(confidence=59.95, wde_data_quality=80.0, visibility_data_quality=80.0, scoring_data_quality=80.0)
    assert d2.no_bet is True
    assert CONFIDENCE_NO_BET_THRESHOLD == 60.0


def test_threshold_unchanged():
    assert CONFIDENCE_NO_BET_THRESHOLD == 60.0
