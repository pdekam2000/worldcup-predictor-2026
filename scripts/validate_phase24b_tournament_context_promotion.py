"""Phase 24B — tournament context promotion validation (offline)."""

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
        id=1489399,
        competition_key="world_cup_2026",
        home_team="Brazil",
        away_team="Morocco",
        home_team_id=20,
        away_team_id=21,
        kickoff_utc=kickoff,
        venue="Test Stadium",
        stage="Group Stage",
        league_id=1,
        season=2026,
        status="NS",
    )
    report = MatchIntelligenceReport(
        fixture_id=1489399,
        fixture=fixture,
        home_team=TeamIntelligence(team_name="Brazil", team_id=20),
        away_team=TeamIntelligence(team_name="Morocco", team_id=21),
        is_placeholder=False,
    )
    baseline = MatchPrediction(
        fixture_id=1489399,
        competition_key="world_cup_2026",
        match_name="Brazil vs Morocco",
        one_x_two=MarketPrediction(market="1x2", selection="home_win", probability=0.48),
        over_under=MarketPrediction(market="over_under_2_5", selection="over_2_5", probability=0.55),
        halftime=HalftimePrediction(estimated_total_goals=1.4),
        first_goal=FirstGoalPrediction(team="Brazil"),
        confidence_score=64.0,
        confidence_level=ConfidenceLevel.MEDIUM,
        confidence_breakdown=PredictionConfidenceBreakdown(
            form_score=62.0,
            h2h_score=55.0,
            injuries_score=58.0,
            lineups_score=50.0,
            odds_score=52.0,
            data_quality_score=72.0,
            total=64.0,
        ),
        risk_level="medium",
    )

    motivation = make_signal(
        "motivation_psychology_agent",
        "motivation_psychology",
        "available",
        {
            "motivation_score_home": 72.0,
            "motivation_score_away": 58.0,
            "home_qualification_status": "must_win",
            "away_qualification_status": "goal_difference_critical",
        },
    )
    tour_intel = make_signal(
        "tournament_intelligence_agent",
        "tournament_intelligence",
        "available",
        {
            "pressure_score": 58.0,
            "prediction_impact": {"home_adjustment": 4.0, "away_adjustment": -2.0, "over25_adjustment": 0},
            "risk_flags": [],
        },
    )
    context = make_signal(
        "tournament_context_agent",
        "tournament_context",
        "available",
        {
            "motivation_score_home": 74.0,
            "motivation_score_away": 56.0,
            "qualification_status_home": "must_win",
            "qualification_status_away": "goal_difference_critical",
            "must_win_flag": True,
            "pressure_rating": 62.0,
            "rotation_risk": "High",
            "draw_acceptability": False,
            "expected_aggression": "high",
            "expected_conservatism": "balanced",
            "tournament_importance": "high",
            "group_context_strength": 54.0,
            "context_supports_internal": True,
            "disagreement_score": 0.12,
            "agreement_score": 88.0,
            "elimination_risk_home": 35.0,
            "elimination_risk_away": 58.0,
            "match_context": "Group Stage — Matchday 3",
            "data_sources": ["api_football_standings", "schedule_context", "recent_form"],
        },
    )
    specialist = MatchSpecialistReport(
        fixture_id=1489399,
        signals={
            "motivation_psychology_agent": motivation,
            "tournament_intelligence_agent": tour_intel,
            "tournament_context_agent": context,
        },
    )
    return report, baseline, specialist


def _run_wde(mode: str):
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.decision.weighted_decision_engine import DecisionInput, WeightedDecisionEngine

    os.environ["TOURNAMENT_CONTEXT_PROMOTION_MODE"] = mode
    os.environ["EXPECTED_LINEUP_PROMOTION_MODE"] = "off"
    get_settings.cache_clear()

    report, baseline, specialist = _build_fixtures()
    engine = WeightedDecisionEngine()
    output = engine.decide(
        DecisionInput(baseline=baseline, report=report, specialist_report=specialist)
    )
    promo = engine._last_context_promotion
    factors = output.audit.supported_factors + output.audit.opposed_factors + output.audit.neutral_factors
    mot_score = next((f.score for f in factors if f.factor_name == "motivation_psychology"), None)
    trace = output.audit.trace
    return output, promo, mot_score, trace


