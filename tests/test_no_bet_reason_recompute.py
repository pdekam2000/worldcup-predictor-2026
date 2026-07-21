"""Unit tests for reason-based no_bet recomputation."""

from __future__ import annotations

from worldcup_predictor.api.pick_visibility import enrich_pick_visibility
from worldcup_predictor.decision.no_bet_evaluator import (
    apply_no_bet_decision_to_prediction,
    evaluate_no_bet_reasons,
)
from worldcup_predictor.decision.no_bet_reasons import (
    NoBetReason,
    ordered_reason_codes,
)
from worldcup_predictor.domain.prediction import (
    ConfidenceLevel,
    FirstGoalPrediction,
    HalftimePrediction,
    MarketPrediction,
    MatchPrediction,
    PredictionConfidenceBreakdown,
)


def _pred(*, confidence: float, no_bet: bool, dq: float = 80.0, placeholder: bool = False) -> MatchPrediction:
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
        is_placeholder=placeholder,
        metadata={},
    )


def test_confidence_clears_after_enrichment():
    baseline = evaluate_no_bet_reasons(
        confidence=54.0,
        wde_data_quality=80.0,
        visibility_data_quality=80.0,
        scoring_data_quality=80.0,
        inherited_reasons=["CONFIDENCE_BELOW_60"],
        baseline_no_bet=True,
    )
    assert baseline.no_bet is True
    assert NoBetReason.CONFIDENCE_BELOW_60.value in baseline.active_reasons

    final = evaluate_no_bet_reasons(
        confidence=67.0,
        wde_data_quality=80.0,
        visibility_data_quality=80.0,
        scoring_data_quality=80.0,
        inherited_reasons=["CONFIDENCE_BELOW_60"],
        baseline_no_bet=True,
    )
    assert final.no_bet is False
    assert final.active_reasons == []
    assert NoBetReason.CONFIDENCE_BELOW_60.value in final.cleared_reasons


def test_stale_odds_remain_blocking():
    d = evaluate_no_bet_reasons(
        confidence=75.0,
        wde_data_quality=90.0,
        visibility_data_quality=90.0,
        scoring_data_quality=90.0,
        odds_status="stale",
    )
    assert d.no_bet is True
    assert d.active_reasons == [NoBetReason.STALE_ODDS.value]


def test_low_wde_dq_remains_blocking():
    d = evaluate_no_bet_reasons(
        confidence=75.0,
        wde_data_quality=44.0,
        visibility_data_quality=80.0,
        scoring_data_quality=80.0,
    )
    assert d.no_bet is True
    assert NoBetReason.WDE_DATA_QUALITY_BELOW_50.value in d.active_reasons


def test_placeholder_remains_blocking():
    d = evaluate_no_bet_reasons(
        confidence=80.0,
        wde_data_quality=90.0,
        visibility_data_quality=90.0,
        scoring_data_quality=90.0,
        placeholder=True,
    )
    assert d.no_bet is True
    assert d.active_reasons == [NoBetReason.PLACEHOLDER_DATA.value]


def test_manual_block_remains_blocking():
    d = evaluate_no_bet_reasons(
        confidence=90.0,
        wde_data_quality=90.0,
        visibility_data_quality=90.0,
        scoring_data_quality=90.0,
        manual_block=True,
    )
    assert d.no_bet is True
    assert d.active_reasons == [NoBetReason.MANUAL_BLOCK.value]

    # Inherited manual never clears even if manual_block flag is false
    d2 = evaluate_no_bet_reasons(
        confidence=90.0,
        wde_data_quality=90.0,
        visibility_data_quality=90.0,
        scoring_data_quality=90.0,
        manual_block=False,
        inherited_reasons=["MANUAL_BLOCK"],
    )
    assert d2.no_bet is True
    assert NoBetReason.MANUAL_BLOCK.value in d2.active_reasons


def test_legacy_unknown_remains_blocking():
    d = evaluate_no_bet_reasons(
        confidence=90.0,
        wde_data_quality=90.0,
        visibility_data_quality=90.0,
        scoring_data_quality=90.0,
        inherited_reasons=["LEGACY_UNKNOWN_REASON"],
    )
    assert d.no_bet is True
    assert d.active_reasons == [NoBetReason.LEGACY_UNKNOWN_REASON.value]


def test_multiple_reasons_partial_clear():
    final = evaluate_no_bet_reasons(
        confidence=70.0,
        wde_data_quality=90.0,
        visibility_data_quality=90.0,
        scoring_data_quality=90.0,
        odds_status="stale",
        inherited_reasons=["CONFIDENCE_BELOW_60", "STALE_ODDS"],
        baseline_no_bet=True,
    )
    assert final.no_bet is True
    assert NoBetReason.CONFIDENCE_BELOW_60.value in final.cleared_reasons
    assert final.active_reasons == [NoBetReason.STALE_ODDS.value]


def test_no_sticky_inheritance():
    """Baseline no_bet_flag=True with no active reason → final no_bet=False."""
    d = evaluate_no_bet_reasons(
        confidence=67.0,
        wde_data_quality=80.0,
        visibility_data_quality=80.0,
        scoring_data_quality=80.0,
        inherited_reasons=[],
        baseline_no_bet=True,
    )
    assert d.no_bet is False
    assert d.active_reasons == []


