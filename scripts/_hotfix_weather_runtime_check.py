#!/usr/bin/env python3
import os
pid = int(os.popen("systemctl show worldcup-api -p MainPID --value").read().strip())
raw = open(f"/proc/{pid}/environ", "rb").read().split(b"\0")
weather = {}
for item in raw:
    if item.startswith(b"WEATHER_"):
        k, _, v = item.partition(b"=")
        weather[k.decode()] = len(v)
print("process_weather_keys", sorted(weather.keys()))
print("WEATHER_API_KEY_value_len", weather.get("WEATHER_API_KEY", 0))
print("WEATHER_CACHE_TTL_SECONDS_value", end=" ")
for item in raw:
    if item.startswith(b"WEATHER_CACHE_TTL_SECONDS="):
        print(item.split(b"=", 1)[1].decode())
        break
else:
    print("missing")

from worldcup_predictor.config.settings import get_settings
s = get_settings()
print("get_settings_weather_configured", s.weather_provider_configured)
print("get_settings_weather_key_len", len(s.weather_api_key.strip()))
