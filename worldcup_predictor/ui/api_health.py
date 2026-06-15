"""API connectivity checks for the GUI — never exposes secret keys."""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.clients.openai_client import OpenAIClient
from worldcup_predictor.config.settings import Settings


@dataclass(frozen=True)
class ApiServiceStatus:
    service: str
    env_var: str
    configured: bool
    connected: bool | None
    message: str
    latency_ms: float | None = None


def test_api_football(settings: Settings) -> ApiServiceStatus:
    if not settings.api_football_configured:
        return ApiServiceStatus(
            service="API-Football",
            env_var="API_FOOTBALL_KEY",
            configured=False,
            connected=None,
            message="Key not configured — placeholder schedule/fixtures will be used.",
        )

    client = ApiFootballClient(settings)
    start = time.perf_counter()
    try:
        result = client._safe_get(  # noqa: SLF001
            "timezone",
            {},
            placeholder_factory=lambda: [],
        )
        latency = (time.perf_counter() - start) * 1000
        if result.source in ("live", "cache") and result.data is not None:
            return ApiServiceStatus(
                service="API-Football",
                env_var="API_FOOTBALL_KEY",
                configured=True,
                connected=True,
                message=f"Connected ({result.source})",
                latency_ms=round(latency, 1),
            )
        return ApiServiceStatus(
            service="API-Football",
            env_var="API_FOOTBALL_KEY",
            configured=True,
            connected=False,
            message=result.error or "Request failed — check key or quota.",
            latency_ms=round(latency, 1),
        )
    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        return ApiServiceStatus(
            service="API-Football",
            env_var="API_FOOTBALL_KEY",
            configured=True,
            connected=False,
            message=str(exc),
            latency_ms=round(latency, 1),
        )


def test_openai(settings: Settings) -> ApiServiceStatus:
    if not settings.openai_configured:
        return ApiServiceStatus(
            service="OpenAI",
            env_var="OPENAI_API_KEY",
            configured=False,
            connected=None,
            message="Key not configured — local rule-based reports will be used.",
        )

    start = time.perf_counter()
    try:
        client = OpenAIClient(settings)
        client.ping_connection()
        latency = (time.perf_counter() - start) * 1000
        return ApiServiceStatus(
            service="OpenAI",
            env_var="OPENAI_API_KEY",
            configured=True,
            connected=True,
            message=f"Connected (model: {settings.openai_model})",
            latency_ms=round(latency, 1),
        )
    except ImportError:
        return ApiServiceStatus(
            service="OpenAI",
            env_var="OPENAI_API_KEY",
            configured=True,
            connected=False,
            message="openai package not installed.",
        )
    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        return ApiServiceStatus(
            service="OpenAI",
            env_var="OPENAI_API_KEY",
            configured=True,
            connected=False,
            message=str(exc),
            latency_ms=round(latency, 1),
        )


def test_weather(settings: Settings) -> ApiServiceStatus:
    from worldcup_predictor.providers.weather_provider import WeatherProvider

    provider = WeatherProvider(settings)
    if not provider.is_configured:
        return ApiServiceStatus(
            service=f"Weather ({provider.active_provider_name})",
            env_var=provider.active_env_var,
            configured=False,
            connected=None,
            message=f"Optional — set WEATHER_PROVIDER={provider.active_provider_name} and key.",
        )
    return ApiServiceStatus(
        service=f"Weather ({provider.active_provider_name})",
        env_var=provider.active_env_var,
        configured=True,
        connected=None,
        message="Optional enrichment — used when API-Sports fixture weather is missing.",
    )


def test_optional_providers(settings: Settings) -> list[ApiServiceStatus]:
    from worldcup_predictor.providers.registry import ProviderRegistry

    rows: list[ApiServiceStatus] = []
    for item in ProviderRegistry(settings).status_report():
        if item.tier.name != "ENRICHMENT":
            continue
        if item.provider in ("rapid_football_stats", "rapid_xg_statistics", "rapid_open_weather"):
            continue  # dedicated ping tests
        rows.append(
            ApiServiceStatus(
                service=item.label,
                env_var=item.env_var,
                configured=item.configured,
                connected=None,
                message=item.note + (" — configured." if item.configured else " — optional, not set."),
            )
        )
    return rows


