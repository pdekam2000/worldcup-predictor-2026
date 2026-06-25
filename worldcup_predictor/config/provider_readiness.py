"""Phase 36C — provider key presence checks (never expose secret values)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.config.env_loading import is_production_runtime, loaded_env_file_display
from worldcup_predictor.config.settings import Settings, get_settings


class ProductionProviderEnvError(RuntimeError):
    """Raised when production prediction/validation runs without required API keys."""

    code = "production_provider_env_missing"

    def __init__(self, message: str = "production_provider_env_missing") -> None:
        super().__init__(message)


def provider_key_presence(settings: Settings | None = None) -> dict[str, bool]:
    settings = settings or get_settings()
    return {
        "API_FOOTBALL_KEY": settings.api_football_configured,
        "SPORTMONKS_API_KEY": settings.sportmonks_configured,
        "THE_ODDS_API_KEY": settings.the_odds_api_configured,
        "WEATHER_API_KEY": settings.weather_provider_configured,
        "DATABASE_URL": settings.postgres_configured,
        "STRIPE_SECRET_KEY": settings.stripe_secret_key_configured,
        "STRIPE_WEBHOOK_SECRET": settings.stripe_webhook_secret_configured,
        "STRIPE_STARTER_PRICE_ID": settings.stripe_starter_price_configured,
        "STRIPE_PRO_PRICE_ID": settings.stripe_pro_price_configured,
    }


def stripe_env_diagnostic(settings: Settings | None = None) -> dict[str, str | bool]:
    """Yes/no Stripe env diagnostic — never exposes secret values."""
    settings = settings or get_settings()
    keys = provider_key_presence(settings)
    return {
        "STRIPE_SECRET_KEY_present": keys["STRIPE_SECRET_KEY"],
        "STRIPE_WEBHOOK_SECRET_present": keys["STRIPE_WEBHOOK_SECRET"],
        "STRIPE_STARTER_PRICE_ID_present": keys["STRIPE_STARTER_PRICE_ID"],
        "STRIPE_PRO_PRICE_ID_present": keys["STRIPE_PRO_PRICE_ID"],
        "STRIPE_MODE": settings.stripe_mode_normalized,
    }


def provider_diagnostic(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    keys = provider_key_presence(settings)
    required_ok = keys["API_FOOTBALL_KEY"]
    return {
        "APP_ENV": settings.app_env,
        "ENVIRONMENT": __import__("os").environ.get("ENVIRONMENT", ""),
        "ENV_FILE": __import__("os").environ.get("ENV_FILE", ""),
        "loaded_env_file": loaded_env_file_display(),
        "is_production_runtime": is_production_runtime(),
        "API_FOOTBALL_KEY_present": keys["API_FOOTBALL_KEY"],
        "SPORTMONKS_API_KEY_present": keys["SPORTMONKS_API_KEY"],
        "THE_ODDS_API_KEY_present": keys["THE_ODDS_API_KEY"],
        "WEATHER_API_KEY_present": keys["WEATHER_API_KEY"],
        "DATABASE_URL_present": keys["DATABASE_URL"],
        "STRIPE_SECRET_KEY_present": keys["STRIPE_SECRET_KEY"],
        "STRIPE_WEBHOOK_SECRET_present": keys["STRIPE_WEBHOOK_SECRET"],
        "STRIPE_STARTER_PRICE_ID_present": keys["STRIPE_STARTER_PRICE_ID"],
        "STRIPE_PRO_PRICE_ID_present": keys["STRIPE_PRO_PRICE_ID"],
        "STRIPE_MODE": settings.stripe_mode_normalized,
        "provider_readiness_summary": "ready" if required_ok else "missing_required_api_football",
        "production_prediction_allowed": required_ok,
    }


def assert_production_api_football(settings: Settings | None = None) -> None:
    """Fail hard before production prediction validation or storage when key missing."""
    settings = settings or get_settings()
    if not settings.api_football_configured:
        raise ProductionProviderEnvError(
            "production_provider_env_missing: API_FOOTBALL_KEY is required before running predictions"
        )
    if is_production_runtime() and settings.app_env != "production":
        # Keys present but APP_ENV not set — allow if keys exist
        pass


def weather_provider_status(settings: Settings | None = None) -> dict[str, Any]:
    """Safe weather provider diagnostic — no secrets."""
    settings = settings or get_settings()
    return {
        "weather_configured": settings.weather_provider_configured,
        "weather_provider": settings.weather_provider,
        "weather_provider_ready": settings.weather_provider_configured,
        "weather_cache_ttl_seconds": int(settings.weather_cache_ttl_seconds),
        "loaded_env_file": loaded_env_file_display(),
        "app_env": settings.app_env,
    }


def stamp_provider_readiness(payload: dict[str, Any], settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    out = dict(payload)
    weather = weather_provider_status(settings)
    out["provider_readiness"] = {
        "api_football_configured": settings.api_football_configured,
        "sportmonks_configured": settings.sportmonks_configured,
        "the_odds_api_configured": settings.the_odds_api_configured,
        "weather_configured": weather["weather_configured"],
        "weather_provider": weather["weather_provider"],
        "weather_cache_ttl_seconds": weather["weather_cache_ttl_seconds"],
        "loaded_env_file": weather["loaded_env_file"],
        "app_env": weather["app_env"],
    }
    if settings.api_football_configured:
        out.pop("provider_env_missing", None)
    else:
        out["provider_env_missing"] = True
    return out
