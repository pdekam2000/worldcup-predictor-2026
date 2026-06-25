"""Quick weather provider test — no secrets printed."""

from __future__ import annotations

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.providers.weather_provider import WeatherProvider

s = get_settings()
print("configured=", s.weather_provider_configured)
p = WeatherProvider(s)
r = p.get_venue_forecast(city="Toronto")
data = r.data or {}
print("fetch_ok=", r.available)
print("error=", r.error)
if data.get("available"):
    print("risk=", data.get("weather_risk_level"))
    print("temp=", data.get("temperature_c"))
    print("summary_len=", len(str(data.get("weather_summary") or "")))
