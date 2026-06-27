"""
RapidAPI Open Weather — optional backup weather enrichment only.

Provider: open-weather13.p.rapidapi.com
Never replaces primary WeatherAPI/OpenWeather. No mock data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from worldcup_predictor.config.settings import Settings
from worldcup_predictor.weather_impact import compute_weather_impact, rain_probability_from_condition

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RapidWeatherCallResult:
    endpoint: str
    loaded: bool
    response_count: int = 0
    error: str | None = None
    data: dict[str, Any] | None = None


class RapidOpenWeatherClient:
    """RapidAPI Open Weather backup client."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.rapid_open_weather_base_url.rstrip("/")

    @property
    def is_configured(self) -> bool:
        return self._settings.rapid_open_weather_configured

    def _headers(self) -> dict[str, str]:
        return {
            "x-rapidapi-key": self._settings.rapid_open_weather_key,
            "x-rapidapi-host": self._settings.rapid_open_weather_host,
            "Content-Type": "application/json",
        }

    def ping(self) -> RapidWeatherCallResult:
        if not self.is_configured:
            return RapidWeatherCallResult(
                endpoint="rapid_weather/ping",
                loaded=False,
                error="not_configured",
            )
        return self._get("ping", "/city", {"city": "London"})

    def get_current_by_city(self, city: str) -> RapidWeatherCallResult:
        return self._get("current_city", "/city", {"city": city})

    def get_forecast_by_coords(
        self,
        latitude: float,
        longitude: float,
    ) -> RapidWeatherCallResult:
        return self._get(
            "forecast_coords",
            "/fivedaysforcast",
            {"latitude": str(latitude), "longitude": str(longitude)},
        )

    def get_venue_weather(
        self,
        *,
        city: str,
        latitude: float | None = None,
        longitude: float | None = None,
        kickoff_utc: datetime | None = None,
    ) -> RapidWeatherCallResult:
        """Resolve venue weather: city current + optional 5-day/3-hour forecast."""
        if not self.is_configured:
            return RapidWeatherCallResult(
                endpoint="rapid_weather/venue",
                loaded=False,
                error="not_configured",
            )

        current: dict[str, Any] | None = None
        forecast_items: list[dict[str, Any]] = []
        lat = latitude
        lon = longitude

        if city and city != "TBD":
            current_result = self.get_current_by_city(city)
            if current_result.loaded and isinstance(current_result.data, dict):
                current = current_result.data
                coord = current.get("coord") or {}
                lat = lat or _float(coord.get("lat"))
                lon = lon or _float(coord.get("lon"))

        if lat is not None and lon is not None:
            forecast_result = self.get_forecast_by_coords(lat, lon)
            if forecast_result.loaded and isinstance(forecast_result.data, dict):
                forecast_items = forecast_result.data.get("list") or []
                if not current and forecast_items:
                    current = _forecast_item_to_current(forecast_items[0], forecast_result.data)

        if not current:
            return RapidWeatherCallResult(
                endpoint="rapid_weather/venue",
                loaded=False,
                error="weather_not_found",
            )

        normalized = self._normalize_payload(
            current=current,
            forecast_items=forecast_items,
            kickoff_utc=kickoff_utc,
            city=city,
        )
        return RapidWeatherCallResult(
            endpoint="rapid_weather/venue",
            loaded=True,
            response_count=1 + len(forecast_items),
            data=normalized,
        )

    def _normalize_payload(
        self,
        *,
        current: dict[str, Any],
        forecast_items: list[dict[str, Any]],
        kickoff_utc: datetime | None,
        city: str,
    ) -> dict[str, Any]:
        main = current.get("main") or {}
        weather = (current.get("weather") or [{}])[0]
        wind = current.get("wind") or {}
        condition = weather.get("description") or weather.get("main") or ""
        temp_c = _to_celsius(_float(main.get("temp")))
        humidity = _float(main.get("humidity"))
        wind_kmh = _wind_to_kmh(_float(wind.get("speed")))
        rain_mm = _float((current.get("rain") or {}).get("1h"))
        rain_prob = rain_probability_from_condition(condition, rain_mm=rain_mm)

        kickoff_forecast = _pick_kickoff_forecast(forecast_items, kickoff_utc)
        if kickoff_forecast:
            k_main = kickoff_forecast.get("main") or {}
            k_weather = (kickoff_forecast.get("weather") or [{}])[0]
            k_condition = k_weather.get("description") or k_weather.get("main") or condition
            k_temp = _to_celsius(_float(k_main.get("temp"))) or temp_c
            k_wind = _wind_to_kmh(_float((kickoff_forecast.get("wind") or {}).get("speed"))) or wind_kmh
            k_rain = rain_probability_from_condition(
                k_condition,
                rain_mm=_float((kickoff_forecast.get("rain") or {}).get("3h")),
            )
            if k_temp is not None:
                temp_c = k_temp
            if k_wind is not None:
                wind_kmh = k_wind
            rain_prob = max(rain_prob, k_rain)

        impact = compute_weather_impact(temp_c, rain_prob, wind_kmh)
        from worldcup_predictor.intelligence.weather_intelligence_engine import enrich_normalized_weather

        base = {
            "available": True,
            "provider": "rapid_open_weather",
            "source": "rapid_open_weather",
            "city": city,
            "temperature_c": temp_c,
            "feels_like_c": _to_celsius(_float(main.get("feels_like"))),
            "condition": condition,
            "rain_probability": rain_prob,
            "rain_mm": rain_mm,
            "wind_speed_kmh": wind_kmh,
            "wind_gust_kmh": _wind_to_kmh(_float(wind.get("gust"))),
            "humidity_pct": humidity,
            "visibility_km": _visibility_km(current.get("visibility")),
            "cloud_cover_pct": (current.get("clouds") or {}).get("all"),
            "kickoff_forecast": kickoff_forecast,
            "forecast_periods": len(forecast_items),
            "severe_weather_alerts": [],
            "cached": False,
        }
        if kickoff_utc is not None:
            base["kickoff_utc"] = kickoff_utc.isoformat()
        if kickoff_forecast:
            from worldcup_predictor.intelligence.weather_intelligence_engine import (
                kickoff_snapshot_from_hour,
                merge_kickoff_weather_fields,
            )

            snap = kickoff_snapshot_from_hour(kickoff_forecast, provider="openweather")
            base = merge_kickoff_weather_fields(base, snap)
        return enrich_normalized_weather(base)

    def _get(self, logical: str, path: str, params: dict[str, Any]) -> RapidWeatherCallResult:
        url = f"{self._base_url}/{path.lstrip('/')}"
        try:
            with httpx.Client(timeout=20.0, follow_redirects=True) as client:
                response = client.get(url, headers=self._headers(), params=params)
                if response.status_code >= 400:
                    return RapidWeatherCallResult(
                        endpoint=f"rapid_weather/{logical}",
                        loaded=False,
                        error=f"http_{response.status_code}",
                    )
                payload = response.json()
            if isinstance(payload, dict) and str(payload.get("cod")) not in ("200", "200.0"):
                if payload.get("message"):
                    return RapidWeatherCallResult(
                        endpoint=f"rapid_weather/{logical}",
                        loaded=False,
                        error=str(payload.get("message")),
                    )
            if logical == "forecast_coords" and isinstance(payload, dict):
                items = payload.get("list") or []
                loaded = len(items) > 0
                return RapidWeatherCallResult(
                    endpoint=f"rapid_weather/{logical}",
                    loaded=loaded,
                    response_count=len(items),
                    data=payload,
                )
            if isinstance(payload, dict) and payload.get("main"):
                return RapidWeatherCallResult(
                    endpoint=f"rapid_weather/{logical}",
                    loaded=True,
                    response_count=1,
                    data=payload,
                )
            return RapidWeatherCallResult(
                endpoint=f"rapid_weather/{logical}",
                loaded=False,
                error="empty_response",
            )
        except Exception as exc:
            logger.debug("Rapid Open Weather %s failed: %s", logical, exc)
            return RapidWeatherCallResult(
                endpoint=f"rapid_weather/{logical}",
                loaded=False,
                error=str(exc),
            )


def _float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_celsius(temp: float | None) -> float | None:
    if temp is None:
        return None
    if temp > 55:
        return round((temp - 32) * 5 / 9, 1)
    return round(temp, 1)


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


def _forecast_item_to_current(item: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "main": item.get("main") or {},
        "weather": item.get("weather") or [],
        "wind": item.get("wind") or {},
        "rain": item.get("rain") or {},
        "coord": (payload.get("city") or {}).get("coord") if isinstance(payload.get("city"), dict) else {},
    }


def _pick_kickoff_forecast(
    items: list[dict[str, Any]],
    kickoff_utc: datetime | None,
) -> dict[str, Any] | None:
    if not items or kickoff_utc is None:
        return None
    target_ts = kickoff_utc.timestamp()
    best: dict[str, Any] | None = None
    best_delta = float("inf")
    for item in items:
        dt = item.get("dt")
        if dt is None:
            continue
        try:
            delta = abs(float(dt) - target_ts)
        except (TypeError, ValueError):
            continue
        if delta < best_delta:
            best_delta = delta
            best = item
    return best
