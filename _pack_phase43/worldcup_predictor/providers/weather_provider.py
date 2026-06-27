"""Weather provider — WeatherAPI or OpenWeather (optional enrichment) — Phase 43."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from worldcup_predictor.config.settings import Settings, WeatherProviderKind
from worldcup_predictor.intelligence.weather_intelligence_engine import (
    enrich_normalized_weather,
    extract_severe_alerts_weatherapi,
    kickoff_snapshot_from_hour,
    merge_kickoff_weather_fields,
    pick_openweather_kickoff_hour,
    pick_weatherapi_kickoff_hour,
)
from worldcup_predictor.providers.base import ProviderCallResult, ProviderTier
from worldcup_predictor.providers.weather_cache import weather_cache_get, weather_cache_set
from worldcup_predictor.weather_impact import rain_probability_from_condition

logger = logging.getLogger(__name__)


class WeatherProvider:
    """Optional venue weather — cache-first; never replaces API-Sports fixture payload."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def active_provider_name(self) -> WeatherProviderKind:
        return self._settings.weather_provider

    @property
    def active_env_var(self) -> str:
        if self._settings.weather_provider == "openweather":
            return "OPENWEATHER_API_KEY" if self._settings.openweather_configured else "WEATHER_API_KEY"
        return "WEATHER_API_KEY"

    @property
    def is_configured(self) -> bool:
        return self._settings.weather_provider_configured

    def get_venue_forecast(
        self,
        *,
        city: str,
        country: str | None = None,
        kickoff_utc: datetime | None = None,
    ) -> ProviderCallResult:
        if not self.is_configured:
            return ProviderCallResult(
                data=None,
                provider=self.active_provider_name,
                tier=ProviderTier.ENRICHMENT,
                endpoint="forecast",
                configured=False,
                error=f"{self.active_env_var} not configured for {self.active_provider_name}",
            )

        query = f"{city},{country}" if country and country not in {"", "TBD"} else city
        kickoff_iso = kickoff_utc.isoformat() if kickoff_utc else None
        provider = self._settings.weather_provider

        cached = weather_cache_get(provider, query, kickoff_iso=kickoff_iso, settings=self._settings)
        if cached and cached.get("available"):
            cached = dict(cached)
            cached["cached"] = True
            cached["cache_source"] = "weather_cache"
            return ProviderCallResult(
                data=cached,
                provider=provider,
                tier=ProviderTier.ENRICHMENT,
                endpoint="forecast",
                trace={"cache_hit": True},
            )

        if provider == "openweather":
            result = self._fetch_openweather(query, kickoff_utc=kickoff_utc)
        else:
            result = self._fetch_weatherapi(query, kickoff_utc=kickoff_utc)

        if result.available and isinstance(result.data, dict):
            weather_cache_set(
                provider,
                query,
                result.data,
                kickoff_iso=kickoff_iso,
                settings=self._settings,
            )
        return result

    def _fetch_weatherapi(self, query: str, *, kickoff_utc: datetime | None) -> ProviderCallResult:
        endpoint = "forecast.json"
        params = {
            "key": self._settings.weather_api_key,
            "q": query,
            "days": 3,
            "aqi": "no",
            "alerts": "yes",
        }
        try:
            url = "https://api.weatherapi.com/v1/forecast.json"
            with httpx.Client(timeout=20.0) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
            normalized = self._normalize_weatherapi(payload, kickoff_utc=kickoff_utc)
            return ProviderCallResult(
                data=normalized,
                provider="weatherapi",
                tier=ProviderTier.ENRICHMENT,
                endpoint=endpoint,
            )
        except Exception as exc:
            logger.exception("WeatherAPI request failed")
            return ProviderCallResult(
                data=None,
                provider="weatherapi",
                tier=ProviderTier.ENRICHMENT,
                endpoint=endpoint,
                error=str(exc),
            )

    def _fetch_openweather(self, query: str, *, kickoff_utc: datetime | None) -> ProviderCallResult:
        endpoint = "forecast"
        params = {
            "appid": self._settings.effective_openweather_key,
            "q": query,
            "units": "metric",
        }
        try:
            url = "https://api.openweathermap.org/data/2.5/forecast"
            with httpx.Client(timeout=20.0) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
            normalized = self._normalize_openweather(payload, kickoff_utc=kickoff_utc)
            return ProviderCallResult(
                data=normalized,
                provider="openweather",
                tier=ProviderTier.ENRICHMENT,
                endpoint=endpoint,
            )
        except Exception as exc:
            logger.exception("OpenWeather request failed")
            return ProviderCallResult(
                data=None,
                provider="openweather",
                tier=ProviderTier.ENRICHMENT,
                endpoint=endpoint,
                error=str(exc),
            )

    def _normalize_weatherapi(
        self,
        payload: dict[str, Any],
        *,
        kickoff_utc: datetime | None,
    ) -> dict[str, Any]:
        current = payload.get("current") or {}
        condition = (current.get("condition") or {}).get("text", "")
        rain_mm = _float(current.get("precip_mm"))
        base = {
            "available": True,
            "provider": "weatherapi",
            "source": "weatherapi",
            "temperature_c": current.get("temp_c"),
            "feels_like_c": current.get("feelslike_c"),
            "condition": condition,
            "rain_probability": rain_probability_from_condition(condition, rain_mm=rain_mm),
            "rain_mm": rain_mm,
            "wind_speed_kmh": current.get("wind_kph"),
            "wind_gust_kmh": current.get("gust_kph"),
            "humidity_pct": current.get("humidity"),
            "visibility_km": current.get("vis_km"),
            "cloud_cover_pct": current.get("cloud"),
            "severe_weather_alerts": extract_severe_alerts_weatherapi(payload),
            "cached": False,
        }
        if kickoff_utc is not None:
            base["kickoff_utc"] = kickoff_utc.isoformat()
        hour = pick_weatherapi_kickoff_hour(payload, kickoff_utc)
        kickoff_snap = kickoff_snapshot_from_hour(hour, provider="weatherapi")
        merged = merge_kickoff_weather_fields(base, kickoff_snap)
        return enrich_normalized_weather(merged)

    def _normalize_openweather(
        self,
        payload: dict[str, Any],
        *,
        kickoff_utc: datetime | None,
    ) -> dict[str, Any]:
        items = payload.get("list") or []
        first = items[0] if items else {}
        weather = (first.get("weather") or [{}])[0]
        condition = weather.get("main", "")
        rain_mm = _float((first.get("rain") or {}).get("3h"))
        wind = first.get("wind") or {}
        base = {
            "available": True,
            "provider": "openweather",
            "source": "openweather",
            "temperature_c": (first.get("main") or {}).get("temp"),
            "feels_like_c": (first.get("main") or {}).get("feels_like"),
            "condition": condition,
            "rain_probability": rain_probability_from_condition(condition, rain_mm=rain_mm),
            "rain_mm": rain_mm,
            "wind_speed_kmh": _wind_to_kmh(_float(wind.get("speed"))),
            "wind_gust_kmh": _wind_to_kmh(_float(wind.get("gust"))),
            "humidity_pct": (first.get("main") or {}).get("humidity"),
            "visibility_km": _visibility_km(first.get("visibility")),
            "cloud_cover_pct": (first.get("clouds") or {}).get("all"),
            "severe_weather_alerts": [],
            "cached": False,
        }
        if kickoff_utc is not None:
            base["kickoff_utc"] = kickoff_utc.isoformat()
        hour = pick_openweather_kickoff_hour(payload, kickoff_utc)
        kickoff_snap = kickoff_snapshot_from_hour(hour, provider="openweather")
        merged = merge_kickoff_weather_fields(base, kickoff_snap)
        return enrich_normalized_weather(merged)


def _float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _wind_to_kmh(speed: float | None) -> float | None:
    if speed is None:
        return None
    return round(speed * 3.6, 1)


def _visibility_km(value: Any) -> float | None:
    try:
        if value is None:
            return None
        num = float(value)
        return round(num / 1000.0, 1) if num > 100 else round(num, 1)
    except (TypeError, ValueError):
        return None
