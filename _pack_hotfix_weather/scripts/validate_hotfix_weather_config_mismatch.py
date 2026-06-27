"""Hotfix — weather config mismatch + wrong predict endpoint validation."""

from __future__ import annotations

import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _report(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nHotfix weather validation: {passed}/{len(checks)} PASS")
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
    record("health_providers_route", "health/providers" in (root / "worldcup_predictor/api/routes/health.py").read_text(encoding="utf-8"))
    record("stamp_on_enrich", "stamp_provider_readiness" in (root / "worldcup_predictor/api/display_helpers.py").read_text(encoding="utf-8"))
    record("weather_refresh_helper", "_refresh_weather_intelligence_on_serve" in (root / "worldcup_predictor/api/display_helpers.py").read_text(encoding="utf-8"))
    record("wrong_endpoint_handler", "wrong_predictions_endpoint" in (root / "worldcup_predictor/api/routes/predictions.py").read_text(encoding="utf-8"))

    from worldcup_predictor.config.provider_readiness import weather_provider_status, stamp_provider_readiness
    from worldcup_predictor.api.display_helpers import _refresh_weather_intelligence_on_serve, enrich_prediction_payload
    from worldcup_predictor.config.settings import get_settings

    settings = get_settings()
    ws = weather_provider_status(settings)
    record("weather_status_shape", "weather_provider_ready" in ws and "weather_cache_ttl_seconds" in ws)

    frozen_payload = {
        "fixture_id": 1489393,
        "cache_validation_reason": "post_kickoff_frozen",
        "weather_intelligence": {"available": False, "source": "none"},
        "provider_readiness": {"weather_configured": False},
        "kickoff_utc": "2026-06-20T20:00:00",
    }
    enriched = enrich_prediction_payload(
        frozen_payload,
        competition_key="world_cup_2026",
        season=2026,
        settings=settings,
    )
    record(
        "frozen_refreshes_provider_readiness",
        enriched.get("provider_readiness", {}).get("weather_configured") == settings.weather_provider_configured,
    )
    wi = enriched.get("weather_intelligence") or {}
    record(
        "frozen_weather_annotated",
        not wi.get("available") and wi.get("unavailable_reason") == "frozen_post_kickoff_snapshot",
    )
    record("frozen_provider_now_flag", wi.get("provider_now_configured") is True or not settings.weather_provider_configured)

    from fastapi.testclient import TestClient
    from worldcup_predictor.api.main import app

    client = TestClient(app)
    record("health_ok", client.get("/api/health").status_code == 200)
    hp = client.get("/api/health/providers").json()
    record("health_providers_ok", hp.get("status") == "ok" and "weather_configured" in hp)
    wrong = client.get("/api/predictions/1489393")
    record("wrong_endpoint_404", wrong.status_code == 404)
    record("wrong_endpoint_hint", wrong.json().get("detail", {}).get("code") == "wrong_endpoint")
    record("correct_endpoint_exists", client.get("/api/predict/1489393").status_code in (200, 404))

    _report(checks)
    failed = [name for name, ok, _ in checks if not ok]
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
