"""Shared weather impact scoring — moderate influence, no mock data."""

from __future__ import annotations


def rain_probability_from_condition(condition: str, *, rain_mm: float | None = None) -> float:
    text = (condition or "").lower()
    if rain_mm is not None and rain_mm > 0:
        return min(0.55 + rain_mm * 0.15, 0.9)
    if any(word in text for word in ("rain", "drizzle", "storm", "thunder")):
        return 0.65
    if "cloud" in text or "overcast" in text:
        return 0.35
    return 0.1


def compute_weather_impact(
    temperature_c: float | None,
    rain_probability: float | None,
    wind_speed_kmh: float | None,
) -> float:
    """Moderate 20–80 impact score for specialist/decision layers."""
    temp = temperature_c if temperature_c is not None else 22.0
    rain = rain_probability if rain_probability is not None else 0.15
    wind = wind_speed_kmh if wind_speed_kmh is not None else 10.0
    impact = 50 + (rain * 20) + (wind * 0.5) - abs(temp - 22) * 0.3
    return round(max(20.0, min(impact, 80.0)), 1)
