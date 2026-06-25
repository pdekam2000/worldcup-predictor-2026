"""Collect market profiles from existing research artifacts (cache-first)."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from worldcup_predictor.market_edge.models import MARKET_IDS, MarketProfile

ROOT = Path(".")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _odds_coverage_pct(api_rows: int, sm_rows: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(min(1.0, (api_rows + sm_rows) / total), 4)


def collect_all_profiles() -> dict[str, MarketProfile]:
    ml1 = _load_json(ROOT / "artifacts/ml1_lgbm_results.json") or {}
    ml1_inv = _load_json(ROOT / "artifacts/ml1_dataset_inventory.json") or {}
    ml1_markets = ml1_inv.get("markets") or {}
    ml1_models = ml1.get("models") or {}
    ml1_sources = ml1_inv.get("sources") or {}
    total_ml1 = int(ml1_inv.get("total_rows") or 1617)
    odds_cov = _odds_coverage_pct(
        int(ml1_sources.get("api_odds_snapshots") or 0),
        int(ml1_sources.get("uefa_sportmonks_odds") or 0),
        total_ml1,
    )

    p51h = _load_json(ROOT / "artifacts/phase51h_egie_backtest.json") or {}
    p51h_mkts = (p51h.get("metrics") or {}).get("by_market") or {}

    p54f7 = _load_json(ROOT / "artifacts/phase54f7_market_specific_xg/market_specific_optimization.json") or {}
    p54f7_mkts = p54f7.get("markets") or {}

    p54p = _load_json(ROOT / "artifacts/phase54p_goalscorer_intelligence/historical_replay.json") or {}
    p54q = _load_json(ROOT / "artifacts/phase54q_goalscorer_generalization/phase54q_report.json") or {}
    p54o_edge = _load_json(ROOT / "artifacts/phase54o_goalscorer_bridge/edge_analysis.json") or {}
    p54q1 = _load_json(ROOT / "artifacts/phase54q1_uefa_goalscorer_odds_audit/phase54q1_report.json") or {}

    ml1_fg = _load_json(ROOT / "artifacts/ml1_fg_engine_results.json") or {}

    fg_ml1_rows = int((ml1_markets.get("first_goal_team") or {}).get("row_count") or 359)
    gs_fixtures = int((p54q.get("dataset_v3") or {}).get("fixtures") or 1541)
    gs_odds_fixtures = int((p54q.get("dataset_v3") or {}).get("fixtures_with_odds") or 47)
    gs_odds_pct = gs_odds_fixtures / gs_fixtures if gs_fixtures else 0.0

    mw = ml1_models.get("MW_Model") or {}
    btts = ml1_models.get("BTTS_Model") or {}
    ou15 = ml1_models.get("OU15_Model") or {}
    ou25 = ml1_models.get("OU25_Model") or {}

    anytime_54p = ((p54p.get("markets") or {}).get("anytime") or {}).get("composite_scorer") or {}
    anytime_54q = ((p54q.get("overall_replay") or {}).get("markets") or {}).get("anytime") or {}
    anytime_comp_54q = anytime_54q.get("composite_scorer") or {}
    first_gs_54p = ((p54p.get("markets") or {}).get("first_goal") or {}).get("composite_scorer") or {}
    first_gs_54q = ((p54q.get("overall_replay") or {}).get("markets") or {}).get("first_goal") or {}
    first_comp_54q = first_gs_54q.get("composite_scorer") or {}

    fg_f7 = (p54f7_mkts.get("first_goal_team") or {}).get("baseline") or {}
    gr_f7 = ((p54f7_mkts.get("goal_range") or {}).get("arms") or {}).get("baseline") or {}

    disagree_hit = float(p54o_edge.get("disagree_group_hit_rate") or 0)
    wc_gs_top3 = float(anytime_54p.get("top3_hit") or 0)
    overall_gs_top3 = float(anytime_comp_54q.get("top3_hit") or 0)

    profiles: dict[str, MarketProfile] = {}

    profiles["1x2"] = MarketProfile(
        market_id="1x2",
        display_name="1X2",
        dataset_size=total_ml1,
        coverage_pct=1.0,
        accuracy=float(mw.get("accuracy") or 0),
        baseline_accuracy=float(mw.get("majority_baseline_accuracy") or 0.39),
        calibration_ece=float(mw["calibration_ece"]) if mw.get("calibration_ece") is not None else None,
        stability_score=max(0.0, min(1.0, float(mw.get("delta_vs_majority") or 0) * 5 + 0.5)),
        odds_availability_pct=odds_cov,
        roi_potential=max(0.0, min(1.0, 0.5 + float(mw.get("roi_proxy") or -0.6))),
        production_status="production",
        infrastructure_tier="ml1_production",
        data_sources=["artifacts/ml1_lgbm_results.json", "prediction/scoring_engine.py"],
        notes="Primary WDE market; ML-1 delta vs majority small but positive.",
    )

    dc_acc = min(0.72, float(mw.get("accuracy") or 0.4) + 0.17)
    profiles["double_chance"] = MarketProfile(
        market_id="double_chance",
        display_name="Double Chance",
        dataset_size=total_ml1,
        coverage_pct=1.0,
        accuracy=dc_acc,
        accuracy_metric="derived_proxy",
        baseline_accuracy=0.55,
        stability_score=0.55,
        odds_availability_pct=odds_cov * 0.5,
        roi_potential=0.45,
        production_status="production_derived",
        infrastructure_tier="derived_from_1x2",
        data_sources=["api/prediction_output.py"],
        notes="Derived from 1X2; no dedicated edge backtest.",
    )

    profiles["btts"] = MarketProfile(
        market_id="btts",
        display_name="BTTS",
        dataset_size=total_ml1,
        coverage_pct=1.0,
        accuracy=float(btts.get("accuracy") or 0),
        baseline_accuracy=float(btts.get("majority_baseline_accuracy") or 0.58),
        calibration_ece=float(btts.get("calibration_ece") or 0.15),
        brier=float(btts.get("brier_score") or 0.27),
        stability_score=max(0.0, min(1.0, 0.5 + float(btts.get("delta_vs_majority") or 0) * 3)),
        odds_availability_pct=odds_cov,
        roi_potential=max(0.0, min(1.0, 0.5 + float(btts.get("roi_proxy") or -0.45))),
        production_status="production",
        infrastructure_tier="ml1_production",
        data_sources=["artifacts/ml1_lgbm_results.json", "prediction/extended_markets.py"],
    )

    profiles["over_0_5_ht"] = MarketProfile(
        market_id="over_0_5_ht",
        display_name="Over 0.5 HT",
        dataset_size=0,
        coverage_pct=0.0,
        accuracy=None,
        stability_score=0.1,
        odds_availability_pct=0.05,
        roi_potential=0.1,
        production_status="none",
        infrastructure_tier="gap",
        data_sources=["artifacts/sportmonks_all_in_deep_test/ (discovery only)"],
        notes="No labels, trainer, or backtest engine.",
    )

    profiles["over_1_5"] = MarketProfile(
        market_id="over_1_5",
        display_name="Over 1.5",
        dataset_size=total_ml1,
        coverage_pct=1.0,
        accuracy=float(ou15.get("accuracy") or 0),
        baseline_accuracy=float(ou15.get("majority_baseline_accuracy") or 0.82),
        calibration_ece=float(ou15.get("calibration_ece") or 0.13),
        brier=float(ou15.get("brier_score") or 0.17),
        stability_score=max(0.0, min(1.0, 0.4 + float(ou15.get("delta_vs_majority") or 0) * 3)),
        odds_availability_pct=odds_cov,
        roi_potential=max(0.0, min(1.0, 0.5 + float(ou15.get("roi_proxy") or -0.19))),
        production_status="research_only",
        infrastructure_tier="ml1_labels",
        data_sources=["artifacts/ml1_lgbm_results.json"],
        notes="High raw accuracy but below majority baseline.",
    )

    profiles["over_2_5"] = MarketProfile(
        market_id="over_2_5",
        display_name="Over 2.5",
        dataset_size=total_ml1,
        coverage_pct=1.0,
        accuracy=float(ou25.get("accuracy") or 0),
        baseline_accuracy=float(ou25.get("majority_baseline_accuracy") or 0.61),
        calibration_ece=float(ou25.get("calibration_ece") or 0.16),
        brier=float(ou25.get("brier_score") or 0.27),
        stability_score=max(0.0, min(1.0, 0.45 + float(ou25.get("delta_vs_majority") or 0) * 3)),
        odds_availability_pct=odds_cov,
        roi_potential=max(0.0, min(1.0, 0.5 + float(ou25.get("roi_proxy") or -0.45))),
        production_status="production",
        infrastructure_tier="ml1_production",
        data_sources=["artifacts/ml1_lgbm_results.json", "prediction/scoring_engine.py"],
    )

    fg_51h = (p51h_mkts.get("first_goal_team") or {})
    fg_acc = float(fg_f7.get("accuracy") or fg_51h.get("winrate") or 0.5)
    profiles["team_to_score_first"] = MarketProfile(
        market_id="team_to_score_first",
        display_name="Team To Score First",
        dataset_size=int(p54f7.get("usable_fixtures") or fg_ml1_rows),
        coverage_pct=fg_ml1_rows / total_ml1 if total_ml1 else 0,
        accuracy=fg_acc,
        accuracy_metric="accuracy",
        baseline_accuracy=0.5,
        calibration_ece=float(fg_f7.get("calibration_ece") or 0.1),
        stability_score=0.55,
        odds_availability_pct=max(odds_cov, 0.3),
        roi_potential=0.55,
        production_status="production",
        infrastructure_tier="goal_timing_xg",
        data_sources=["artifacts/phase51h_egie_backtest.json", "artifacts/phase54f7_market_specific_xg/"],
    )

    profiles["first_goal_team"] = MarketProfile(
        market_id="first_goal_team",
        display_name="First Goal Team",
        dataset_size=int(p54f7.get("usable_fixtures") or fg_ml1_rows),
        coverage_pct=fg_ml1_rows / total_ml1 if total_ml1 else 0,
        accuracy=fg_acc,
        baseline_accuracy=0.5,
        calibration_ece=float(fg_f7.get("calibration_ece") or 0.1),
        stability_score=0.52,
        odds_availability_pct=max(odds_cov, 0.35),
        roi_potential=0.58,
        production_status="production",
        infrastructure_tier="goal_timing_xg",
        data_sources=["artifacts/phase51h_egie_backtest.json", "artifacts/ml1_fg_engine_results.json"],
        notes="Alias of team-to-score-first in current infra.",
    )

    profiles["anytime_goalscorer"] = MarketProfile(
        market_id="anytime_goalscorer",
        display_name="Anytime Goalscorer",
        dataset_size=gs_fixtures,
        coverage_pct=1.0,
        accuracy=overall_gs_top3,
        accuracy_metric="top3_hit",
        baseline_accuracy=0.20,
        calibration_ece=0.37,
        stability_score=0.62 if overall_gs_top3 >= 0.55 else 0.4,
        odds_availability_pct=gs_odds_pct,
        roi_potential=min(1.0, 0.35 + disagree_hit * 0.5 + wc_gs_top3 * 0.2),
        production_status="shadow_high_value",
        infrastructure_tier="goalscorer_54k_54s",
        data_sources=[
            "artifacts/phase54q_goalscorer_generalization/",
            "artifacts/phase54p_goalscorer_intelligence/",
            "artifacts/phase54o_goalscorer_bridge/edge_analysis.json",
        ],
        notes=f"WC bridged top-3={wc_gs_top3:.1%}; disagree hit={disagree_hit:.1%}; UEFA odds gap per 54Q-1.",
    )

    profiles["first_goalscorer"] = MarketProfile(
        market_id="first_goalscorer",
        display_name="First Goalscorer",
        dataset_size=gs_fixtures,
        coverage_pct=1.0,
        accuracy=float(first_comp_54q.get("top3_hit") or first_gs_54p.get("top3_hit") or 0.31),
        accuracy_metric="top3_hit",
        baseline_accuracy=0.08,
        calibration_ece=0.40,
        stability_score=0.35,
        odds_availability_pct=gs_odds_pct * 0.8,
        roi_potential=0.42,
        production_status="shadow",
        infrastructure_tier="goalscorer_54k_54s",
        data_sources=["artifacts/phase54q_goalscorer_generalization/"],
    )

    gr_51h = (p51h_mkts.get("goal_range") or {})
    profiles["goal_range"] = MarketProfile(
        market_id="goal_range",
        display_name="Goal Range",
        dataset_size=int((ml1_markets.get("goal_range") or {}).get("row_count") or 359),
        coverage_pct=0.22,
        accuracy=float(gr_f7.get("accuracy") or gr_51h.get("winrate") or 0.28),
        baseline_accuracy=0.17,
        stability_score=0.3,
        odds_availability_pct=0.1,
        roi_potential=0.25,
        production_status="production",
        infrastructure_tier="goal_timing",
        data_sources=["artifacts/phase51h_egie_backtest.json", "artifacts/phase54f7_market_specific_xg/"],
        notes="RESEARCH_ONLY per 54F-7.",
    )

    gt_51h = (p51h_mkts.get("goal_minute") or {})
    profiles["goal_timing"] = MarketProfile(
        market_id="goal_timing",
        display_name="Goal Timing",
        dataset_size=int(p51h.get("metrics", {}).get("fixtures_scanned") or 349),
        coverage_pct=0.22,
        accuracy=float(gt_51h.get("soft_winrate") or 0.34),
        accuracy_metric="soft_winrate",
        baseline_accuracy=0.15,
        stability_score=0.28,
        odds_availability_pct=0.08,
        roi_potential=0.22,
        production_status="production",
        infrastructure_tier="goal_timing",
        data_sources=["artifacts/phase51h_egie_backtest.json", "goal_timing/backtest/"],
        notes="Hard minute hit rate ~3.4%; soft tolerance ~33.8%.",
    )

    profiles["correct_score"] = MarketProfile(
        market_id="correct_score",
        display_name="Correct Score",
        dataset_size=total_ml1,
        coverage_pct=0.5,
        accuracy=0.12,
        accuracy_metric="top1_proxy",
        baseline_accuracy=0.05,
        stability_score=0.2,
        odds_availability_pct=odds_cov * 0.3,
        roi_potential=0.15,
        production_status="production_display",
        infrastructure_tier="poisson_derived",
        data_sources=["prediction/extended_markets.py"],
        notes="No dedicated backtest; accuracy is literature-style proxy for top-1 CS.",
    )

    for mid in MARKET_IDS:
        profiles.setdefault(mid, MarketProfile(market_id=mid, display_name=mid))

    return profiles
