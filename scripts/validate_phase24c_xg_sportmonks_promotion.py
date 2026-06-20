"""Phase 24C — xG + Sportmonks prediction promotion validation (offline)."""

from __future__ import annotations

import os
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _build_fixtures():
    from datetime import datetime, timedelta, timezone

    from worldcup_predictor.agents.specialists.helpers import make_signal
    from worldcup_predictor.domain.fixture import Fixture
    from worldcup_predictor.domain.intelligence import MatchIntelligenceReport, TeamIntelligence
    from worldcup_predictor.domain.prediction import (
        ConfidenceLevel,
        FirstGoalPrediction,
        HalftimePrediction,
        MarketPrediction,
        MatchPrediction,
        PredictionConfidenceBreakdown,
    )
    from worldcup_predictor.domain.specialist import MatchSpecialistReport

    kickoff = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=2)
    fixture = Fixture(
        id=1489400,
        competition_key="world_cup_2026",
        home_team="France",
        away_team="Japan",
        home_team_id=30,
        away_team_id=31,
        kickoff_utc=kickoff,
        venue="Test Stadium",
        stage="Group Stage",
        league_id=1,
        season=2026,
        status="NS",
    )
    report = MatchIntelligenceReport(
        fixture_id=1489400,
        fixture=fixture,
        home_team=TeamIntelligence(team_name="France", team_id=30),
        away_team=TeamIntelligence(team_name="Japan", team_id=31),
        is_placeholder=False,
    )
    baseline = MatchPrediction(
        fixture_id=1489400,
        competition_key="world_cup_2026",
        match_name="France vs Japan",
        one_x_two=MarketPrediction(market="1x2", selection="home_win", probability=0.52),
        over_under=MarketPrediction(market="over_under_2_5", selection="over_2_5", probability=0.58),
        halftime=HalftimePrediction(estimated_total_goals=1.5),
        first_goal=FirstGoalPrediction(team="France"),
        confidence_score=66.0,
        confidence_level=ConfidenceLevel.MEDIUM,
        confidence_breakdown=PredictionConfidenceBreakdown(
            form_score=64.0,
            h2h_score=55.0,
            injuries_score=60.0,
            lineups_score=52.0,
            odds_score=58.0,
            data_quality_score=74.0,
            total=66.0,
        ),
        risk_level="medium",
    )

    tactics = make_signal(
        "tactics_agent",
        "tactics",
        "available",
        {
            "xg_attack_strength_home": 58.0,
            "xg_attack_strength_away": 52.0,
            "over_under_tendency": "over_lean",
            "expected_goal_pressure": 2.9,
        },
    )
    xg_v2 = make_signal(
        "xg_chance_quality_intelligence_agent",
        "xg_chance_quality_v2",
        "available",
        {
            "goals_pressure_score": 62.0,
            "prediction_impact": {"over25_adjustment": 4.0},
            "risk_flags": [],
        },
    )
    xg_intel = make_signal(
        "xg_intelligence_agent",
        "sportmonks_xg_intelligence",
        "available",
        {
            "home_xg": 1.65,
            "away_xg": 1.05,
            "xg_total": 2.7,
            "xg_difference": 0.6,
            "xg_confidence": 85.0,
            "plan_support": "full",
            "comparison_available": True,
            "disagreement_score": 0.18,
            "xg_supports_internal": True,
            "data_sources": ["xGFixture"],
        },
    )
    sm_pred = make_signal(
        "sportmonks_prediction_agent",
        "sportmonks_prediction_benchmark",
        "available",
        {
            "sportmonks_home_probability": 0.48,
            "sportmonks_draw_probability": 0.28,
            "sportmonks_away_probability": 0.24,
            "sportmonks_confidence": 62.0,
            "disagreement_vs_internal": 0.32,
            "consensus_with_internal": 52.0,
            "conflict_level": "medium",
            "recommendation": "caution",
            "sportmonks_odds_available": True,
            "sportmonks_prediction_available": True,
            "internal_lean": "home_win",
            "sportmonks_lean": "home_win",
        },
    )
    specialist = MatchSpecialistReport(
        fixture_id=1489400,
        signals={
            "tactics_agent": tactics,
            "xg_chance_quality_intelligence_agent": xg_v2,
            "xg_intelligence_agent": xg_intel,
            "sportmonks_prediction_agent": sm_pred,
        },
    )
    return report, baseline, specialist


def _run_wde(xg_mode: str, sm_mode: str):
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.decision.weighted_decision_engine import DecisionInput, WeightedDecisionEngine

    os.environ["XG_PROMOTION_MODE"] = xg_mode
    os.environ["SPORTMONKS_PREDICTION_PROMOTION_MODE"] = sm_mode
    os.environ["EXPECTED_LINEUP_PROMOTION_MODE"] = "off"
    os.environ["TOURNAMENT_CONTEXT_PROMOTION_MODE"] = "off"
    get_settings.cache_clear()

    report, baseline, specialist = _build_fixtures()
    engine = WeightedDecisionEngine()
    output = engine.decide(
        DecisionInput(baseline=baseline, report=report, specialist_report=specialist)
    )
    factors = output.audit.all_contributions
    tactics_score = next((f.score for f in factors if f.factor_name == "tactics_matchup"), None)
    return (
        output,
        engine._last_xg_promotion,
        engine._last_sportmonks_promotion,
        tactics_score,
        output.audit.trace,
        output.confidence_score,
    )


