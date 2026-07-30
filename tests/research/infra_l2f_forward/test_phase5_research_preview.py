"""Phase 5 research preview + agreement classification tests."""

from __future__ import annotations

from worldcup_predictor.research.infra_l2f_forward.agreement import (
    MODELS_AGREE,
    MODELS_CONFLICT,
    RESEARCH_ONLY_NO_BET,
    classify_model_agreement,
)
from worldcup_predictor.research.infra_l2f_forward.research_preview import build_top_comparison


def test_agreement_models_agree():
    out = classify_model_agreement(
        canonical_top1="1-0",
        exact_top1="1-0",
        top3_overlap=3,
        top5_overlap=4,
        canonical_confidence=55.0,
        canonical_top5_mass=0.48,
        exact_top5_mass=0.50,
        canonical_total_lambda=2.4,
        exact_total_lambda=2.5,
        high_score_tail_diff=0.01,
        no_bet=False,
    )
    assert out["agreement_classification"] in {MODELS_AGREE, "SHADOW_HIGHER_CONCENTRATION"}
    assert MODELS_AGREE in out["agreement_tags"]
    assert out["does_not_alter_canonical_routing"] is True


def test_agreement_conflict_and_no_bet():
    out = classify_model_agreement(
        canonical_top1="2-0",
        exact_top1="0-2",
        top3_overlap=0,
        top5_overlap=0,
        canonical_confidence=60.0,
        canonical_top5_mass=0.4,
        exact_top5_mass=0.35,
        canonical_total_lambda=2.2,
        exact_total_lambda=2.3,
        high_score_tail_diff=0.0,
        no_bet=True,
    )
    assert out["agreement_classification"] == RESEARCH_ONLY_NO_BET
    assert MODELS_CONFLICT in out["agreement_tags"]


def test_top_comparison_metrics():
    c = [{"score": "1-0", "probability": 0.12}, {"score": "2-0", "probability": 0.1}, {"score": "1-1", "probability": 0.09}]
    e = [{"score": "1-0", "probability": 0.11}, {"score": "0-0", "probability": 0.1}, {"score": "2-0", "probability": 0.08}]
    cmp = build_top_comparison(c, e)
    assert cmp["top1_agreement"] is True
    assert cmp["top3_overlap_count"] == 2
    assert cmp["score_distance_top1"] == 0
    assert len(cmp["side_by_side"]) == 5
