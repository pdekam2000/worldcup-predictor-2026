"""Phase 36C — production env wiring validation."""

from __future__ import annotations

import os
import runpy
import tempfile
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nPhase 36C validation: {passed}/{len(checks)} PASS")
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

    from worldcup_predictor.config.env_loading import is_production_runtime, resolve_env_file
    from worldcup_predictor.config.provider_readiness import (
        ProductionProviderEnvError,
        assert_production_api_football,
        provider_diagnostic,
    )
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.automation.worldcup_background.prediction_store_guard import (
        evaluate_prediction_storage,
    )

    # Local/dev: .env should resolve when present
    get_settings.cache_clear()
    env_path = resolve_env_file()
    record("env_file_resolves", env_path is not None, str(env_path) if env_path else "none")

    settings = get_settings()
    diag = provider_diagnostic(settings)
    record("diagnostic_no_secret_values", all(
        not str(v).startswith("633c") and "g6Qg" not in str(v)
        for v in diag.values()
    ))
    record("api_football_present_local", diag["API_FOOTBALL_KEY_present"], diag["provider_readiness_summary"])

    # Production resolution simulation via ENV_FILE (absolute path)
    with tempfile.TemporaryDirectory() as tmp:
        prod = Path(tmp) / ".env.production"
        prod.write_text("API_FOOTBALL_KEY=test-key-for-validation-only\nAPP_ENV=production\n", encoding="utf-8")
        old_app = os.environ.get("APP_ENV")
        old_env_file = os.environ.get("ENV_FILE")
        old_key = os.environ.pop("API_FOOTBALL_KEY", None)
        try:
            os.environ.pop("APP_ENV", None)
            os.environ["ENV_FILE"] = str(prod.resolve())
            get_settings.cache_clear()
            from worldcup_predictor.config.env_loading import resolve_env_file, note_loaded_env_file

            resolved = resolve_env_file()
            record("explicit_env_file_selected", resolved == prod.resolve(), str(resolved))
            note_loaded_env_file(resolved)
            sim = get_settings()
            record("env_file_sim_api_key_loaded", sim.api_football_configured)
        finally:
            if old_app is None:
                os.environ.pop("APP_ENV", None)
            else:
                os.environ["APP_ENV"] = old_app
            if old_env_file is None:
                os.environ.pop("ENV_FILE", None)
            else:
                os.environ["ENV_FILE"] = old_env_file
            if old_key is not None:
                os.environ["API_FOOTBALL_KEY"] = old_key
            get_settings.cache_clear()

    try:
        assert_production_api_football(settings)
        record("assert_production_passes_with_key", True)
    except ProductionProviderEnvError as exc:
        record("assert_production_passes_with_key", False, str(exc))

    bad_payload = {
        "status": "ok",
        "fixture_id": 1,
        "confidence": 3.0,
        "is_placeholder": True,
        "provider_env_missing": True,
        "audit_trace": {"confidence": {"no_bet_reasons": ["placeholder_data"]}},
    }
    good_payload = {
        "status": "ok",
        "fixture_id": 1,
        "confidence": 48.0,
        "is_placeholder": False,
        "provider_readiness": {"api_football_configured": True},
    }
    allow_bad, reason_bad = evaluate_prediction_storage(bad_payload, settings=settings, existing_payload=good_payload)
    record("no_key_placeholder_blocked", not allow_bad, reason_bad)
    record("no_overwrite_non_placeholder", reason_bad in ("provider_env_missing_would_downgrade", "provider_env_missing_placeholder", "would_downgrade_existing_non_placeholder", "provider_env_missing"))

    from worldcup_predictor.automation.worldcup_background.stale_prediction_policy import is_stored_prediction_quality_valid

    stale_34b = {
        "status": "ok",
        "prediction_engine_version": "34b-v1",
        "adaptive_confidence_version": "1-v1",
        "national_team_intelligence": {"version": "32e"},
        "confidence": 3.0,
        "is_placeholder": True,
        "provider_env_missing": True,
        "probabilities": {"home_win": 51.7, "draw": 23.6, "away_win": 24.7},
        "adaptive_confidence_trace": {"confidence_before_adaptive": 11.5, "confidence_after_adaptive": 13.0},
        "audit_trace": {"confidence": {"no_bet_reasons": ["placeholder_data"], "final": 11.5}},
    }
    ok, reason = is_stored_prediction_quality_valid(stale_34b)
    record("34b_placeholder_payload_invalid", not ok, reason)

    _report(checks)
    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
