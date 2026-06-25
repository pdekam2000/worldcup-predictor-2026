"""Phase 34B — Stale confidence cache fix validation."""

from __future__ import annotations

import json
import runpy
import time
import uuid
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nPhase 34B validation: {passed}/{len(checks)} PASS")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print()


def _stale_germany_payload() -> dict:
    """Simulates production stale fixture 1489393 cache."""
    return {
        "status": "ok",
        "fixture_id": 1489393,
        "home_team": "Germany",
        "away_team": "Ivory Coast",
        "confidence": 3.0,
        "prediction": "draw",
        "no_bet": True,
        "pick_tier": "caution",
        "data_quality": 65.0,
        "cache_source": "background_daily",
        "cached_at": time.time() - 3600,
        "probabilities": {"home_win": 51.7, "draw": 23.6, "away_win": 24.7},
        "national_team_intelligence": {"version": "32e", "national_form_score": 47.2},
        "audit_trace": {
            "confidence": {
                "baseline": 27.5,
                "final": 11.5,
                "no_bet_reasons": ["placeholder_data", "confidence_below_60"],
            }
        },
    }


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    from worldcup_predictor.automation.worldcup_background.stale_prediction_policy import (
        is_stored_prediction_quality_valid,
    )
    from worldcup_predictor.api.prediction_metadata import (
        build_adaptive_confidence_trace,
        stamp_prediction_engine_metadata,
    )
    from worldcup_predictor.automation.worldcup_background.prediction_store import WorldcupPredictionStore
    from worldcup_predictor.config.provider_readiness import assert_production_api_football, ProductionProviderEnvError
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline
    from worldcup_predictor.prediction.engine_versions import (
        ADAPTIVE_CONFIDENCE_VERSION,
        NATIONAL_TEAM_INTELLIGENCE_VERSION,
        PREDICTION_ENGINE_VERSION,
    )
    from worldcup_predictor.quota.prediction_cache import get_cached_prediction, store_prediction

    stale = _stale_germany_payload()
    ok, reason = is_stored_prediction_quality_valid(stale)
    record("stale_payload_invalidated", not ok, reason)
    record("stale_reason_engine_or_placeholder", "engine_version" in reason or "placeholder" in reason or "adaptive" in reason or "mismatch" in reason)

    get_settings.cache_clear()
    settings = get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    store = WorldcupPredictionStore(settings)

    try:
        assert_production_api_football(settings)
        record("production_provider_env_present", True)
    except ProductionProviderEnvError as exc:
        record("production_provider_env_present", False, str(exc))
        _report(checks)
        return 1

    fid = 1489393
    row = repo.get_fixture_row(fid)
    record("fixture_1489393_exists", row is not None)

    # Upsert stale payload then confirm store rejects it
    repo.upsert_worldcup_stored_prediction(
        fixture_id=fid,
        payload=stale,
        kickoff_utc=str(row.get("kickoff_utc") if row else "2026-06-20T20:00:00"),
        source="phase34b_test_stale",
    )
    cached_stale = store.get(fixture_id=fid)
    record("stale_sqlite_not_served", cached_stale is None)

    # Fresh pipeline + store
    pipeline = PredictPipeline(settings)
    result = pipeline.run(fixture_id=fid, record_history=False)
    record("pipeline_success", result.success)

    if result.success:
        from worldcup_predictor.automation.worldcup_background.prediction_runner import build_api_payload

        fresh = build_api_payload(result, intelligence_report=result.intelligence_report, specialist_report=result.specialist_report)
        from worldcup_predictor.api.prediction_metadata import stamp_prediction_engine_metadata

        fresh = stamp_prediction_engine_metadata(fresh, prediction=result.prediction, generated_by="phase34b_test")
        fresh["cached_at"] = time.time()
        fresh["kickoff_utc"] = str(row.get("kickoff_utc") if row else fresh.get("kickoff_utc"))

        record("engine_version_stamped", fresh.get("prediction_engine_version") == PREDICTION_ENGINE_VERSION)
        record("nat_intel_32e", (fresh.get("national_team_intelligence") or {}).get("version") == NATIONAL_TEAM_INTELLIGENCE_VERSION)
        record("adaptive_version_stamped", fresh.get("adaptive_confidence_version") == ADAPTIVE_CONFIDENCE_VERSION)
        record("adaptive_trace_present", isinstance(fresh.get("adaptive_confidence_trace"), dict))
        record("confidence_not_placeholder_3", float(fresh.get("confidence") or 0) > 15.0, f"conf={fresh.get('confidence')}")
        record("not_provider_placeholder", fresh.get("is_placeholder") is False and not fresh.get("provider_env_missing"))
        record("provider_readiness_stamped", bool((fresh.get("provider_readiness") or {}).get("api_football_configured")))

        trace = fresh.get("adaptive_confidence_trace") or {}
        record("adaptive_before_after", "confidence_before_adaptive" in trace and "confidence_after_adaptive" in trace)

        ok2, reason2 = is_stored_prediction_quality_valid(fresh)
        record("fresh_payload_valid", ok2, reason2)

        repo.upsert_worldcup_stored_prediction(
            fixture_id=fid,
            payload=fresh,
            kickoff_utc=fresh.get("kickoff_utc"),
            source="phase34b_test_fresh",
        )
        served = store.get(fixture_id=fid)
        record("fresh_sqlite_served", served is not None)
        record("served_confidence_fresh", served is not None and float(served.get("confidence") or 0) > 15.0)

        dup_before = repo._conn.execute(
            "SELECT COUNT(*) AS c FROM worldcup_stored_predictions WHERE fixture_id = ?", (fid,)
        ).fetchone()["c"]
        repo.upsert_worldcup_stored_prediction(
            fixture_id=fid, payload=fresh, kickoff_utc=fresh.get("kickoff_utc"), source="phase34b_test_fresh",
        )
        dup_after = repo._conn.execute(
            "SELECT COUNT(*) AS c FROM worldcup_stored_predictions WHERE fixture_id = ?", (fid,)
        ).fetchone()["c"]
        record("no_duplicate_rows", dup_before == 1 and dup_after == 1)

        comp = get_settings()
        store_prediction(
            fid,
            fresh,
            competition_key="world_cup_2026",
            season=2026,
            locale="en",
            settings=settings,
        )
        file_hit = get_cached_prediction(fid, competition_key="world_cup_2026", season=2026, locale="en", settings=settings)
        record("file_cache_reuse", file_hit is not None and file_hit.get("prediction_engine_version") == PREDICTION_ENGINE_VERSION)

        adj = build_adaptive_confidence_trace(result.prediction)
        record("adaptive_trace_from_prediction", adj is not None and "adaptive_adjustment" in adj)
    else:
        for name in (
            "engine_version_stamped", "nat_intel_32e", "adaptive_trace_present",
            "confidence_not_stale_3", "fresh_sqlite_served", "pipeline_success",
        ):
            record(name, False, "pipeline failed")

    _report(checks)
    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