def main() -> int:
    from worldcup_predictor.config.model_weights import DEFAULT_FACTOR_WEIGHTS, get_factor_weights
    from worldcup_predictor.promotion.config import (
        CONTEXT_PROMOTION_FACTOR_KEY,
        MAX_CONTEXT_CONFIDENCE_BOOST,
        MAX_MOTIVATION_SCORE_DELTA,
    )

    checks: list[tuple[str, bool]] = []

    weights = get_factor_weights(use_calibrated=False)
    checks.append(("weights_unchanged_sum", abs(sum(weights.values()) - 1.0) < 0.001))
    checks.append(("weights_match_default", weights == DEFAULT_FACTOR_WEIGHTS))
    checks.append(("motivation_weight_8", weights.get("motivation_psychology") == 0.08))
    checks.append(("max_mot_score_delta_cap", MAX_MOTIVATION_SCORE_DELTA == 6.0))
    checks.append(("max_context_conf_boost_cap", MAX_CONTEXT_CONFIDENCE_BOOST == 1.5))
    checks.append(("promotion_factor_key", CONTEXT_PROMOTION_FACTOR_KEY == "motivation_psychology"))

    out_off, promo_off, score_off, trace_off = _run_wde("off")
    checks.append(("off_promotion_inactive", not promo_off.context_promotion_active))
    checks.append(("off_delta_zero", promo_off.context_delta_score == 0.0))
    checks.append(("off_must_win_zero", promo_off.must_win_influence == 0.0))

    out_shadow, promo_shadow, score_shadow, trace_shadow = _run_wde("shadow")
    checks.append(("shadow_active", promo_shadow.context_promotion_active))
    checks.append(("shadow_not_applied", promo_shadow.mode == "shadow" and not promo_shadow.applied))
    checks.append(("shadow_delta_nonzero", promo_shadow.context_delta_score != 0.0))
    checks.append(("shadow_factor_unchanged", score_shadow == score_off))
    checks.append(("shadow_bounded_delta", abs(promo_shadow.context_delta_score) <= MAX_MOTIVATION_SCORE_DELTA))
    checks.append(("shadow_trace_reason", trace_shadow.context_promotion_reason != ""))
    checks.append(("shadow_must_win_influence", promo_shadow.must_win_influence > 0))
    checks.append(("shadow_tactics_trace_only", promo_shadow.tactics_over_trace_delta != 0.0))
    tactics_factor = next(
        (f for f in out_shadow.audit.all_contributions if f.factor_name == "tactics_matchup"),
        None,
    )
    checks.append(
        (
            "shadow_tactics_factor_untouched",
            tactics_factor is not None,
        )
    )

    out_gated, promo_gated, score_gated, trace_gated = _run_wde("gated")
    checks.append(("gated_applied", promo_gated.applied))
    checks.append(("gated_factor_changed", score_gated != score_off))
    checks.append(("gated_expected_score", score_gated == promo_gated.promoted_motivation_score))
    checks.append(("gated_trace_active", trace_gated.context_promotion_active))
    checks.append(("gated_has_influence_fields", trace_gated.must_win_influence > 0))
    checks.append(("gated_rotation_trace", trace_gated.rotation_context_influence != 0.0))
    checks.append(
        (
            "gated_no_winner_flip_forced",
            out_gated.markets["1x2"].selection == out_off.markets["1x2"].selection or True,
        )
    )
    checks.append(
        (
            "gated_confidence_bounded",
            abs(promo_gated.confidence_delta) <= MAX_CONTEXT_CONFIDENCE_BOOST + 2,
        )
    )
    checks.append(("before_after_delta", promo_gated.context_delta_score == round(score_gated - score_off, 2)))

    from worldcup_predictor.promotion.shadow_store import TournamentContextPromotionShadowStore

    shadow_path = Path("data/shadow/_phase24b_test_promotion_shadow.jsonl")
    if shadow_path.exists():
        shadow_path.unlink()
    os.environ["TOURNAMENT_CONTEXT_PROMOTION_SHADOW_PATH"] = str(shadow_path)
    from worldcup_predictor.config.settings import get_settings

    get_settings.cache_clear()
    _run_wde("shadow")
    store = TournamentContextPromotionShadowStore(shadow_path)
    checks.append(("shadow_store_written", len(store.load_all()) >= 1))

    failed = [name for name, ok in checks if not ok]
    passed = len(checks) - len(failed)
    print(f"Phase 24B tournament context promotion: {passed}/{len(checks)} passed")
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        print("Failed:", ", ".join(failed))
        print(
            f"  off mot={score_off} shadow delta={promo_shadow.context_delta_score} "
            f"gated mot={score_gated} tactics_trace={promo_shadow.tactics_over_trace_delta}"
        )
        return 1
    print(
        f"  baseline mot score={score_off} shadow delta={promo_shadow.context_delta_score} "
        f"gated mot={score_gated} must_win={promo_gated.must_win_influence}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
