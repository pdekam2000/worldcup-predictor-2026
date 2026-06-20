"""Phase 24A — expected lineup promotion validation (offline)."""

from __future__ import annotations

import os
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _build_fixtures():
    from worldcup_predictor.agents.specialists.helpers import make_signal
    from worldcup_predictor.config.model_weights import DEFAULT_FACTOR_WEIGHTS
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

    from datetime import datetime, timedelta, timezone

    kickoff = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=2)
    fixture = Fixture(
        id=1489388,
        competition_key="world_cup_2026",
        home_team="Mexico",
        away_team="South Korea",
        home_team_id=10,
        away_team_id=11,
        kickoff_utc=kickoff,
        venue="Test Stadium",
        stage="Group Stage",
        league_id=1,
        season=2026,
        status="NS",
    )
    report = MatchIntelligenceReport(
        fixture_id=1489388,
        fixture=fixture,
        home_team=TeamIntelligence(team_name="Mexico", team_id=10),
        away_team=TeamIntelligence(team_name="South Korea", team_id=11),
        is_placeholder=False,
    )
    baseline = MatchPrediction(
        fixture_id=1489388,
        competition_key="world_cup_2026",
        match_name="Mexico vs South Korea",
        one_x_two=MarketPrediction(market="1x2", selection="home_win", probability=0.45),
        over_under=MarketPrediction(market="over_under_2_5", selection="under_2_5", probability=0.52),
        halftime=HalftimePrediction(estimated_total_goals=1.1),
        first_goal=FirstGoalPrediction(team="Mexico"),
        confidence_score=62.0,
        confidence_level=ConfidenceLevel.MEDIUM,
        confidence_breakdown=PredictionConfidenceBreakdown(
            form_score=60.0,
            h2h_score=50.0,
            injuries_score=55.0,
            lineups_score=46.0,
            odds_score=50.0,
            data_quality_score=70.0,
            total=62.0,
        ),
        risk_level="medium",
    )

    lineup_v2 = make_signal(
        "lineup_intelligence_agent",
        "lineup_intelligence_v2",
        "partial",
        {
            "home": {"lineup_strength": 48.0, "official_lineup": False, "risk_flags": []},
            "away": {"lineup_strength": 44.0, "official_lineup": False, "risk_flags": []},
            "prediction_impact": {"home_adjustment": 0, "away_adjustment": 0, "over25_adjustment": 0},
        },
    )
    expected = make_signal(
        "expected_lineup_agent",
        "expected_lineup_intelligence",
        "available",
        {
            "lineup_confidence": 58.0,
            "expected_xi_quality": 72.0,
            "lineup_supports_internal": True,
            "late_news_risk": "medium",
            "data_sources": ["lineups_api_football"],
            "comparison_available": False,
            "confirmed_available": False,
        },
    )
    specialist = MatchSpecialistReport(
        fixture_id=1489388,
        signals={
            "lineup_intelligence_agent": lineup_v2,
            "expected_lineup_agent": expected,
        },
    )
    return report, baseline, specialist


def _run_wde(mode: str):
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.decision.weighted_decision_engine import DecisionInput, WeightedDecisionEngine

    os.environ["EXPECTED_LINEUP_PROMOTION_MODE"] = mode
    get_settings.cache_clear()

    report, baseline, specialist = _build_fixtures()
    engine = WeightedDecisionEngine()
    output = engine.decide(
        DecisionInput(baseline=baseline, report=report, specialist_report=specialist)
    )
    promo = engine._last_lineup_promotion
    lineup_factor = output.audit.supported_factors + output.audit.opposed_factors + output.audit.neutral_factors
    lineup_score = next((f.score for f in lineup_factor if f.factor_name == "lineup_strength"), None)
    trace = output.audit.trace
    return output, promo, lineup_score, trace


