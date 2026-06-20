"""Validate Phase 27 fixes — cache schema, audit trace, specialist count."""

from __future__ import annotations

from pathlib import Path
import runpy
import sys
import tempfile

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def main() -> int:
    checks: list[tuple[str, bool]] = []
    try:
        from worldcup_predictor.agents.specialists.orchestrator import SpecialistOrchestrator
        from worldcup_predictor.api.audit_trace_helpers import build_audit_trace
        from worldcup_predictor.config.settings import Settings
        from worldcup_predictor.domain.prediction import (
            ConfidenceLevel,
            FirstGoalPrediction,
            HalftimePrediction,
            MarketPrediction,
            MatchPrediction,
            PredictionConfidenceBreakdown,
        )
        from worldcup_predictor.quota.prediction_cache import get_cached_prediction, store_prediction
        from worldcup_predictor.quota.prediction_cache_policy import (
            EXPECTED_SPECIALIST_AGENT_COUNT,
            PHASE_22_REQUIRED_AGENT_KEYS,
            PREDICTION_CACHE_SCHEMA_VERSION,
            is_prediction_cache_valid,
            stamp_prediction_cache,
        )

        def _full_agent_map() -> dict[str, dict[str, str]]:
            agents = {f"legacy_{i}": {"status": "available"} for i in range(EXPECTED_SPECIALIST_AGENT_COUNT - len(PHASE_22_REQUIRED_AGENT_KEYS))}
            for key in PHASE_22_REQUIRED_AGENT_KEYS:
                agents[key] = {"status": "available", "domain": key, "impact_score": "50.0"}
            return agents

        expected_count = len(SpecialistOrchestrator.AGENT_CLASSES) - 1
        checks.append(("expected_agent_count_22", EXPECTED_SPECIALIST_AGENT_COUNT == expected_count == 22))

        legacy_payload = {
            "status": "ok",
            "fixture_id": 1,
            "specialist_summary": {
                "agents": {f"agent_{i}": {"status": "available"} for i in range(18)},
            },
        }
        valid, reason = is_prediction_cache_valid(legacy_payload)
        checks.append(("legacy_18_agent_invalid", not valid and "schema" in reason))

        fresh_agents = _full_agent_map()

        fresh_payload = stamp_prediction_cache(
            {
                "status": "ok",
                "fixture_id": 99,
                "specialist_summary": {"agents": fresh_agents, "aggregated_score": 55.0},
                "prediction": "home",
                "confidence": 60,
            }
        )
        valid_fresh, _ = is_prediction_cache_valid(fresh_payload)
        checks.append(("fresh_22_agent_valid", valid_fresh))
        checks.append(
            ("stamped_schema_version", fresh_payload.get("cache_schema_version") == PREDICTION_CACHE_SCHEMA_VERSION)
        )

        settings = Settings(prediction_cache_dir=str(Path(tempfile.mkdtemp()) / "predictions"))
        store_prediction(
            99,
            fresh_payload,
            competition_key="world_cup_2026",
            season=2026,
            locale="en",
            settings=settings,
        )
        cached = get_cached_prediction(99, competition_key="world_cup_2026", season=2026, locale="en", settings=settings)
        checks.append(("cache_roundtrip_valid", cached is not None and cached.get("specialist_agent_count") == 22))

        store_prediction(
            100,
            legacy_payload,
            competition_key="world_cup_2026",
            season=2026,
            locale="en",
            settings=settings,
        )
        stale = get_cached_prediction(100, competition_key="world_cup_2026", season=2026, locale="en", settings=settings)
        checks.append(("legacy_cache_rejected", stale is None))

        prediction = MatchPrediction(
            fixture_id=99,
            competition_key="world_cup_2026",
            match_name="A vs B",
            one_x_two=MarketPrediction(market="1x2", selection="home_win", probability=0.5),
            over_under=MarketPrediction(market="over_under_2_5", selection="under_2_5", probability=0.5),
            halftime=HalftimePrediction(estimated_total_goals=1.0),
            first_goal=FirstGoalPrediction(team="A"),
            confidence_score=60.0,
            confidence_level=ConfidenceLevel.MEDIUM,
            confidence_breakdown=PredictionConfidenceBreakdown(
                form_score=50.0,
                h2h_score=50.0,
                injuries_score=50.0,
                lineups_score=50.0,
                odds_score=50.0,
                data_quality_score=50.0,
                total=60.0,
            ),
            risk_level="medium",
            metadata={"decision_engine": "weighted", "lineup_promotion_active": "False"},
        )
        trace = build_audit_trace(prediction, fresh_payload["specialist_summary"], settings=settings)
        checks.append(("audit_trace_shape", "promotion_modes" in trace and "expected_lineup" in trace))
        checks.append(
            ("audit_trace_shadow_modes", trace["promotion_modes"]["expected_lineup"] == "shadow")
        )
        checks.append(
            ("audit_trace_no_secrets", "api_key" not in str(trace).lower() and "token" not in str(trace).lower())
        )

        from types import SimpleNamespace

        from worldcup_predictor.providers.sportmonks_consumption import _resolve_raw_fixture_data

        report = SimpleNamespace(
            fixture_id=555,
            provider_metadata={"sportmonks_fixture": {"id": 1, "participants": []}},
        )
        _raw, source = _resolve_raw_fixture_data(report)  # type: ignore[arg-type]
        checks.append(("resolve_raw_import_ok", source in ("provider_metadata", "sqlite_cache_complete", "sqlite_cache", "none")))
    except Exception as exc:
        print(f"FAIL: {exc}")
        import traceback

        traceback.print_exc()
        return 1

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        print(f"\n{len(failed)} check(s) failed")
        return 1
    print(f"\nAll {len(checks)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
