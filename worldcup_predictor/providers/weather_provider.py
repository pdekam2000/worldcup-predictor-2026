"""Weather provider — WeatherAPI or OpenWeather (optional enrichment)."""

from __future__ import annotations

import logging
from typing import Any, Literal

import httpx

from worldcup_predictor.config.settings import Settings, WeatherProviderKind
from worldcup_predictor.providers.base import ProviderCallResult, ProviderTier
from worldcup_predictor.weather_impact import compute_weather_impact, rain_probability_from_condition

logger = logging.getLogger(__name__)


class WeatherProvider:
    """Optional venue weather — never replaces API-Sports fixture payload when present."""

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

        query = f"{city},{country}" if country and country != "TBD" else city
        if self._settings.weather_provider == "openweather":
            return self._fetch_openweather(query)
        return self._fetch_weatherapi(query)

    def _fetch_weatherapi(self, query: str) -> ProviderCallResult:
        endpoint = "forecast.json"
        params = {
            "key": self._settings.weather_api_key,
            "q": query,
            "days": 1,
            "aqi": "no",
            "alerts": "no",
        }
        try:
            url = "https://api.weatherapi.com/v1/forecast.json"
            with httpx.Client(timeout=20.0) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
            normalized = self._normalize_weatherapi(payload)
            normalized["weather_impact_score"] = compute_weather_impact(
                normalized.get("temperature_c"),
                normalized.get("rain_probability"),
                normalized.get("wind_speed_kmh"),
            )
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

    def _fetch_openweather(self, query: str) -> ProviderCallResult:
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
            normalized = self._normalize_openweather(payload)
            normalized["weather_impact_score"] = compute_weather_impact(
                normalized.get("temperature_c"),
                normalized.get("rain_probability"),
                normalized.get("wind_speed_kmh"),
            )
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

    @staticmethod
    def _normalize_weatherapi(payload: dict[str, Any]) -> dict[str, Any]:
        current = payload.get("current") or {}
        condition = (current.get("condition") or {}).get("text", "")
        return {
            "available": True,
            "provider": "weatherapi",
            "source": "weatherapi",
            "temperature_c": current.get("temp_c"),
            "condition": condition,
            "rain_probability": rain_probability_from_condition(condition),
            "wind_speed_kmh": (current.get("wind_kph") or 0),
            "humidity_pct": current.get("humidity"),
            "raw": payload,
        }

    @staticmethod
    def _normalize_openweather(payload: dict[str, Any]) -> dict[str, Any]:
        items = payload.get("list") or []
        first = items[0] if items else {}
        weather = (first.get("weather") or [{}])[0]
        condition = weather.get("main", "")
        return {
            "available": True,
            "provider": "openweather",
            "source": "openweather",
            "temperature_c": (first.get("main") or {}).get("temp"),
            "condition": condition,
            "rain_probability": rain_probability_from_condition(condition),
            "wind_speed_kmh": _wind_to_kmh((first.get("wind") or {}).get("speed")),
            "humidity_pct": (first.get("main") or {}).get("humidity"),
            "raw": payload,
        }


def _wind_to_kmh(speed: Any) -> float | None:
    try:
        if speed is None:
            return None
        return round(float(speed) * 3.6, 1)
    except (TypeError, ValueError):
        return None