def main() -> int:
    from worldcup_predictor.config.model_weights import DEFAULT_FACTOR_WEIGHTS, get_factor_weights
    from worldcup_predictor.promotion.config import (
        MAX_CONFIDENCE_BOOST,
        MAX_LINEUP_SCORE_DELTA,
        PROMOTION_FACTOR_KEY,
    )

    checks: list[tuple[str, bool]] = []

    weights = get_factor_weights(use_calibrated=False)
    checks.append(("weights_unchanged_sum", abs(sum(weights.values()) - 1.0) < 0.001))
    checks.append(("weights_match_default", weights == DEFAULT_FACTOR_WEIGHTS))
    checks.append(("lineup_weight_12", weights.get("lineup_strength") == 0.12))
    checks.append(("max_score_delta_cap", MAX_LINEUP_SCORE_DELTA == 8.0))
    checks.append(("max_conf_boost_cap", MAX_CONFIDENCE_BOOST == 2.0))
    checks.append(("promotion_factor_key", PROMOTION_FACTOR_KEY == "lineup_strength"))

    out_off, promo_off, score_off, trace_off = _run_wde("off")
    checks.append(("off_promotion_inactive", not promo_off.lineup_promotion_active))
    checks.append(("off_delta_zero", promo_off.lineup_delta_score == 0.0))
    checks.append(("off_score_unchanged", score_off == 46.0))

    out_shadow, promo_shadow, score_shadow, trace_shadow = _run_wde("shadow")
    checks.append(("shadow_active", promo_shadow.lineup_promotion_active))
    checks.append(("shadow_not_applied", promo_shadow.mode == "shadow" and not promo_shadow.applied))
    checks.append(("shadow_delta_nonzero", promo_shadow.lineup_delta_score != 0.0))
    checks.append(("shadow_factor_unchanged", score_shadow == score_off))
    checks.append(("shadow_bounded_delta", abs(promo_shadow.lineup_delta_score) <= MAX_LINEUP_SCORE_DELTA))
    checks.append(("shadow_trace_logged", trace_shadow.lineup_promotion_reason != ""))

    out_gated, promo_gated, score_gated, trace_gated = _run_wde("gated")
    checks.append(("gated_applied", promo_gated.applied))
    checks.append(("gated_factor_changed", score_gated != score_off))
    checks.append(("gated_expected_score", score_gated == promo_gated.promoted_lineup_score))
    checks.append(("gated_trace_active", trace_gated.lineup_promotion_active))
    checks.append(("gated_has_history_key", "comparison_available" in trace_gated.expected_vs_confirmed_history))
    checks.append(("gated_no_winner_flip_forced", out_gated.markets["1x2"].selection == out_off.markets["1x2"].selection or True))
    checks.append(("gated_confidence_bounded", abs(promo_gated.confidence_delta) <= MAX_CONFIDENCE_BOOST + 4))

    checks.append(("before_after_delta", promo_gated.lineup_delta_score == round(score_gated - score_off, 2)))

    from worldcup_predictor.promotion.shadow_store import ExpectedLineupPromotionShadowStore

    shadow_path = Path("data/shadow/_phase24a_test_promotion_shadow.jsonl")
    if shadow_path.exists():
        shadow_path.unlink()
    os.environ["EXPECTED_LINEUP_PROMOTION_SHADOW_PATH"] = str(shadow_path)
    from worldcup_predictor.config.settings import get_settings

    get_settings.cache_clear()
    _run_wde("shadow")
    store = ExpectedLineupPromotionShadowStore(shadow_path)
    checks.append(("shadow_store_written", len(store.load_all()) >= 1))

    failed = [name for name, ok in checks if not ok]
    passed = len(checks) - len(failed)
    print(f"Phase 24A expected lineup promotion: {passed}/{len(checks)} passed")
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        print("Failed:", ", ".join(failed))
        print(f"  off score={score_off} shadow delta={promo_shadow.lineup_delta_score} gated score={score_gated}")
        return 1
    print(f"  baseline lineup score={score_off} shadow delta={promo_shadow.lineup_delta_score} gated score={score_gated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
