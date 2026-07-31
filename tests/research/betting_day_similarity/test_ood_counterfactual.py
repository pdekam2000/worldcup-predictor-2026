"""OOD counterfactual research tests — read-only."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.constants import BASELINE_POLICY
from worldcup_predictor.research.betting_day_similarity.ood_counterfactual import (
    DECISION_ARCHIVE,
    DECISION_BUILD,
)
from worldcup_predictor.research.betting_day_similarity.ood_counterfactual.metrics import (
    delta_table,
    summarize_policy_rows,
)
from worldcup_predictor.research.betting_day_similarity.ood_counterfactual.pipeline import (
    run_ood_counterfactual_research,
)


def _raw(i: int, *, hit: bool = True, day: int | None = None) -> dict:
    d = day if day is not None else (i % 50) + 1
    month = 1 + (d - 1) // 28
    dom = ((d - 1) % 28) + 1
    return {
        "fixture_id": 8100 + i,
        "match_name": f"CF{i}",
        "league": "L1" if i % 2 == 0 else "L2",
        "kickoff": f"2025-{month:02d}-{dom:02d}",
        "confidence": 0.5 + (i % 5) * 0.08,
        "entropy": 1.7 + (i % 4) * 0.3,
        "top5_mass": 0.5 + (i % 5) * 0.08,
        "coverage_ratio_primary": 0.72,
        "coverage_ratio_with_insurance": 0.88,
        "residual_mass": 0.12,
        "incremental_uncovered_mass": 0.1,
        "odds_home": 1.9,
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


def test_metrics_delta_table():
    rows = [
        {"overlay_exposure": 1.0, "overlay_pnl": 0.5},
        {"overlay_exposure": 2.0, "overlay_pnl": -0.5},
    ]
    m = summarize_policy_rows(rows, "overlay_exposure", "overlay_pnl")
    assert m["net_profit"] == 0.0
    d = delta_table(m, {**m, "roi": (m["roi"] or 0) + 0.1, "net_profit": 1.0})
    assert d["net_profit"]["delta"] == 1.0


def test_counterfactual_pipeline_immutability(tmp_path: Path):
    baseline_before = copy.deepcopy(BASELINE_POLICY)
    overlay_path = Path("worldcup_predictor/research/betting_day_similarity/overlay_policy.py")
    overlay_before = overlay_path.read_text(encoding="utf-8")
    ood_path = Path("worldcup_predictor/research/betting_day_similarity/ood_detection.py")
    ood_before = ood_path.read_text(encoding="utf-8")
    cand = Path("worldcup_predictor/research/bet_portfolio_manager/calibrated_policy_candidate.json")
    cand_before = cand.read_text(encoding="utf-8") if cand.exists() else ""

    summary = run_ood_counterfactual_research(
        fixtures=_corpus(150),
        output_dir=tmp_path / "cf",
        max_historical=150,
        seed=20260731,
    )
    assert summary["status"] == "OOD_VERIFIER_COUNTERFACTUAL_RESEARCH_COMPLETE"
    assert summary["not_deployed"] is True
    assert summary["decision"] in {DECISION_BUILD, DECISION_ARCHIVE}
    assert summary["similarity_unchanged"] is True
    assert summary["portfolio_unchanged"] is True
    assert summary["ood_detector_unchanged"] is True
    assert BASELINE_POLICY == baseline_before
    assert overlay_path.read_text(encoding="utf-8") == overlay_before
    assert ood_path.read_text(encoding="utf-8") == ood_before
    if cand.exists():
        assert cand.read_text(encoding="utf-8") == cand_before

    for name in (
        "false_ood_inventory.json",
        "counterfactual_false_ood_replay.json",
        "false_ood_value_analysis.json",
        "false_ood_recovery_curve.json",
        "perfect_ood_upper_bound.json",
        "cost_benefit_analysis.json",
        "recommendation.json",
        "owner_ood_counterfactual_dashboard.html",
        "owner_ood_counterfactual_dashboard.md",
        "OOD_VERIFIER_COUNTERFACTUAL_REPORT.md",
        "validation_report.json",
    ):
        assert (tmp_path / "cf" / name).exists(), name

    rec = json.loads((tmp_path / "cf" / "recommendation.json").read_text(encoding="utf-8"))
    assert rec["no_middle_ground"] is True
    assert rec["decision"] in {DECISION_BUILD, DECISION_ARCHIVE}

    inv = json.loads((tmp_path / "cf" / "false_ood_inventory.json").read_text(encoding="utf-8"))
    assert inv["n_false_ood"] + inv["n_true_ood"] == inv["n_all_ood"]
    for d in inv["days"]:
        assert d["is_false_ood"] is True
        assert float(d.get("baseline_pnl") or 0) >= 0
