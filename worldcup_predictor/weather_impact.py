"""Weather impact scoring and match-level impact analysis — Phase 43."""

from __future__ import annotations

from typing import Any, Literal

WeatherRiskLevel = Literal["low", "medium", "high"]


def rain_probability_from_condition(condition: str, *, rain_mm: float | None = None) -> float:
    text = (condition or "").lower()
    if rain_mm is not None and rain_mm > 0:
        return min(0.55 + rain_mm * 0.15, 0.95)
    if any(word in text for word in ("rain", "drizzle", "storm", "thunder", "shower")):
        return 0.65
    if "cloud" in text or "overcast" in text:
        return 0.35
    return 0.1


def compute_weather_impact(
    temperature_c: float | None,
    rain_probability: float | None,
    wind_speed_kmh: float | None,
    *,
    wind_gust_kmh: float | None = None,
    humidity_pct: float | None = None,
) -> float:
    """Moderate 20–80 impact score for specialist/decision layers."""
    temp = temperature_c if temperature_c is not None else 22.0
    rain = rain_probability if rain_probability is not None else 0.15
    wind = wind_speed_kmh if wind_speed_kmh is not None else 10.0
    gust = wind_gust_kmh if wind_gust_kmh is not None else wind
    effective_wind = max(wind, gust * 0.85)
    humidity = humidity_pct if humidity_pct is not None else 55.0

    impact = 50.0
    impact += rain * 22.0
    impact += effective_wind * 0.45
    impact -= abs(temp - 22.0) * 0.35
    if humidity > 85 and rain > 0.3:
        impact += 4.0
    if temp >= 32:
        impact += (temp - 32) * 0.8
    if temp <= 5:
        impact += (5 - temp) * 0.6
    return round(max(20.0, min(impact, 80.0)), 1)


def classify_weather_risk(
    *,
    temperature_c: float | None,
    rain_probability: float | None,
    wind_speed_kmh: float | None,
    wind_gust_kmh: float | None = None,
    severe_alerts: list[Any] | None = None,
) -> WeatherRiskLevel:
    rain = float(rain_probability or 0.0)
    wind = float(wind_speed_kmh or 0.0)
    gust = float(wind_gust_kmh or wind)
    temp = temperature_c if temperature_c is not None else 22.0
    alerts = severe_alerts or []

    if alerts:
        return "high"
    if rain >= 0.6 or gust >= 45 or wind >= 40 or temp >= 35 or temp <= -2:
        return "high"
    if rain >= 0.35 or gust >= 28 or wind >= 25 or temp >= 30 or temp <= 5:
        return "medium"
    return "low"


def _impact_factor_messages(
    *,
    temperature_c: float | None,
    rain_probability: float | None,
    rain_mm: float | None,
    wind_speed_kmh: float | None,
    wind_gust_kmh: float | None,
    humidity_pct: float | None,
    severe_alerts: list[Any] | None,
) -> list[str]:
    factors: list[str] = []
    rain = float(rain_probability or 0.0)
    wind = float(wind_speed_kmh or 0.0)
    gust = float(wind_gust_kmh or 0.0)
    temp = temperature_c if temperature_c is not None else 22.0
    humidity = float(humidity_pct or 0.0)

    if rain >= 0.5 or (rain_mm is not None and rain_mm >= 2.0):
        factors.append("Heavy rain expected — may reduce passing quality and technical control.")
    elif rain >= 0.35:
        factors.append("Moderate rain risk — slippery surface may affect attacking efficiency.")

    if gust >= 35 or wind >= 30:
        factors.append("Strong wind — crossing accuracy and long-ball volatility increase.")
    elif wind >= 20:
        factors.append("Elevated wind — set pieces and long passes less predictable.")

    if temp >= 32:
        factors.append("Extreme heat — fatigue risk and tempo reduction likely.")
    elif temp >= 28:
        factors.append("Warm conditions — stamina load may rise in second half.")

    if temp <= 5:
        factors.append("Very cold conditions — lower intensity and slower ball movement possible.")
    elif temp <= 10:
        factors.append("Cold pitch conditions — may slightly reduce open-play tempo.")

    if humidity >= 85 and rain >= 0.3:
        factors.append("High humidity with rain — heavy pitch conditions.")

    for alert in severe_alerts or []:
        if isinstance(alert, dict):
            headline = alert.get("headline") or alert.get("event") or alert.get("desc")
            if headline:
                factors.append(f"Severe weather alert: {headline}")
        elif isinstance(alert, str) and alert.strip():
            factors.append(f"Severe weather alert: {alert.strip()}")

    if not factors:
        factors.append("Conditions within normal range for outdoor football.")
    return factors


def build_weather_summary(
    *,
    weather_risk_level: WeatherRiskLevel,
    impact_factors: list[str],
    condition: str | None = None,
) -> str:
    lead = {
        "low": "Weather impact is low.",
        "medium": "Weather impact is medium.",
        "high": "Weather impact is high.",
    }[weather_risk_level]
    detail = impact_factors[0] if impact_factors else "No significant weather disruption expected."
    cond = f" ({condition})" if condition else ""
    return f"{lead}{cond} {detail}".strip()


def analyze_weather_match_impact(normalized: dict[str, Any]) -> dict[str, Any]:
    """Derive impact score, risk level, summary, and factor list from normalized weather."""
    temp = _float(normalized.get("temperature_c"))
    feels = _float(normalized.get("feels_like_c"))
    rain_prob = _float(normalized.get("rain_probability"))
    rain_mm = _float(normalized.get("rain_mm"))
    wind = _float(normalized.get("wind_speed_kmh"))
    gust = _float(normalized.get("wind_gust_kmh"))
    humidity = _float(normalized.get("humidity_pct"))
    alerts = normalized.get("severe_weather_alerts")
    alert_list = alerts if isinstance(alerts, list) else []

    impact_score = compute_weather_impact(
        temp,
        rain_prob,
        wind,
        wind_gust_kmh=gust,
        humidity_pct=humidity,
    )
    risk_level = classify_weather_risk(
        temperature_c=temp,
        rain_probability=rain_prob,
        wind_speed_kmh=wind,
        wind_gust_kmh=gust,
        severe_alerts=alert_list,
    )
    factors = _impact_factor_messages(
        temperature_c=temp,
        rain_probability=rain_prob,
        rain_mm=rain_mm,
        wind_speed_kmh=wind,
        wind_gust_kmh=gust,
        humidity_pct=humidity,
        severe_alerts=alert_list,
    )
    summary = build_weather_summary(
        weather_risk_level=risk_level,
        impact_factors=factors,
        condition=str(normalized.get("condition") or ""),
    )
    return {
        "weather_impact_score": impact_score,
        "weather_risk_level": risk_level,
        "weather_summary": summary,
        "impact_factors": factors,
        "feels_like_c": feels,
    }


def _float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
