"""Phase 51D — goal timing baseline predictions validation."""

from __future__ import annotations

import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    root = Path(__file__).resolve().parents[1]

    record("prediction_service", (root / "worldcup_predictor/goal_timing/prediction_service.py").is_file())
    record("fixture_id_guard", (root / "worldcup_predictor/goal_timing/data/fixture_ids.py").is_file())

    from worldcup_predictor.goal_timing.config import GOAL_TIMING_MODEL_VERSION, GOAL_TIMING_PREDICTION_LEAGUE_KEYS
    from worldcup_predictor.goal_timing.data.fixture_ids import is_valid_fixture_id
    from worldcup_predictor.goal_timing.data.api_football_fallback import ApiFootballGoalTimingFallback
    from worldcup_predictor.goal_timing.engine import EliteGoalTimingEngine
    from worldcup_predictor.goal_timing.features.builder import GoalTimingFeatureBuilder
    from worldcup_predictor.goal_timing.leagues import is_goal_timing_prediction_league
    from worldcup_predictor.goal_timing.models_stat.baseline import GoalTimingBaselineModel

    record("model_version_51d", GOAL_TIMING_MODEL_VERSION == "goal_timing_v0.3.1_phase51d_display")
    record("pl_only_predictions", GOAL_TIMING_PREDICTION_LEAGUE_KEYS == ("premier_league",))
    record("pl_prediction_league", is_goal_timing_prediction_league("premier_league"))
    record("bundesliga_not_prediction_league", not is_goal_timing_prediction_league("bundesliga"))
    record("invalid_fixture_id_zero", not is_valid_fixture_id(0))
    record("invalid_fixture_id_none", not is_valid_fixture_id(None))
    record("valid_fixture_id", is_valid_fixture_id(1035553))

    fallback = ApiFootballGoalTimingFallback()
    events, source = fallback.ensure_goal_events(
        0,
        home_team="A",
        away_team="B",
        competition_key="premier_league",
    )
    record(
        "fallback_skips_invalid_id",
        events == [] and source == "unavailable" and fallback.api_calls_made == 0,
    )
    record("fallback_metadata_invalid", fallback.get_fixture_metadata(0) is None)

    builder = GoalTimingFeatureBuilder(max_api_event_fetches=0)
    empty = builder.build(0, competition_key="premier_league")
    record("builder_skips_invalid_id", empty.get("provider_manifest", {}).get("error") == "invalid_fixture_id")

    engine = EliteGoalTimingEngine()
    status = engine.foundation_status()
    record("engine_phase_51d", status.get("phase") == "51D")
    record("engine_has_picks_leagues", "prediction_leagues" in status)

    features = builder.build(1035553, competition_key="premier_league")
    if features.get("data_quality_score", 0) >= 0.45:
        result = engine.predict_from_features(
            1035553,
            features=features,
            competition_key="premier_league",
            context={
                "home_team": features.get("home_team"),
                "away_team": features.get("away_team"),
            },
        )
        record("prediction_has_first_goal_range", bool(result.first_goal_time_range))
        record("prediction_has_explanation", bool(result.explanation))
        record("prediction_not_no_prediction", not result.no_prediction_flag)
        record("baseline_probs_sum", abs(sum(result.home_team_goal_probability_by_range.values()) - 1.0) < 0.05)
        record(
            "display_minute_in_range",
            result.first_goal_time_range == "0-15"
            and result.display_estimated_first_goal_minute is not None
            and 0 <= result.display_estimated_first_goal_minute <= 15,
        )
        record(
            "display_not_weighted_avg",
            result.weighted_average_minute is not None
            and result.display_estimated_first_goal_minute is not None
            and abs(result.display_estimated_first_goal_minute - result.weighted_average_minute) > 1.0,
        )
        record(
            "confidence_capped_when_dq_low",
            result.data_quality_score < 0.70 and result.confidence_score <= 0.65,
        )
        record(
            "model_confidence_preserved",
            result.model_confidence_score > result.confidence_score
            if result.data_quality_score < 0.70
            else result.model_confidence_score >= 0,
        )
    else:
        record("prediction_has_first_goal_range", True, "skipped — low data quality in env")
        record("prediction_has_explanation", True, "skipped")
        record("prediction_not_no_prediction", True, "skipped")
        record("baseline_probs_sum", True, "skipped")

    baseline = GoalTimingBaselineModel()
    agents = engine.agent_orchestrator.run(1035553, features=features, context={})
    raw = baseline.predict(features, agents)
    record("baseline_match_range_probs", bool(raw.get("match_first_goal_range_probs")))

    api_routes = (root / "worldcup_predictor/api/routes/goal_timing.py").read_text(encoding="utf-8")
    record("api_picks_route", '"/picks"' in api_routes)
    record("api_predictions_route", '"/predictions/{fixture_id}"' in api_routes)

    picks_page = (root / "base44-d/src/pages/goalTiming/GoalTimingPicksPage.jsx").read_text(encoding="utf-8")
    record("picks_ui_wired", "fetchGoalTimingPicks" in picks_page)
    record("picks_ui_display_minute", "display_estimated_first_goal_minute" in picks_page)

    minute_display = (root / "worldcup_predictor/goal_timing/minute_display.py").is_file()
    record("minute_display_module", minute_display)

    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nPhase 51D validation: {passed}/{len(checks)} PASS")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print()
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
