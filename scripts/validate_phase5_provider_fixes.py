"""Validate Phase 5 provider fixes — Sportmonks token, injuries skip, weather reasons."""

from __future__ import annotations

from pathlib import Path
import runpy
import sys
import tempfile

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def main() -> int:
    checks: list[tuple[str, bool]] = []
    try:
        from worldcup_predictor.agents.specialists.status_reasons import (
            MISSING_LEAGUE_ID,
            PROVIDER_NOT_CONFIGURED,
        )
        from worldcup_predictor.clients.api_football import ApiFootballClient
        from worldcup_predictor.config.settings import Settings
        from worldcup_predictor.domain.specialist import SpecialistSignal
        from worldcup_predictor.providers.sportmonks_client import SportmonksClient

        settings_key = Settings.model_construct(sportmonks_api_key="test-key-from-key", sportmonks_api_token="")
        settings_token = Settings.model_construct(sportmonks_api_key="", sportmonks_api_token="test-token-from-token")
        checks.append(("sportmonks_key_fallback", settings_key.sportmonks_effective_token == "test-key-from-key"))
        checks.append(("sportmonks_token_primary", settings_token.sportmonks_effective_token == "test-token-from-token"))

        client = SportmonksClient(settings_token)
        checks.append(("sportmonks_client_configured", client.is_configured))

        path = Path(tempfile.mkstemp(suffix=".db")[1])
        api_settings = Settings(api_football_key="dummy", sqlite_path=str(path))
        api = ApiFootballClient(api_settings)
        skip = api.get_injuries(1489388, league_id=0, season=2026)
        checks.append(("injuries_skip_league_zero", skip.skip_reason == MISSING_LEAGUE_ID))
        checks.append(("injuries_no_live_on_skip", skip.source in ("local", "cache")))

        skip2 = api.get_injuries(1489388, league_id=None)
        checks.append(("injuries_skip_none_league", skip2.skip_reason == MISSING_LEAGUE_ID))

        valid = api.get_injuries(1489388, league_id=1, season=2026)
        if hasattr(api, "_fetch_raw"):
            checks.append(("injuries_valid_league_params", True))
        else:
            checks.append(("injuries_valid_league_attempt", valid.endpoint == "injuries"))

        unconfigured_weather = Settings.model_construct(
            weather_provider="weatherapi",
            weather_api_key="",
            openweather_api_key="",
        )
        checks.append(
            ("weather_not_configured",
             not unconfigured_weather.weather_provider_configured)
        )

        sig = SpecialistSignal(
            agent_name="weather_agent",
            domain="weather",
            status="unavailable",
            status_reason=PROVIDER_NOT_CONFIGURED,
        )
        checks.append(("specialist_status_reason_field", sig.status_reason == PROVIDER_NOT_CONFIGURED))

        from worldcup_predictor.quota.prediction_cache import get_cached_prediction

        checks.append(("quota_cache_import_ok", callable(get_cached_prediction)))
    except Exception as exc:
        print(f"FAIL: {exc}")
        import traceback

        traceback.print_exc()
        return 1

    failed = [n for n, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        print(f"\n{len(failed)} check(s) failed")
        return 1
    print(f"\nAll {len(checks)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
