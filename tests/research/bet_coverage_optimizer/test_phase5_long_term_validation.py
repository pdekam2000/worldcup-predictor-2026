"""Phase 5 long-term validation tests (research-only)."""

from __future__ import annotations

import json
from pathlib import Path

from worldcup_predictor.research.bet_coverage_optimizer.phase5.historical_validation import (
    run_historical_validation,
)
from worldcup_predictor.research.bet_coverage_optimizer.phase5.layer_builder import (
    extract_real_market_candidates,
    select_main_and_insurance,
)
from worldcup_predictor.research.bet_coverage_optimizer.phase5.readiness import compute_readiness_score
from worldcup_predictor.research.bet_coverage_optimizer.phase5.robustness import run_robustness_tests


def _fx(i: int, *, actual: str, ins_scores: list[str], main_extra: list[str] | None = None) -> dict:
    top = [
        {"score": "1-0", "probability": 0.18},
        {"score": "2-0", "probability": 0.15},
        {"score": "2-1", "probability": 0.12},
        {"score": "0-0", "probability": 0.10},
        {"score": "1-1", "probability": 0.09},
        {"score": "3-0", "probability": 0.08},
        {"score": "0-1", "probability": 0.07},
        {"score": "3-1", "probability": 0.06},
    ]
    exact3 = ["1-0", "2-0", "2-1"]
    main_cov = main_extra or ["0-0", "3-0"]
    return {
        "fixture_id": 1000 + i,
        "league": "TEST" if i % 2 == 0 else "TESTB",
        "top_n_scores": top,
        "exact3": exact3,
        "main_coverage_scores": main_cov,
        "insurance_scores": ins_scores,
        "baseline_125_scores": [t["score"] for t in top],
        "actual_score": actual,
        "prematch_odds_complete": True,
        "monetary": {"coverage_odds": 2.0, "insurance_odds": 2.2, "stake": 1.0},
        "entropy": 2.2 + (i % 5) * 0.1,
        "confidence": 0.4 + (i % 5) * 0.05,
        "lambda_total": 2.5,
        "odds_home": 1.9,
        "insurance_market_label": "BTTS Yes",
        "insurance_market_family": "btts",
        "insurance_odds": 2.2,
        "incremental_uncovered_mass": 0.09,
        "primary_overlap_ratio": 0.2,
        "coverage_ratio_primary": 0.7,
        "residual_mass": 0.2,
        "all_candidates": [],
    }


def test_layer_builder_uses_real_odds_only():
    top = [("1-0", 0.2), ("2-0", 0.15), ("0-0", 0.1), ("1-1", 0.09), ("2-1", 0.08)]
    raw = {
        "oddsFT_BTTS_Yes": 1.9,
        "oddsFT_BTTS_No": 1.85,
        "oddsFT_Over_2_5": 2.05,
        "oddsFT_Under_2_5": 1.75,
        "oddsFT_1": 2.10,
        "oddsFT_X": 3.20,
        "oddsFT_2": 3.40,
    }
    # Fabricated / missing should be ignored
    raw["oddsFT_Over_1_5"] = 0.5
    cands = extract_real_market_candidates(raw, top_n_pairs=top, exact3=["1-0", "2-0", "0-0"])
    assert cands
    assert all(float(c["odds"]) > 1.0 for c in cands)
    layers = select_main_and_insurance(cands, top_n_pairs=top, exact3=["1-0", "2-0", "0-0"])
    assert layers["main_coverage"] is not None


def test_historical_validation_insurance_reduces_failure():
    fixtures = []
    for i in range(120):
        # Cycle: often main hits; sometimes only insurance; sometimes miss
        mod = i % 7
        if mod < 4:
            actual = "1-0"
            ins = ["1-1"]
        elif mod < 6:
            actual = "1-1"
            ins = ["1-1"]
        else:
            actual = "0-1"
            ins = ["1-1"]
        fixtures.append(_fx(i, actual=actual, ins_scores=ins))
    hv = run_historical_validation(fixtures)
    assert hv["included_fixtures"] == 120
    assert hv["complete_coupon_failure"]["insurance_reduces_complete_failure"] is True
    assert hv["main_plus_insurance_outperforms_main"] is True


