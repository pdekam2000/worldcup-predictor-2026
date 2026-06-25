"""Phase 36B — placeholder prediction repair validation."""

from __future__ import annotations

import json
import runpy
import time
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nPhase 36B validation: {passed}/{len(checks)} PASS")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print()


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    from worldcup_predictor.automation.worldcup_background.prediction_runner import run_and_store_prediction
    from worldcup_predictor.automation.worldcup_background.prediction_store import WorldcupPredictionStore
    from worldcup_predictor.automation.worldcup_background.stale_prediction_policy import (
        is_stored_prediction_quality_valid,
        should_invalidate_stored_row,
    )
    from worldcup_predictor.config.provider_readiness import assert_production_api_football, provider_diagnostic
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    from worldcup_predictor.quota.prediction_cache import get_cached_prediction

    fid = 1489393
    get_settings.cache_clear()
    settings = get_settings()

    try:
        assert_production_api_football(settings)
        record("api_football_required", True)
    except Exception as exc:
        record("api_football_required", False, str(exc))

    diag = provider_diagnostic(settings)
    record("diagnostic_api_football_yes_no", diag["API_FOOTBALL_KEY_present"] is True)
    record("no_secrets_in_diagnostic", "633c1b49" not in json.dumps(diag))

    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    row = repo.get_fixture_row(fid)
    record("fixture_1489393_exists", row is not None)

    placeholder_payload = {
        "status": "ok",
        "fixture_id": fid,
        "confidence": 3.0,
        "prediction_engine_version": "34b-v1",
        "adaptive_confidence_version": "1-v1",
        "national_team_intelligence": {"version": "32e"},
        "is_placeholder": True,
        "provider_env_missing": True,
        "generated_by": "phase34b_test",
        "probabilities": {"home_win": 51.7, "draw": 23.6, "away_win": 24.7},
        "adaptive_confidence_trace": {"confidence_before_adaptive": 11.5, "confidence_after_adaptive": 13.0},
        "audit_trace": {"confidence": {"no_bet_reasons": ["placeholder_data"], "final": 11.5}},
    }
    should_inv, inv_reason = should_invalidate_stored_row(placeholder_payload, source="phase34b_test_fresh")
    record("detects_bad_placeholder_row", should_inv, inv_reason)

    ok_before, _ = is_stored_prediction_quality_valid(placeholder_payload)
    record("placeholder_payload_not_served", not ok_before)

    # Clear file cache so store.get reflects SQLite quality gate only
    from worldcup_predictor.cache.api_cache import ApiCache

    cache = ApiCache(Path(settings.prediction_cache_dir), default_ttl_seconds=3600)
    key = ApiCache.build_key(
        "prediction_result",
        {"fixture_id": fid, "competition": "world_cup_2026", "season": 2026, "locale": "en"},
    )
    cache._path_for(key).unlink(missing_ok=True)

    repo.upsert_worldcup_stored_prediction(
        fixture_id=fid,
        payload=placeholder_payload,
        kickoff_utc=str(row.get("kickoff_utc") if row else "2026-06-20T20:00:00"),
        source="phase36b_test_stale",
    )
    store = WorldcupPredictionStore(settings)
    served_bad = store.get(fixture_id=fid)
    record("stale_placeholder_not_served", served_bad is None)

    repo.invalidate_worldcup_stored_prediction(fid, reason="provider_env_missing_placeholder")

    payload = run_and_store_prediction(fid, settings=settings, source="phase36b_validation", record_history=False)
    record("repair_pipeline_success", payload.get("status") != "error")
    conf = float(payload.get("confidence") or 0)
    record("confidence_not_placeholder_3", conf > 15.0, f"conf={conf}")
    record("is_placeholder_false", payload.get("is_placeholder") is False, str(payload.get("is_placeholder")))
    readiness = payload.get("provider_readiness") or {}
    record("provider_readiness_stamped", readiness.get("api_football_configured") is True)
    record("engine_version_34b", payload.get("prediction_engine_version") == "34b-v1")
    record("nat_intel_32e", (payload.get("national_team_intelligence") or {}).get("version") == "32e")
    record("adaptive_trace_present", isinstance(payload.get("adaptive_confidence_trace"), dict))

    ok_after, reason_after = is_stored_prediction_quality_valid(payload)
    record("repaired_payload_valid", ok_after, reason_after)

    served = store.get(fixture_id=fid)
    record("sqlite_serves_repaired", served is not None)
    record("cache_reuse_confidence", served is not None and float(served.get("confidence") or 0) > 15.0)

    file_hit = get_cached_prediction(fid, competition_key="world_cup_2026", season=2026, locale="en", settings=settings)
    record("file_cache_reuse", file_hit is not None and float(file_hit.get("confidence") or 0) > 15.0)

    if served and file_hit:
        record("second_request_same_confidence", abs(float(served.get("confidence") or 0) - float(file_hit.get("confidence") or 0)) < 0.2)

    _report(checks)
    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
