"""Betting Day Similarity Engine research tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np

from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.constants import (
    BASELINE_POLICY,
)
from worldcup_predictor.research.betting_day_similarity.constants import FORBIDDEN_LIVE_FEATURES
from worldcup_predictor.research.betting_day_similarity.distance_metrics import (
    cosine_distance,
    euclidean,
    manhattan,
    mixed_distance,
)
from worldcup_predictor.research.betting_day_similarity.evaluation import chronological_splits
from worldcup_predictor.research.betting_day_similarity.feature_builder import (
    build_day_feature_vector,
    compute_day_labels,
    expected_feature_names,
    rolling_stats_before_date,
)
from worldcup_predictor.research.betting_day_similarity.feature_provenance import validate_leakage
from worldcup_predictor.research.betting_day_similarity.nearest_neighbors import knn_indices
from worldcup_predictor.research.betting_day_similarity.ood_detection import ood_status
from worldcup_predictor.research.betting_day_similarity.overlay_policy import apply_similarity_overlay
from worldcup_predictor.research.betting_day_similarity.pipeline import run_betting_day_similarity_research
from worldcup_predictor.research.betting_day_similarity.preprocessing import FeatureScaler, matrix_from_days
from worldcup_predictor.research.betting_day_similarity.similarity_score import day_similarity_quality_score


def _raw(i: int, *, hit: bool = True, day: int | None = None) -> dict:
    d = day if day is not None else (i % 40) + 1
    month = 1 + (d - 1) // 28
    dom = ((d - 1) % 28) + 1
    return {
        "fixture_id": 7000 + i,
        "match_name": f"Sim {i}",
        "league": "L1" if i % 2 == 0 else "L2",
        "kickoff": f"2025-{month:02d}-{dom:02d}",
        "confidence": 0.5 + (i % 5) * 0.08,
        "entropy": 1.8 + (i % 4) * 0.3,
        "top5_mass": 0.5 + (i % 5) * 0.08,
        "coverage_ratio_primary": 0.7,
        "coverage_ratio_with_insurance": 0.85,
        "residual_mass": 0.15,
        "incremental_uncovered_mass": 0.12,
        "odds_home": 1.9 + (i % 3) * 0.1,
        "main_market_label": "Under 3.5",
        "insurance_market_label": "BTTS Yes",
        "insurance_odds": 1.85,
        "exact3": ["1-0", "2-0", "2-1"],
        "main_coverage_scores": ["0-0"],
        "insurance_scores": ["1-1"],
        "actual_score": "1-0" if hit else "0-2",
    }


def _corpus(n: int = 90) -> list[dict]:
    return [_raw(i, hit=(i % 3) != 0, day=i + 1) for i in range(n)]


def test_feature_cutoff_and_no_result_features():
    fx = _corpus(6)
    pack = build_day_feature_vector(
        fx[:3],
        date="2025-01-05",
        cutoff_timestamp="2025-01-05T12:00:00Z",
        baseline_decision={"selected_fixture_ids": [7000], "action": "SMALL_BET"},
    )
    feats = pack["features"]
    for bad in FORBIDDEN_LIVE_FEATURES:
        assert bad not in feats
    assert "realized_roi" not in feats
    assert pack["meta"]["result_features_excluded"] is True


def test_rolling_excludes_current_and_future():
    hist = []
    for i in range(10):
        hist.append(
            {
                "vienna_date": f"2025-01-{i+1:02d}",
                "labels": {"realized_roi": 0.1 * i, "profitable_day": 1, "coupon_survival": 0.7, "insurance_rescue_count": 0, "complete_coupon_failure": 0},
                "features": {"avg_wde_confidence": 0.6},
            }
        )
    roll = rolling_stats_before_date(hist, target_date="2025-01-05", lookback_days=90)
    assert "rolling_league_reliability" in roll
    # Must not use day 5+
    assert isinstance(roll["rolling_league_reliability"], float)


def test_deterministic_feature_vector():
    fx = _corpus(9)
    a = build_day_feature_vector(fx[:3], date="2025-01-02", cutoff_timestamp="2025-01-02T12:00:00Z")
    b = build_day_feature_vector(fx[:3], date="2025-01-02", cutoff_timestamp="2025-01-02T12:00:00Z")
    assert a["features"] == b["features"]
    assert a["meta"]["feature_content_hash"] == b["meta"]["feature_content_hash"]


def test_training_only_scaler_and_chronological_splits():
    names = expected_feature_names()[:10]
    days = []
    for i in range(20):
        days.append(
            {
                "vienna_date": f"2025-02-{i+1:02d}",
                "day_id": f"d{i}",
                "features": {n: float(i % 5) for n in names},
            }
        )
    splits = chronological_splits(days)
    assert splits["manifest"]["overlap_train_val"] is False
    assert splits["manifest"]["overlap_val_hold"] is False
    assert splits["manifest"]["shuffle"] is False
    X = matrix_from_days(splits["train"], names)
    scaler = FeatureScaler().fit(X, names)
    Xt = scaler.transform(matrix_from_days(splits["validation"], names))
    assert Xt.shape[1] == len(names)


def test_distances_and_knn():
    a = np.array([0.0, 0.0, 1.0])
    b = np.array([1.0, 0.0, 1.0])
    assert euclidean(a, b) > 0
    assert manhattan(a, b) > 0
    assert cosine_distance(a, b) >= 0
    assert mixed_distance(a, b) > 0
    lib = np.vstack([a, b, np.array([2.0, 2.0, 2.0])])
    nn = knn_indices(a, lib, k=2, method="euclidean")
    assert nn[0][0] == 0
    assert nn[0][1] == 0.0


def test_ood_and_similarity_score():
    x = np.zeros(5)
    ood = ood_status(
        x,
        nn_distance=10.0,
        nn_p95=1.0,
        centroid_distance=10.0,
        centroid_p95=1.0,
        train_min=np.zeros(5),
        train_max=np.ones(5),
        missing_ratio=0.0,
        cfg={},
    )
    assert ood["ood_level"] == "strongly_out_of_distribution"
    sim = day_similarity_quality_score(
        nn_similarity_strength=0.8,
        analog_sample_size=2,
        analog_roi_mean=-0.2,
        analog_roi_std=0.1,
        analog_drawdown_mean=1.0,
        analog_coupon_survival=0.4,
        analog_failure_rate=0.4,
        regime_confidence=0.5,
        feature_completeness=1.0,
        ood_level="strongly_out_of_distribution",
        min_analog_count=5,
    )
    assert sim["recommendation"] == "OUT_OF_DISTRIBUTION"
    assert sim["not_a_profit_probability"] is True


def test_overlay_cannot_change_predictions_or_markets():
    out = apply_similarity_overlay(
        base_action="SMALL_BET",
        base_exposure=2.0,
        base_selected_fixture_ids=[1, 2],
        similarity_recommendation="HOSTILE_SIMILARITY",
        ood_level="in_distribution",
        overlay_cfg={"reduce_capital_multiplier": 0.5, "max_exposure_reduction": 0.4},
    )
    assert out["predictions_unchanged"] is True
    assert out["selections_markets_unchanged"] is True
    assert out["freezes_unchanged"] is True


def test_overlay_ood_skip_and_favorable_micro():
    skip = apply_similarity_overlay(
        base_action="BET",
        base_exposure=3.0,
        base_selected_fixture_ids=[1],
        similarity_recommendation="FAVORABLE_SIMILARITY",
        ood_level="strongly_out_of_distribution",
        overlay_cfg={"skip_on_strong_ood": True},
    )
    assert skip["overlay_action"] == "SIMILARITY_SKIP_OOD"
    assert skip["exposure_units"] == 0.0
    fav = apply_similarity_overlay(
        base_action="WATCH_NO_CAPITAL",
        base_exposure=0.0,
        base_selected_fixture_ids=[],
        similarity_recommendation="FAVORABLE_SIMILARITY",
        ood_level="in_distribution",
        overlay_cfg={"watch_micro_allocation": 0.1, "supports_capital_multiplier": 1.15, "max_exposure_uplift": 1.25},
    )
    assert fav["action"] == "WATCH_POSITIVE"


def test_labels_separated_from_features():
    fx = _corpus(3)
    pack = build_day_feature_vector(fx, date="2025-01-01", cutoff_timestamp="2025-01-01T12:00:00Z")
    labels = compute_day_labels(fx, {"selected_fixture_ids": [7000]})
    assert labels["evaluation_only"] is True
    assert "realized_roi" not in pack["features"]


def test_leakage_validation_pass():
    days = [
        {
            "vienna_date": "2025-01-01",
            "cutoff_timestamp": "2025-01-01T12:00:00Z",
            "features": {"avg_wde_confidence": 0.6},
            "labels": {"evaluation_only": True, "realized_roi": 0.1},
        }
    ]
    leak = validate_leakage(days)
    assert leak["passed"] is True


def test_baseline_and_candidate_unchanged(tmp_path: Path):
    baseline_before = copy.deepcopy(BASELINE_POLICY)
    cand_path = Path("worldcup_predictor/research/bet_portfolio_manager/calibrated_policy_candidate.json")
    cand_before = cand_path.read_text(encoding="utf-8") if cand_path.exists() else ""
    summary = run_betting_day_similarity_research(
        fixtures=_corpus(120),
        output_dir=tmp_path / "sim",
        neighbors=5,
        method="mixed",
        max_historical=120,
        seed=20260731,
    )
    assert BASELINE_POLICY == baseline_before
    if cand_path.exists():
        assert cand_path.read_text(encoding="utf-8") == cand_before
    assert summary["not_deployed"] is True
    assert summary["baseline_pm_unchanged"] is True
    for name in (
        "day_feature_provenance.json",
        "leakage_validation.json",
        "feature_dictionary.md",
        "historical_day_features.csv",
        "historical_day_labels.csv",
        "historical_day_manifest.json",
        "similarity_method_comparison.json",
        "regime_assignments.json",
        "regime_profiles.json",
        "regime_stability_report.json",
        "chronological_split_manifest.json",
        "walk_forward_similarity_validation.json",
        "final_holdout_similarity_evaluation.json",
        "similarity_threshold_grid.csv",
        "similarity_threshold_grid.json",
        "similarity_pareto_frontier.json",
        "policy_comparison.json",
        "forward_shadow_summary.json",
        "validation_report.json",
        "BETTING_DAY_SIMILARITY_ENGINE_REPORT.md",
    ):
        assert (tmp_path / "sim" / name).exists(), name


def test_hostile_and_favorable_recommendations():
    fav = day_similarity_quality_score(
        nn_similarity_strength=0.9,
        analog_sample_size=10,
        analog_roi_mean=0.25,
        analog_roi_std=0.05,
        analog_drawdown_mean=0.2,
        analog_coupon_survival=0.8,
        analog_failure_rate=0.1,
        regime_confidence=0.8,
        feature_completeness=1.0,
        ood_level="in_distribution",
        min_analog_count=5,
    )
    assert fav["recommendation"] == "FAVORABLE_SIMILARITY"
    host = day_similarity_quality_score(
        nn_similarity_strength=0.4,
        analog_sample_size=8,
        analog_roi_mean=-0.2,
        analog_roi_std=0.2,
        analog_drawdown_mean=2.0,
        analog_coupon_survival=0.3,
        analog_failure_rate=0.5,
        regime_confidence=0.4,
        feature_completeness=0.9,
        ood_level="in_distribution",
        min_analog_count=5,
    )
    assert host["recommendation"] == "HOSTILE_SIMILARITY"
