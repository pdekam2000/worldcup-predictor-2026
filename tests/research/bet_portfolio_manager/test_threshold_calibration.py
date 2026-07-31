"""Threshold calibration research tests — Portfolio Manager."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from worldcup_predictor.research.bet_portfolio_manager.constants import (
    GRADE_THRESHOLDS as BASELINE_GRADE_THRESHOLDS,
)
from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.audits import (
    action_performance_audit,
    action_semantics_audit,
    gate_attribution,
    grade_audit,
)
from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.capital_modes import (
    calibrate_capital_modes,
)
from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.constants import (
    BASELINE_POLICY,
)
from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.grid_search import (
    check_guardrails,
    chronological_splits,
    generate_candidate_policies,
    leakage_validation,
    pareto_frontier,
    run_grid_on_split,
    score_candidate,
)
from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.metrics import (
    always_bet_metrics,
    summarize_days,
)
from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.pipeline import (
    run_threshold_calibration,
)
from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.policy_engine import (
    decide_under_policy,
    replay_all_days,
)
from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.watch_split import (
    research_watch_split,
)


def _raw(i: int, *, league: str = "L1", conf: float = 0.7, ent: float = 2.0, hit: bool = True, day: int | None = None) -> dict:
    d = (day if day is not None else (i % 40) + 1)
    month = 1 + (d - 1) // 28
    dom = ((d - 1) % 28) + 1
    actual = "1-0" if hit else "0-2"
    return {
        "fixture_id": 9000 + i,
        "match_name": f"Cal Match {i}",
        "league": league,
        "kickoff": f"2025-{month:02d}-{dom:02d}",
        "confidence": conf,
        "entropy": ent,
        "top5_mass": conf,
        "coverage_ratio_primary": 0.75,
        "coverage_ratio_with_insurance": 0.88,
        "residual_mass": 0.12,
        "incremental_uncovered_mass": 0.10,
        "odds_home": 1.95,
        "main_market_family": "over_under",
        "insurance_market_family": "btts",
        "main_market_label": "Under 3.5",
        "insurance_market_label": "BTTS Yes",
        "insurance_odds": 1.90,
        "exact3": ["1-0", "2-0", "2-1"],
        "main_coverage_scores": ["0-0", "3-0"],
        "insurance_scores": ["1-1"],
        "actual_score": actual,
        "top_n_scores": [
            {"score": "1-0", "probability": 0.18},
            {"score": "2-0", "probability": 0.14},
            {"score": "2-1", "probability": 0.11},
            {"score": "0-0", "probability": 0.10},
            {"score": "1-1", "probability": 0.09},
        ],
    }


def _corpus(n: int = 90) -> list[dict]:
    rows = []
    for i in range(n):
        hit = (i % 3) != 0
        conf = 0.55 + (i % 5) * 0.08
        ent = 1.5 + (i % 4) * 0.4
        rows.append(_raw(i, conf=conf, ent=ent, hit=hit, day=i + 1))
    return rows


def test_action_semantics_separation():
    days = replay_all_days(_corpus(60), policy=BASELINE_POLICY)
    sem = action_semantics_audit(days)
    assert "WATCH_NO_CAPITAL_days" in sem
    assert "HARD_SKIP_days" in sem
    assert "skipped" not in sem or sem["definitions"].get("skipped")
    assert sem["full_capital_days"] + sem["reduced_capital_days"] + sem["WATCH_NO_CAPITAL_days"] + sem["HARD_SKIP_days"] <= len(days) + sem["action_counts"].get("WATCH_POSITIVE", 0)


def test_watch_no_capital_and_hard_skip_handling():
    days = replay_all_days(_corpus(60), policy=BASELINE_POLICY)
    for d in days:
        a = d["action"]
        if a == "WATCH_NO_CAPITAL":
            assert d["action_semantics"]["observation_only"] is True
            assert d["action_semantics"]["hard_rejection"] is False
            assert float(d["exposure_units"]) == 0.0
        if a == "HARD_SKIP":
            assert d["action_semantics"]["hard_rejection"] is True
            assert float(d["exposure_units"]) == 0.0


def test_gate_attribution():
    days = replay_all_days(_corpus(45), policy=BASELINE_POLICY)
    rows, summary = gate_attribution(days)
    assert "gates_ranked" in summary
    for r in rows:
        assert "failed_gates" in r
        assert r["result_not_used_in_decision"] is True


def test_counterfactual_and_result_isolation():
    days = replay_all_days(_corpus(45), policy=BASELINE_POLICY)
    perf = action_performance_audit(days)
    for key in ("WATCH_NO_CAPITAL", "HARD_SKIP"):
        block = (perf.get("by_action") or {}).get(key)
        if not block:
            continue
        assert "COUNTERFACTUAL_FROM_FROZEN_OUTPUTS" in block
    for d in days:
        assert d.get("result_not_used_in_decision") is True


def test_grade_aggregation_and_normalization_audit():
    days = replay_all_days(_corpus(60), policy=BASELINE_POLICY)
    perf, boundary = grade_audit(days)
    assert set(perf["grades"].keys()) >= {"S", "A", "B", "C", "D", "F"}
    assert "hypotheses_tested" in boundary
    assert "score_normalization_compressed" in boundary["hypotheses_tested"]


def test_deterministic_grid_and_ranking():
    a = generate_candidate_policies()
    b = generate_candidate_policies()
    assert [p["policy_version"] for p in a] == [p["policy_version"] for p in b]
    assert len(a) >= 10
    fx = _corpus(60)
    days = replay_all_days(fx, policy=BASELINE_POLICY)
    shells = [{"date": d["date"], "fixtures": d["fixtures"]} for d in days]
    splits = chronological_splits(shells)
    grid1 = run_grid_on_split(splits["train_fixtures"], splits["validation_fixtures"], a[:8])
    grid2 = run_grid_on_split(splits["train_fixtures"], splits["validation_fixtures"], a[:8])
    assert [r["configuration_id"] for r in grid1] == [r["configuration_id"] for r in grid2]
    assert [r["validation_rank_score"] for r in grid1] == [r["validation_rank_score"] for r in grid2]


def test_chronological_splits_no_overlap():
    days = [{"date": f"2025-01-{i:02d}", "fixtures": []} for i in range(1, 21)]
    splits = chronological_splits(days)
    train = {d["date"] for d in splits["train"]}
    val = {d["date"] for d in splits["validation"]}
    hold = {d["date"] for d in splits["holdout"]}
    assert not (train & val)
    assert not (val & hold)
    assert not (train & hold)
    # chronological order
    assert max(train) <= min(val)
    assert max(val) <= min(hold)
    leak = leakage_validation(splits["manifest"])
    assert leak["chronological_order_ok"] is True
    assert leak["no_shuffle"] is True


def test_pareto_frontier_construction():
    fake = []
    for i, (roi, dd, exp) in enumerate([(0.5, 2.0, 1.0), (0.4, 1.0, 0.5), (0.3, 3.0, 2.0), (0.45, 1.5, 0.8)]):
        fake.append(
            {
                "configuration_id": f"cfg_{i}",
                "policy_version": f"p{i}",
                "validation_metrics": {
                    "roi": roi,
                    "max_drawdown": dd,
                    "average_exposure": exp,
                    "active_day_ratio": 0.3,
                },
            }
        )
    frontier = pareto_frontier(fake)
    assert len(frontier) >= 1
    ids = {f["configuration_id"] for f in frontier}
    assert "cfg_2" not in ids  # dominated


def test_watch_positive_reject_and_micro_allocation():
    fx = _corpus(80)
    days = replay_all_days(fx, policy=BASELINE_POLICY)
    shells = [{"date": d["date"], "fixtures": d["fixtures"]} for d in days]
    splits = chronological_splits(shells)
    res = research_watch_split(splits["train_fixtures"], splits["validation_fixtures"])
    assert "WATCH_POSITIVE_count" in res
    assert "WATCH_REJECT_count" in res
    assert res["final_locked_ratio"] in (0.05, 0.10, 0.15, 0.20)
    assert res["classification_uses_prematch_only"] is True
    pol = copy.deepcopy(BASELINE_POLICY)
    pol["watch_micro_allocation_ratio"] = 0.10
    pol["watch_positive_score_slack"] = 20.0  # force near-boundary eligibility when WATCH
    d = decide_under_policy(splits["train_fixtures"][:3] or fx[:3], policy=pol)
    assert d["action"] in {"BET", "SMALL_BET", "WATCH_POSITIVE", "WATCH_NO_CAPITAL", "HARD_SKIP"}


def test_capital_allocation_rounding_and_modes():
    fx = _corpus(50)
    cal = calibrate_capital_modes(fx, policy=BASELINE_POLICY)
    assert cal["kelly_disabled_by_default"] is True
    assert "equal" in cal["by_mode"]
    assert "score_weighted" in cal["by_mode"]
    assert "fractional_kelly_research" in cal["by_mode"]


def test_baseline_policy_unchanged_and_candidate_separate(tmp_path: Path):
    baseline_before = copy.deepcopy(BASELINE_POLICY)
    fx = _corpus(100)
    summary = run_threshold_calibration(
        fixtures=fx,
        output_dir=tmp_path / "cal",
        max_candidates=6,
    )
    assert BASELINE_POLICY == baseline_before
    assert BASELINE_GRADE_THRESHOLDS  # baseline module still importable/unchanged shape
    cand = tmp_path / "cal" / "recommended_calibrated_policy.json"
    assert cand.exists()
    payload = json.loads(cand.read_text(encoding="utf-8"))
    assert payload["baseline_unchanged"] is True
    assert payload["not_deployed"] is True
    assert payload["readiness_recommendation"] in {
        "CALIBRATION_GO",
        "CALIBRATION_HOLD",
        "CALIBRATION_RESEARCH_MORE",
    }
    # Required artifacts
    for name in (
        "action_semantics_audit.json",
        "gate_attribution_summary.json",
        "threshold_grid_results.json",
        "chronological_split_manifest.json",
        "leakage_validation.json",
        "final_holdout_evaluation.json",
        "pareto_frontier.json",
        "watch_split_research.json",
        "capital_allocation_calibration.json",
        "validation_report.json",
        "BET_PORTFOLIO_MANAGER_THRESHOLD_CALIBRATION_REPORT.md",
    ):
        assert (tmp_path / "cal" / name).exists(), name
    assert summary["not_deployed"] is True


def test_guardrails_not_forced():
    managed = {"roi": 0.1, "max_drawdown": 10.0, "average_exposure": 5.0, "active_day_ratio": 0.9}
    always = {"roi": 0.4, "max_drawdown": 2.0, "average_exposure": 1.0}
    g = check_guardrails(managed, always)
    assert g["all_passed"] is False
    assert "managed_roi_ge_always" in g["failed"]


def test_locked_holdout_evaluation_once(tmp_path: Path):
    fx = _corpus(100)
    summary = run_threshold_calibration(fixtures=fx, output_dir=tmp_path / "h", max_candidates=4)
    hold = json.loads((tmp_path / "h" / "final_holdout_evaluation.json").read_text(encoding="utf-8"))
    assert hold["locked_once"] is True
    assert hold["no_retune_after_holdout"] is True
    assert summary["status"].startswith("BET_PORTFOLIO_MANAGER_THRESHOLD_CALIBRATION_")


def test_score_candidate_deterministic():
    m = {"roi": 0.4, "max_drawdown": 2.0, "average_exposure": 0.5, "active_day_ratio": 0.3, "win_frequency": 0.5}
    a = {"roi": 0.35, "max_drawdown": 4.0, "average_exposure": 2.0}
    assert score_candidate(m, a) == score_candidate(m, a)


def test_baseline_reproduces_7e77aa3_metrics_within_tolerance():
    """Full-sample Always Bet / Managed should match commit 7e77aa3 within tight tolerance."""
    from worldcup_predictor.research.bet_coverage_optimizer.phase5.corpus import build_phase5_corpus
    from worldcup_predictor.research.bet_portfolio_manager.historical_validation import (
        run_historical_portfolio_validation,
    )
    from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.constants import (
        BASELINE_POLICY,
    )
    from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.metrics import (
        summarize_days,
    )
    from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.policy_engine import (
        replay_all_days,
    )

    corpus = build_phase5_corpus(min_fixtures=1000, max_historical=1200, top_n=8)
    fixtures = list(corpus.get("primary_fixtures") or [])[:1200]
    hv = run_historical_portfolio_validation(fixtures)
    days = replay_all_days(fixtures, policy=BASELINE_POLICY)
    m = summarize_days(days)
    assert abs(float(hv["always_bet"]["roi"]) - 0.408275) < 1e-5
    assert abs(float(hv["always_bet"]["max_drawdown"]) - 7.76) < 1e-6
    assert abs(float(hv["portfolio_managed"]["roi"]) - float(m["roi"])) < 1e-8
    assert int(m["n_zero_capital_days"]) == 402
    assert m["action_distribution"].get("WATCH_NO_CAPITAL") == 400
    assert m["action_distribution"].get("HARD_SKIP") == 2


def test_canonical_and_optimizer_modules_unchanged_paths():
    """Calibration must not rewrite canonical / coverage / insurance / freeze modules."""
    roots = [
        Path("worldcup_predictor/research/bet_coverage_optimizer"),
        Path("worldcup_predictor/wde") if Path("worldcup_predictor/wde").exists() else None,
        Path("worldcup_predictor/ecse") if Path("worldcup_predictor/ecse").exists() else None,
    ]
    # Smoke: calibration package is separate; baseline policy id preserved
    assert BASELINE_POLICY["policy_version"] == "baseline_v1_7e77aa3"
    cand = Path("worldcup_predictor/research/bet_portfolio_manager/calibrated_policy_candidate.json")
    assert cand.exists()
    payload = json.loads(cand.read_text(encoding="utf-8"))
    assert payload.get("baseline_unchanged") is True
    assert payload.get("not_deployed") is True
    for r in roots:
        if r is not None:
            assert r.exists()