def main() -> int:
    from worldcup_predictor.config.model_weights import DEFAULT_FACTOR_WEIGHTS, get_factor_weights
    from worldcup_predictor.promotion.config import (
        MAX_CUMULATIVE_PROMOTION_CONF_DELTA,
        MAX_SPORTMONKS_CONFIDENCE_REDUCE,
        MAX_XG_TACTICS_SCORE_DELTA,
        XG_PROMOTION_FACTOR_KEY,
    )

    checks: list[tuple[str, bool]] = []

    weights = get_factor_weights(use_calibrated=False)
    checks.append(("weights_unchanged_sum", abs(sum(weights.values()) - 1.0) < 0.001))
    checks.append(("weights_match_default", weights == DEFAULT_FACTOR_WEIGHTS))
    checks.append(("tactics_weight_12", weights.get("tactics_matchup") == 0.12))
    checks.append(("max_xg_delta_cap", MAX_XG_TACTICS_SCORE_DELTA == 6.0))
    checks.append(("max_sm_conf_reduce", MAX_SPORTMONKS_CONFIDENCE_REDUCE == 6.0))
    checks.append(("cumulative_conf_cap", MAX_CUMULATIVE_PROMOTION_CONF_DELTA == 6.0))
    checks.append(("xg_factor_key", XG_PROMOTION_FACTOR_KEY == "tactics_matchup"))

    out_off, xg_off, sm_off, score_off, trace_off, conf_off = _run_wde("off", "off")
    checks.append(("off_xg_inactive", not xg_off.xg_promotion_active))
    checks.append(("off_sm_inactive", not sm_off.sportmonks_promotion_active))
    checks.append(("off_xg_delta_zero", xg_off.xg_delta_score == 0.0))

    out_shadow, xg_shadow, sm_shadow, score_shadow, trace_shadow, conf_shadow = _run_wde("shadow", "shadow")
    checks.append(("shadow_xg_active", xg_shadow.xg_promotion_active))
    checks.append(("shadow_xg_not_applied", xg_shadow.mode == "shadow" and not xg_shadow.applied))
    checks.append(("shadow_xg_delta_nonzero", xg_shadow.xg_delta_score != 0.0))
    checks.append(("shadow_tactics_unchanged", score_shadow == score_off))
    checks.append(("shadow_xg_bounded", abs(xg_shadow.xg_delta_score) <= MAX_XG_TACTICS_SCORE_DELTA))
    checks.append(("shadow_sm_active", sm_shadow.sportmonks_promotion_active))
    checks.append(("shadow_sm_not_applied", sm_shadow.mode == "shadow" and not sm_shadow.applied))
    checks.append(("shadow_sm_disagreement", sm_shadow.sportmonks_disagreement_signal != ""))
    checks.append(("shadow_conf_unchanged", conf_shadow == conf_off))
    checks.append(("shadow_trace_xg_reason", trace_shadow.xg_promotion_reason != ""))

    out_gated, xg_gated, sm_gated, score_gated, trace_gated, conf_gated = _run_wde("gated", "gated")
    checks.append(("gated_xg_applied", xg_gated.applied))
    checks.append(("gated_tactics_changed", score_gated != score_off))
    checks.append(
        (
            "gated_xg_expected_score",
            abs(float(score_gated) - xg_gated.promoted_tactics_score) < 0.11,
        )
    )
    checks.append(("gated_sm_applied", sm_gated.applied))
    checks.append(("gated_sm_conf_delta", sm_gated.sportmonks_confidence_delta == -3.0))
    checks.append(
        (
            "gated_conf_promotion_applied",
            trace_gated.combined_promotion_confidence_delta <= -2.0,
        )
    )
    checks.append(("gated_combined_conf_trace", trace_gated.combined_promotion_confidence_delta != 0.0))
    checks.append(("gated_no_winner_flip", out_gated.markets["1x2"].selection == out_off.markets["1x2"].selection))
    checks.append(("gated_no_auto_nobet", out_gated.no_bet_flag == out_off.no_bet_flag))
    checks.append(
        (
            "before_after_xg_delta",
            abs(xg_gated.xg_delta_score - round(float(score_gated) - float(score_off), 2)) <= 0.11,
        )
    )

    from worldcup_predictor.promotion.shadow_store import (
        SportmonksPredictionPromotionShadowStore,
        XGPromotionShadowStore,
    )

    xg_path = Path("data/shadow/_phase24c_test_xg_shadow.jsonl")
    sm_path = Path("data/shadow/_phase24c_test_sm_shadow.jsonl")
    for p in (xg_path, sm_path):
        if p.exists():
            p.unlink()
    os.environ["XG_PROMOTION_SHADOW_PATH"] = str(xg_path)
    os.environ["SPORTMONKS_PREDICTION_PROMOTION_SHADOW_PATH"] = str(sm_path)
    from worldcup_predictor.config.settings import get_settings

    get_settings.cache_clear()
    _run_wde("shadow", "shadow")
    checks.append(("xg_shadow_store_written", len(XGPromotionShadowStore(xg_path).load_all()) >= 1))
    checks.append(("sm_shadow_store_written", len(SportmonksPredictionPromotionShadowStore(sm_path).load_all()) >= 1))

    failed = [name for name, ok in checks if not ok]
    passed = len(checks) - len(failed)
    print(f"Phase 24C xG + Sportmonks promotion: {passed}/{len(checks)} passed")
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        print("Failed:", ", ".join(failed))
        print(
            f"  off tactics={score_off} xg delta={xg_shadow.xg_delta_score} "
            f"gated tactics={score_gated} conf {conf_off}->{conf_gated}"
        )
        return 1
    print(
        f"  baseline tactics={score_off} xg delta={xg_gated.xg_delta_score} "
        f"gated tactics={score_gated} conf {conf_off}->{conf_gated} sm_delta={sm_gated.sportmonks_confidence_delta}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
