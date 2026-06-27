"""Phase 43 — weather intelligence integration validation."""

from __future__ import annotations

import json
import runpy
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nPhase 43 validation: {passed}/{len(checks)} PASS")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print()


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    root = Path(__file__).resolve().parents[1]
    record("weather_intelligence_engine", (root / "worldcup_predictor/intelligence/weather_intelligence_engine.py").is_file())
    record("weather_cache_module", (root / "worldcup_predictor/providers/weather_cache.py").is_file())
    record("weather_extraction_module", (root / "worldcup_predictor/providers/weather_extraction.py").is_file())
    record("weather_accuracy_analytics", (root / "worldcup_predictor/validation/weather_accuracy_analytics.py").is_file())

    detail_src = (root / "base44-d/src/pages/PredictionDetail.jsx").read_text(encoding="utf-8")
    record("frontend_weather_section", "PredictionDetailWeatherSection" in detail_src)
    record("frontend_weather_intelligence_field", "weather_intelligence" in detail_src)
    record("frontend_weather_impact_label", "Weather Intelligence" in detail_src)

    from worldcup_predictor.config.settings import Settings
    from worldcup_predictor.intelligence.weather_intelligence_engine import (
        build_weather_api_block,
        enrich_normalized_weather,
    )
    from worldcup_predictor.providers.weather_cache import weather_cache_get, weather_cache_set
    from worldcup_predictor.validation.weather_accuracy_analytics import (
        WeatherAccuracyTracker,
        classify_weather_buckets,
    )
    from worldcup_predictor.weather_impact import analyze_weather_match_impact, classify_weather_risk

    configured = Settings.model_construct(weather_provider="weatherapi", weather_api_key="test-key")
    unconfigured = Settings.model_construct(weather_provider="weatherapi", weather_api_key="")
    record("weather_api_detected_when_key_set", configured.weather_provider_configured)
    record("weather_api_absent_without_key", not unconfigured.weather_provider_configured)

    sample = enrich_normalized_weather(
        {
            "available": True,
            "provider": "weatherapi",
            "source": "weatherapi",
            "temperature_c": 31.0,
            "feels_like_c": 34.0,
            "humidity_pct": 78,
            "rain_probability": 0.55,
            "rain_mm": 2.5,
            "wind_speed_kmh": 28.0,
            "wind_gust_kmh": 42.0,
            "visibility_km": 8.0,
            "cloud_cover_pct": 90,
            "condition": "Moderate rain",
            "kickoff_local_weather": {"temperature_c": 30.0, "condition": "Light rain"},
            "severe_weather_alerts": [],
        }
    )
    record("weather_impact_score_present", sample.get("weather_impact_score") is not None)
    record("weather_risk_level_present", sample.get("weather_risk_level") in {"low", "medium", "high"})
    record("weather_summary_present", bool(sample.get("weather_summary")))
    record("impact_factors_present", len(sample.get("impact_factors") or []) >= 1)

    api_block = build_weather_api_block(sample, venue="Test Stadium", kickoff_utc="2026-06-20T18:00:00")
    record("api_block_has_fields", all(k in api_block for k in ("temperature_c", "rain_probability", "wind_speed_kmh", "humidity_pct")))
    record("api_block_no_raw_key", "raw" not in api_block)
    block_json = json.dumps(api_block)
    record("no_api_key_leakage", "test-key" not in block_json and "appid" not in block_json.lower())

    risk = classify_weather_risk(
        temperature_c=31,
        rain_probability=0.55,
        wind_speed_kmh=28,
        wind_gust_kmh=42,
    )
    record("heavy_rain_risk_medium_or_high", risk in {"medium", "high"}, f"risk={risk}")

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        from worldcup_predictor.config.settings import Settings as S

        s = S.model_construct(api_cache_dir=str(Path(tmp) / "cache"), weather_cache_ttl_seconds=600)
        weather_cache_set("weatherapi", "London", sample, kickoff_iso="2026-06-20T18:00:00", settings=s)
        cached = weather_cache_get("weatherapi", "London", kickoff_iso="2026-06-20T18:00:00", settings=s)
        record("weather_cache_roundtrip", cached is not None and cached.get("temperature_c") == 31.0)

    buckets = classify_weather_buckets(rain_probability=0.5, wind_speed_kmh=10, temperature_c=22)
    record("bucket_rain_classified", "rain" in buckets)
    tracker = WeatherAccuracyTracker(path=Path(tempfile.mkstemp(suffix=".jsonl")[1]))
    rec = tracker.record_prediction(
        fixture_id=123,
        prediction_id="p1",
        weather=sample,
        result_status="pending",
    )
    record("accuracy_tracker_record", rec.fixture_id == 123 and "rain" in rec.buckets)
    summary = tracker.summary()
    record("accuracy_tracker_summary", summary.get("status") == "ok")

    from worldcup_predictor.providers.weather_extraction import attach_weather_to_prediction, load_weather_from_prediction
    from types import SimpleNamespace

    pred = SimpleNamespace(metadata={})
    report = SimpleNamespace(
        fixture=SimpleNamespace(venue="Stadium", kickoff_utc=None),
        weather=sample,
        supplemental_sources={},
    )
    attach_weather_to_prediction(pred, report)
    loaded = load_weather_from_prediction(pred)
    record("prediction_metadata_weather", loaded is not None and loaded.get("available") is True)

    predictions_src = (root / "worldcup_predictor/api/routes/predictions.py").read_text(encoding="utf-8")
    record("predict_payload_weather_field", "weather_intelligence" in predictions_src)

    wde_src = (root / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    record("wde_weights_unchanged", '"weather_referee_context": 0.06' in wde_src)

    scoring_src = (root / "worldcup_predictor/prediction/scoring_engine.py").read_text(encoding="utf-8")
    record("scoring_uses_weather_risk", "weather_risk_level" in scoring_src)

    from worldcup_predictor.providers.weather_provider import WeatherProvider

    provider = WeatherProvider(Settings.model_construct(weather_provider="weatherapi", weather_api_key="secret-key"))
    fake_payload = {
        "current": {
            "temp_c": 18,
            "feelslike_c": 17,
            "humidity": 60,
            "wind_kph": 12,
            "gust_kph": 20,
            "vis_km": 10,
            "cloud": 40,
            "precip_mm": 0,
            "condition": {"text": "Partly cloudy"},
        },
        "forecast": {"forecastday": [{"hour": [{"time_epoch": 1750000000, "temp_c": 19, "condition": {"text": "Cloudy"}, "chance_of_rain": 10, "wind_kph": 14, "gust_kph": 22, "humidity": 58, "vis_km": 10, "cloud": 50, "precip_mm": 0}]}]},
        "alerts": {"alert": []},
    }
    with patch("httpx.Client") as client_cls:
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = fake_payload
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__enter__.return_value.get.return_value = mock_resp
        client_cls.return_value = mock_client
        result = provider.get_venue_forecast(city="Berlin", kickoff_utc=None)
    record("weather_provider_fetch", result.available, f"error={result.error}")
    if result.data:
        record("fetched_no_secret_in_data", "secret-key" not in json.dumps(result.data))

    from fastapi.testclient import TestClient
    from worldcup_predictor.api.main import app

    client = TestClient(app)
    health = client.get("/api/health")
    record("api_health_ok", health.status_code == 200)
    acc = client.get("/api/accuracy/summary")
    record("accuracy_dashboard_ok", acc.status_code == 200)

    _report(checks)
    failed = [name for name, ok, _ in checks if not ok]
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
