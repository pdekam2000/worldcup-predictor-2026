#!/usr/bin/env python3
"""One-off: verify weather provider fetch for upcoming city."""
import os
import sys
from datetime import datetime

os.environ.setdefault("APP_ENV", "production")
sys.path.insert(0, "/opt/worldcup-predictor")

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.providers.weather_provider import WeatherProvider

settings = get_settings()
print("weather_configured", settings.weather_provider_configured)
wp = WeatherProvider(settings)
result = wp.get_venue_forecast(
    city="Los Angeles",
    country=None,
    kickoff_utc=datetime.fromisoformat("2026-06-21T19:00:00+00:00"),
)
data = result.data or {}
print("available", data.get("available"))
print("condition", data.get("condition"))
print("temp_c", data.get("temperature_c"))
print("error", result.error)
