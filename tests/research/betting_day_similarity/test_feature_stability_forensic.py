"""Forensic audit tests — feature stability / OOD. Additive research only."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np

from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.constants import BASELINE_POLICY
from worldcup_predictor.research.betting_day_similarity.feature_stability.ood_forensic import ood_day_analysis
from worldcup_predictor.research.betting_day_similarity.feature_stability.pipeline import (
    run_feature_stability_forensic,
)
from worldcup_predictor.research.betting_day_similarity.feature_stability.stability_drift import (
    distribution_drift_report,
    feature_stability_stats,
)
from worldcup_predictor.research.betting_day_similarity.overlay_policy import apply_similarity_overlay


def _raw(i: int, *, hit: bool = True, day: int | None = None) -> dict:
    d = day if day is not None else (i % 50) + 1
    month = 1 + (d - 1) // 28
    dom = ((d - 1) % 28) + 1
    return {
        "fixture_id": 8000 + i,
        "match_name": f"F{i}",
        "league": "L1" if i % 2 == 0 else "L2",
        "kickoff": f"2025-{month:02d}-{dom:02d}",
        "confidence": 0.45 + (i % 6) * 0.07,
        "entropy": 1.6 + (i % 5) * 0.25,
        "top5_mass": 0.45 + (i % 6) * 0.07,
        "coverage_ratio_primary": 0.7,
        "coverage_ratio_with_insurance": 0.86,
        "residual_mass": 0.14,
        "incremental_uncovered_mass": 0.11,
        "odds_home": 1.85 + (i % 4) * 0.12,
        "main_market_label": "Under 3.5",
        "insurance_market_label": "BTTS Yes",
        "insurance_odds": 1.9,
        "exact3": ["1-0", "2-0", "2-1"],
        "main_coverage_scores": ["0-0"],
        "insurance_scores": ["1-1"],
        "actual_score": "1-0" if hit else "0-2",
    }


def _corpus(n: int = 120) -> list[dict]:
    return [_raw(i, hit=(i % 3) != 0, day=i + 1) for i in range(n)]


def test_stability_and_drift_deterministic():
    rng = np.random.default_rng(20260731)
    names = [f"f{i}" for i in range(5)]
    train = rng.normal(0, 1, size=(40, 5))
    val = rng.normal(0.2, 1.1, size=(20, 5))
    hold = rng.normal(0.8, 1.5, size=(20, 5))
    a = feature_stability_stats(train, val, hold, names)
    b = feature_stability_stats(train, val, hold, names)
    assert a == b
    assert len(a["ranked_by_instability"]) == 5
    d = distribution_drift_report(train, val, hold, names)
    assert len(d["ranked_by_train_holdout_drift"]) == 5
    assert "psi" in d["ranked_by_train_holdout_drift"][0]["train_vs_holdout"]


def test_ood_false_alarm_metrics():
    hold = [{"vienna_date": "2025-01-01", "baseline_action": "SMALL_BET", "baseline_exposure": 1.0, "features": {"avg_wde_confidence": 3.0}}]
    analyses = [
        {
            "ood": {"ood_level": "strongly_out_of_distribution", "reasons": ["nn"], "nn_distance": 5, "centroid_distance": 4},
            "similarity": {"day_similarity_quality_score": 40, "recommendation": "OUT_OF_DISTRIBUTION"},
            "regime_id": 0,
            "nn_distance": 5,
        }
    ]
    rows = [{"vienna_date": "2025-01-01", "baseline_pnl": 1.5, "overlay_pnl": 0.0, "overlay_action": "SIMILARITY_SKIP_OOD", "overlay_exposure": 0.0}]
    rep = ood_day_analysis(
        hold,
        analyses,
        rows,
        feature_names=["avg_wde_confidence"],
        train_mean=np.array([0.5]),
        train_std=np.array([0.1]),
    )
    assert rep["false_ood_metrics"]["false_ood"] == 1
    assert rep["total_missed_profit"] > 0


def test_overlay_untouched_by_forensic_logic():
    # Overlay policy behavior still available and unchanged contract
    out = apply_similarity_overlay(
        base_action="BET",
        base_exposure=2.0,
        base_selected_fixture_ids=[1],
        similarity_recommendation="HOSTILE_SIMILARITY",
        ood_level="in_distribution",
        overlay_cfg={"reduce_capital_multiplier": 0.5, "max_exposure_reduction": 0.4},
    )
    assert out["predictions_unchanged"] is True


def test_forensic_pipeline_artifacts_and_immutability(tmp_path: Path):
    baseline_before = copy.deepcopy(BASELINE_POLICY)
    cand = Path("worldcup_predictor/research/bet_portfolio_manager/calibrated_policy_candidate.json")
    cand_before = cand.read_text(encoding="utf-8") if cand.exists() else ""
    overlay_py = Path("worldcup_predictor/research/betting_day_similarity/overlay_policy.py").read_text(encoding="utf-8")

    summary = run_feature_stability_forensic(
        fixtures=_corpus(150),
        output_dir=tmp_path / "fs",
        max_historical=150,
        max_ablation_features=6,
        seed=20260731,
    )
    assert summary["status"] == "BETTING_DAY_FEATURE_STABILITY_AND_OOD_FORENSIC_COMPLETE"
    assert summary["not_deployed"] is True
    assert summary["similarity_overlay_unchanged"] is True
    assert summary["portfolio_manager_unchanged"] is True
    assert BASELINE_POLICY == baseline_before
    if cand.exists():
        assert cand.read_text(encoding="utf-8") == cand_before
    assert Path("worldcup_predictor/research/betting_day_similarity/overlay_policy.py").read_text(encoding="utf-8") == overlay_py

    for name in (
        "feature_stability_report.json",
        "distribution_drift_report.json",
        "ood_day_analysis.json",
        "feature_importance.json",
        "feature_ablation_report.json",
        "minimal_feature_set.json",
        "regime_stability.json",
        "similarity_method_forensic.json",
        "component_contribution.json",
        "failure_root_cause.json",
        "validation_report.json",
        "owner_feature_stability_dashboard.html",
        "owner_feature_stability_dashboard.md",
        "BETTING_DAY_FEATURE_STABILITY_FORENSIC_REPORT.md",
    ):
        assert (tmp_path / "fs" / name).exists(), name

    root = json.loads((tmp_path / "fs" / "failure_root_cause.json").read_text(encoding="utf-8"))
    assert root["primary_root_cause"]
    assert root["not_implemented"] is True