def test_rapid_football_stats(settings: Settings) -> ApiServiceStatus:
    from worldcup_predictor.clients.rapid_football_stats import RapidFootballStatsClient

    if not settings.rapid_football_stats_enabled:
        return ApiServiceStatus(
            service="RapidAPI Football Stats",
            env_var="RAPID_FOOTBALL_STATS_ENABLED",
            configured=False,
            connected=None,
            message="Optional — set RAPID_FOOTBALL_STATS_ENABLED=true and key to enable.",
        )
    if not settings.rapid_football_stats_key.strip():
        return ApiServiceStatus(
            service="RapidAPI Football Stats",
            env_var="RAPID_FOOTBALL_STATS_KEY",
            configured=False,
            connected=None,
            message="Enabled but key missing — supplemental enrichment skipped.",
        )

    client = RapidFootballStatsClient(settings)
    start = time.perf_counter()
    result = client.ping()
    latency = (time.perf_counter() - start) * 1000
    if result.loaded:
        return ApiServiceStatus(
            service="RapidAPI Football Stats",
            env_var="RAPID_FOOTBALL_STATS_KEY",
            configured=True,
            connected=True,
            message="Supplemental enrichment available (xG, odds, player stats).",
            latency_ms=round(latency, 1),
        )
    return ApiServiceStatus(
        service="RapidAPI Football Stats",
        env_var="RAPID_FOOTBALL_STATS_KEY",
        configured=True,
        connected=False,
        message=result.error or "Ping failed — API-Sports remains primary.",
        latency_ms=round(latency, 1),
    )


def test_rapid_xg_statistics(settings: Settings) -> ApiServiceStatus:
    from worldcup_predictor.clients.rapid_xg_statistics import RapidXgStatisticsClient

    if not settings.rapid_xg_enabled:
        return ApiServiceStatus(
            service="Rapid Football XG Statistics",
            env_var="RAPID_XG_ENABLED",
            configured=False,
            connected=None,
            message="Optional — set RAPID_XG_ENABLED=true and key to enable.",
        )
    if not settings.rapid_xg_key.strip():
        return ApiServiceStatus(
            service="Rapid Football XG Statistics",
            env_var="RAPID_XG_KEY",
            configured=False,
            connected=None,
            message="Enabled but key missing — supplemental enrichment skipped.",
        )

    client = RapidXgStatisticsClient(settings)
    start = time.perf_counter()
    result = client.ping()
    latency = (time.perf_counter() - start) * 1000
    if result.loaded:
        return ApiServiceStatus(
            service="Rapid Football XG Statistics",
            env_var="RAPID_XG_KEY",
            configured=True,
            connected=True,
            message="Supplemental xG/odds enrichment available.",
            latency_ms=round(latency, 1),
        )
    return ApiServiceStatus(
        service="Rapid Football XG Statistics",
        env_var="RAPID_XG_KEY",
        configured=True,
        connected=False,
        message=result.error or "Ping failed — API-Sports remains primary.",
        latency_ms=round(latency, 1),
    )


def test_rapid_open_weather(settings: Settings) -> ApiServiceStatus:
    from worldcup_predictor.clients.rapid_open_weather import RapidOpenWeatherClient

    if not settings.rapid_open_weather_enabled:
        return ApiServiceStatus(
            service="Rapid Open Weather",
            env_var="RAPID_OPEN_WEATHER_ENABLED",
            configured=False,
            connected=None,
            message="Optional — set RAPID_OPEN_WEATHER_ENABLED=true and key to enable.",
        )
    if not settings.rapid_open_weather_key.strip():
        return ApiServiceStatus(
            service="Rapid Open Weather",
            env_var="RAPID_OPEN_WEATHER_KEY",
            configured=False,
            connected=None,
            message="Enabled but key missing — weather backup skipped.",
        )

    client = RapidOpenWeatherClient(settings)
    start = time.perf_counter()
    result = client.ping()
    latency = (time.perf_counter() - start) * 1000
    if result.loaded:
        return ApiServiceStatus(
            service="Rapid Open Weather",
            env_var="RAPID_OPEN_WEATHER_KEY",
            configured=True,
            connected=True,
            message="Weather backup available (city + 5-day forecast).",
            latency_ms=round(latency, 1),
        )
    return ApiServiceStatus(
        service="Rapid Open Weather",
        env_var="RAPID_OPEN_WEATHER_KEY",
        configured=True,
        connected=False,
        message=result.error or "Ping failed — primary weather provider remains preferred.",
        latency_ms=round(latency, 1),
    )


def test_all_apis(settings: Settings) -> list[ApiServiceStatus]:
    return [
        test_api_football(settings),
        test_openai(settings),
        test_weather(settings),
        test_rapid_football_stats(settings),
        test_rapid_xg_statistics(settings),
        test_rapid_open_weather(settings),
        *test_optional_providers(settings),
    ]


def overall_api_readiness(statuses: list[ApiServiceStatus]) -> tuple[str, float]:
    """Return readiness label and 0–1 progress for API layer."""
    by_name = {s.service: s for s in statuses}
    api_football = by_name.get("API-Football")
    openai = by_name.get("OpenAI")

    if api_football is None or openai is None:
        return "Not Ready", 0.15

    if not api_football.configured and not openai.configured:
        return "Not Ready", 0.15

    both_ready = (
        api_football.configured
        and api_football.connected is True
        and openai.configured
        and openai.connected is True
    )
    if both_ready:
        return "Ready", 1.0

    any_connected = any(
        s.configured and s.connected is True for s in (api_football, openai)
    )
    if any_connected:
        return "Partial", 0.55

    if api_football.configured or openai.configured:
        return "Partial", 0.35

    return "Not Ready", 0.3
