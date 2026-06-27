"""Weather intelligence engine — normalize, analyze, and expose API blocks — Phase 43."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from worldcup_predictor.weather_impact import analyze_weather_match_impact, rain_probability_from_condition


def enrich_normalized_weather(raw: dict[str, Any]) -> dict[str, Any]:
    """Apply match impact analysis to a normalized weather dict (no provider calls)."""
    if not raw or not raw.get("available"):
        return {
            "available": False,
            "source": raw.get("source") or raw.get("provider") or "none",
            "data_source": "none",
        }
    out = dict(raw)
    out.pop("raw", None)
    analysis = analyze_weather_match_impact(out)
    out.update(analysis)
    return out


def build_weather_intelligence(
    weather: dict[str, Any] | None,
    *,
    venue: str | None = None,
    kickoff_utc: str | None = None,
) -> dict[str, Any]:
    """Build specialist/API weather intelligence block from report weather."""
    if not weather or not weather.get("available"):
        return build_weather_api_block(None, venue=venue, kickoff_utc=kickoff_utc)
    return build_weather_api_block(enrich_normalized_weather(weather), venue=venue, kickoff_utc=kickoff_utc)


def build_weather_api_block(
    normalized: dict[str, Any] | None,
    *,
    venue: str | None = None,
    kickoff_utc: str | None = None,
) -> dict[str, Any]:
    """Public API shape for predict responses — no secrets, no raw provider payload."""
    if not normalized or not normalized.get("available"):
        block: dict[str, Any] = {
            "available": False,
            "source": (normalized or {}).get("source") or "none",
            "data_source": "none",
            "venue": venue,
            "kickoff_utc": kickoff_utc,
            "weather_summary": None,
            "weather_impact_score": None,
            "weather_risk_level": None,
        }
        reason = (normalized or {}).get("unavailable_reason")
        if reason:
            block["unavailable_reason"] = str(reason)
        if (normalized or {}).get("provider_now_configured"):
            block["provider_now_configured"] = True
        note = (normalized or {}).get("note")
        if note:
            block["note"] = str(note)
        return block

    kickoff_local = normalized.get("kickoff_local_weather")
    if not isinstance(kickoff_local, dict):
        kickoff_local = None

    alerts = normalized.get("severe_weather_alerts") or []
    if not isinstance(alerts, list):
        alerts = []

    return {
        "available": True,
        "source": normalized.get("source") or normalized.get("provider") or "live",
        "data_source": normalized.get("cache_source") or normalized.get("source") or "live",
        "venue": venue or normalized.get("venue"),
        "kickoff_utc": kickoff_utc or normalized.get("kickoff_utc"),
        "condition": normalized.get("condition"),
        "temperature_c": normalized.get("temperature_c"),
        "feels_like_c": normalized.get("feels_like_c"),
        "humidity_pct": normalized.get("humidity_pct"),
        "rain_probability": normalized.get("rain_probability"),
        "rain_mm": normalized.get("rain_mm"),
        "wind_speed_kmh": normalized.get("wind_speed_kmh"),
        "wind_gust_kmh": normalized.get("wind_gust_kmh"),
        "visibility_km": normalized.get("visibility_km"),
        "cloud_cover_pct": normalized.get("cloud_cover_pct"),
        "kickoff_local_weather": kickoff_local,
        "severe_weather_alerts": [
            {
                "headline": a.get("headline") or a.get("event") or a.get("desc"),
                "severity": a.get("severity"),
                "effective": a.get("effective"),
                "expires": a.get("expires"),
            }
            for a in alerts
            if isinstance(a, dict)
        ][:5],
        "weather_impact_score": normalized.get("weather_impact_score"),
        "weather_risk_level": normalized.get("weather_risk_level"),
        "weather_summary": normalized.get("weather_summary"),
        "impact_factors": list(normalized.get("impact_factors") or [])[:6],
        "cached": bool(normalized.get("cached")),
    }


def merge_kickoff_weather_fields(
    base: dict[str, Any],
    kickoff_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    """Prefer kickoff-hour forecast values when available."""
    if not kickoff_snapshot:
        return base
    out = dict(base)
    for key in (
        "temperature_c",
        "feels_like_c",
        "humidity_pct",
        "rain_probability",
        "rain_mm",
        "wind_speed_kmh",
        "wind_gust_kmh",
        "visibility_km",
        "cloud_cover_pct",
        "condition",
    ):
        val = kickoff_snapshot.get(key)
        if val is not None:
            out[key] = val
    out["kickoff_local_weather"] = kickoff_snapshot
    return out


def kickoff_snapshot_from_hour(
    hour_row: dict[str, Any] | None,
    *,
    provider: str,
) -> dict[str, Any] | None:
    if not hour_row:
        return None
    if provider == "weatherapi":
        condition = (hour_row.get("condition") or {}).get("text", "")
        rain_mm = _float((hour_row.get("precip_mm")))
        return {
            "temperature_c": hour_row.get("temp_c"),
            "feels_like_c": hour_row.get("feelslike_c"),
            "humidity_pct": hour_row.get("humidity"),
            "rain_probability": max(
                rain_probability_from_condition(condition, rain_mm=rain_mm),
                _float(hour_row.get("chance_of_rain")) / 100.0 if hour_row.get("chance_of_rain") is not None else 0.0,
            ),
            "rain_mm": rain_mm,
            "wind_speed_kmh": hour_row.get("wind_kph"),
            "wind_gust_kmh": hour_row.get("gust_kph"),
            "visibility_km": hour_row.get("vis_km"),
            "cloud_cover_pct": hour_row.get("cloud"),
            "condition": condition,
            "time_local": hour_row.get("time"),
        }
    main = hour_row.get("main") or {}
    weather = (hour_row.get("weather") or [{}])[0]
    condition = weather.get("description") or weather.get("main") or ""
    rain_mm = _float((hour_row.get("rain") or {}).get("3h"))
    wind = hour_row.get("wind") or {}
    return {
        "temperature_c": main.get("temp"),
        "feels_like_c": main.get("feels_like"),
        "humidity_pct": main.get("humidity"),
        "rain_probability": rain_probability_from_condition(condition, rain_mm=rain_mm),
        "rain_mm": rain_mm,
        "wind_speed_kmh": _wind_to_kmh(_float(wind.get("speed"))),
        "wind_gust_kmh": _wind_to_kmh(_float(wind.get("gust"))),
        "visibility_km": _visibility_km(hour_row.get("visibility")),
        "cloud_cover_pct": (hour_row.get("clouds") or {}).get("all"),
        "condition": condition,
        "time_local": hour_row.get("dt_txt"),
    }


def pick_weatherapi_kickoff_hour(
    payload: dict[str, Any],
    kickoff_utc: datetime | None,
) -> dict[str, Any] | None:
    if kickoff_utc is None:
        return None
    days = ((payload.get("forecast") or {}).get("forecastday") or [])
    hours: list[dict[str, Any]] = []
    for day in days:
        hours.extend(day.get("hour") or [])
    return _pick_nearest_hour(hours, kickoff_utc, time_key="time_epoch")


def pick_openweather_kickoff_hour(
    payload: dict[str, Any],
    kickoff_utc: datetime | None,
) -> dict[str, Any] | None:
    if kickoff_utc is None:
        return None
    items = payload.get("list") or []
    return _pick_nearest_hour(items, kickoff_utc, time_key="dt")


def extract_severe_alerts_weatherapi(payload: dict[str, Any]) -> list[dict[str, Any]]:
    alerts = ((payload.get("alerts") or {}).get("alert") or [])
    if not isinstance(alerts, list):
        return []
    out: list[dict[str, Any]] = []
    for row in alerts:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "headline": row.get("headline") or row.get("event"),
                "severity": row.get("severity"),
                "effective": row.get("effective"),
                "expires": row.get("expires"),
                "desc": row.get("desc"),
            }
        )
    return out


def _pick_nearest_hour(
    items: list[dict[str, Any]],
    kickoff_utc: datetime,
    *,
    time_key: str,
) -> dict[str, Any] | None:
    target = kickoff_utc.timestamp()
    best: dict[str, Any] | None = None
    best_delta = float("inf")
    for item in items:
        raw = item.get(time_key)
        if raw is None and time_key == "time_epoch":
            raw = item.get("time")
        if raw is None:
            continue
        try:
            if time_key in {"time", "time_epoch"} and isinstance(raw, str):
                ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
            else:
                ts = float(raw)
        except (TypeError, ValueError):
            continue
        delta = abs(ts - target)
        if delta < best_delta:
            best_delta = delta
            best = item
    return best


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