def test_serialization_stability_and_order():
    d = evaluate_no_bet_reasons(
        confidence=55.0,
        wde_data_quality=40.0,
        visibility_data_quality=40.0,
        scoring_data_quality=40.0,
        odds_status="stale",
        placeholder=True,
    )
    expected = ordered_reason_codes(
        {
            NoBetReason.CONFIDENCE_BELOW_60,
            NoBetReason.WDE_DATA_QUALITY_BELOW_50,
            NoBetReason.VISIBILITY_DATA_QUALITY_BELOW_45,
            NoBetReason.SCORING_DATA_QUALITY_BELOW_45,
            NoBetReason.PLACEHOLDER_DATA,
            NoBetReason.STALE_ODDS,
        }
    )
    assert d.active_reasons == expected
    # second call identical
    d2 = evaluate_no_bet_reasons(
        confidence=55.0,
        wde_data_quality=40.0,
        visibility_data_quality=40.0,
        scoring_data_quality=40.0,
        odds_status="stale",
        placeholder=True,
    )
    assert d2.active_reasons == d.active_reasons


def test_public_compatibility_boolean_no_bet():
    pred = _pred(confidence=67.0, no_bet=False, dq=80.0)
    decision = evaluate_no_bet_reasons(
        confidence=67.0,
        wde_data_quality=80.0,
        visibility_data_quality=80.0,
        scoring_data_quality=80.0,
        baseline_no_bet=True,
    )
    pred = apply_no_bet_decision_to_prediction(pred, decision, mode="active")
    block = enrich_pick_visibility({"data_quality": 80.0}, pred, data_quality=80.0)
    assert isinstance(block["no_bet"], bool)
    assert block["no_bet"] is False
    assert block.get("no_bet_recomputed") is True
    assert block.get("no_bet_decision_stage") == "FINAL_POST_ENRICHMENT"


def test_legacy_wde_string_alias_clears():
    d = evaluate_no_bet_reasons(
        confidence=70.0,
        wde_data_quality=80.0,
        visibility_data_quality=80.0,
        scoring_data_quality=80.0,
        inherited_reasons=["confidence_below_60", "data_quality_below_50"],
    )
    assert d.no_bet is False
    assert NoBetReason.CONFIDENCE_BELOW_60.value in d.cleared_reasons
    assert NoBetReason.WDE_DATA_QUALITY_BELOW_50.value in d.cleared_reasons


def test_pick_visibility_does_not_or_sticky_when_active():
    """Active recompute: sticky flag alone must not force no_bet if reasons empty."""
    pred = _pred(confidence=65.0, no_bet=False, dq=80.0)
    pred.metadata = {
        "no_bet_recomputed": "true",
        "no_bet_recompute_mode": "active",
        "no_bet_decision_stage": "FINAL_POST_ENRICHMENT",
        "no_bet_reasons": "",
        "final_no_bet": "false",
    }
    # Even if someone left an old sticky mental model — flag is already False after apply.
    block = enrich_pick_visibility({"data_quality": 80.0}, pred, data_quality=80.0)
    assert block["no_bet"] is False


def test_mode_off_is_noop():
    pred = _pred(confidence=70.0, no_bet=True, dq=80.0)
    decision = evaluate_no_bet_reasons(
        confidence=70.0,
        wde_data_quality=80.0,
        visibility_data_quality=80.0,
        scoring_data_quality=80.0,
        baseline_no_bet=True,
    )
    assert decision.no_bet is False
    out = apply_no_bet_decision_to_prediction(pred, decision, mode="off")
    assert out.no_bet_flag is True
    assert out.metadata.get("no_bet_recomputed") is None


def test_mode_shadow_does_not_change_public_flag():
    pred = _pred(confidence=70.0, no_bet=True, dq=80.0)
    decision = evaluate_no_bet_reasons(
        confidence=70.0,
        wde_data_quality=80.0,
        visibility_data_quality=80.0,
        scoring_data_quality=80.0,
        baseline_no_bet=True,
    )
    out = apply_no_bet_decision_to_prediction(pred, decision, mode="shadow")
    assert out.no_bet_flag is True  # public sticky preserved
    assert out.metadata.get("no_bet_recomputed") == "true"
    assert out.metadata.get("shadow_final_no_bet") == "false"
    assert out.metadata.get("shadow_no_bet_differs") == "true"
    block = enrich_pick_visibility({"data_quality": 80.0}, out, data_quality=80.0)
    # Legacy visibility still ORs sticky flag when mode is not active
    assert block["no_bet"] is True
    assert block.get("shadow_final_no_bet") is False


def test_mode_active_clears_sticky_when_no_reason():
    pred = _pred(confidence=70.0, no_bet=True, dq=80.0)
    decision = evaluate_no_bet_reasons(
        confidence=70.0,
        wde_data_quality=80.0,
        visibility_data_quality=80.0,
        scoring_data_quality=80.0,
        baseline_no_bet=True,
    )
    out = apply_no_bet_decision_to_prediction(pred, decision, mode="active")
    assert out.no_bet_flag is False
    block = enrich_pick_visibility({"data_quality": 80.0}, out, data_quality=80.0)
    assert block["no_bet"] is False


def test_mode_unknown_fails_safe_like_off():
    pred = _pred(confidence=70.0, no_bet=True, dq=80.0)
    decision = evaluate_no_bet_reasons(
        confidence=70.0,
        wde_data_quality=80.0,
        visibility_data_quality=80.0,
        scoring_data_quality=80.0,
        baseline_no_bet=True,
    )
    out = apply_no_bet_decision_to_prediction(pred, decision, mode="not_a_mode")
    # Unknown mode must not flip public flag (safe fallback ≠ active).
    assert out.no_bet_flag is True