def test_readiness_hold_without_forward():
    historical = {
        "main_plus_insurance_outperforms_main": True,
        "complete_coupon_failure": {
            "insurance_reduces_complete_failure": True,
            "insurance_rescue_count": 20,
        },
        "statistical_significance": {"significant_at_0_05": True},
        "priced_subset_analysis": {"n": 100, "roi": -0.05, "profit_factor": 0.9},
        "calibration_error": {"exact3_main_insurance": 0.1},
    }
    readiness = compute_readiness_score(
        historical=historical,
        league={
            "leagues_ranked": [
                {"insurance_hurts_performance": False},
                {"insurance_hurts_performance": False},
                {"insurance_hurts_performance": True},
            ],
            "leagues_where_insurance_hurts": ["X"],
        },
        market={"families_ranked": [{"rescue_frequency": 0.1, "roi": 0.0}]},
        calibration={"higher_confidence_better": True},
        forward={"n_forward_days": 3, "forward_evidence_sufficient": False},
        robustness={"robust_to_incomplete_markets": True},
        n_fixtures=1200,
    )
    assert readiness["recommendation"] in {"HOLD", "GO", "RESEARCH MORE"}
    # Without forward evidence, GO is not allowed
    assert readiness["recommendation"] != "GO" or readiness["gates"]["forward_evidence"]


def test_robustness_graceful(tmp_path: Path):
    fixtures = [_fx(i, actual="1-0", ins_scores=["1-1"]) for i in range(50)]
    # Attach candidates so degradation path runs
    top = [(x["score"], x["probability"]) for x in fixtures[0]["top_n_scores"]]
    raw = {
        "oddsFT_BTTS_Yes": 1.9,
        "oddsFT_BTTS_No": 1.85,
        "oddsFT_Over_2_5": 2.0,
        "oddsFT_Under_2_5": 1.8,
        "oddsFT_1": 2.0,
        "oddsFT_X": 3.2,
        "oddsFT_2": 3.5,
        "oddsFT_1X": 1.3,
        "oddsFT_X2": 1.7,
        "oddsFT_12": 1.35,
        "oddsFT_Over_1_5": 1.4,
        "oddsFT_Under_3_5": 1.6,
    }
    cands = extract_real_market_candidates(raw, top_n_pairs=top, exact3=["1-0", "2-0", "2-1"])
    for f in fixtures:
        f["all_candidates"] = cands
    rep = run_robustness_tests(fixtures, seed=1)
    assert "scenarios" in rep
    assert rep["robust_to_incomplete_markets"] is True


def test_phase5_pipeline_smoke(tmp_path: Path):
    # Use real DBs if present; otherwise skip heavy path with unit-level already covered
    source = Path("data/football_intelligence.db")
    forward = Path("data/evaluation/forward_prediction_tracking.db")
    if not source.exists():
        return
    from worldcup_predictor.research.bet_coverage_optimizer.phase5.pipeline import run_phase5

    result = run_phase5(
        min_fixtures=200,  # smoke: lower floor for CI speed; full run uses 1000
        max_historical=250,
        top_n=8,
        source_db=source,
        forward_db=forward if forward.exists() else None,
        output_dir=tmp_path / "phase5",
    )
    assert result["status"] == "BET_COVERAGE_OPTIMIZER_PHASE5_LONG_TERM_VALIDATED"
    assert result["n_fixtures"] >= 200
    out = Path(result["output_dir"])
    for name in (
        "historical_validation.json",
        "league_validation.json",
        "market_family_validation.json",
        "odds_bucket_validation.json",
        "calibration_report.json",
        "forward_shadow_30d.json",
        "readiness_score.json",
        "owner_validation_dashboard.html",
        "owner_validation_dashboard.md",
        "validation_report.json",
    ):
        assert (out / name).exists(), name
    readiness = json.loads((out / "readiness_score.json").read_text(encoding="utf-8"))
    assert readiness["recommendation"] in {"GO", "HOLD", "RESEARCH MORE"}
