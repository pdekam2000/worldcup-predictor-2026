"""Health and version endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from worldcup_predictor.config.provider_readiness import provider_diagnostic, weather_provider_status

router = APIRouter(tags=["health"])

PROJECT_NAME = "WorldCup Predictor 2026"
API_VERSION = "1.0"


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/providers")
def health_providers() -> dict[str, Any]:
    """Safe provider readiness — no secret values."""
    diag = provider_diagnostic()
    weather = weather_provider_status()
    return {
        "status": "ok",
        **weather,
        "api_football_configured": diag.get("API_FOOTBALL_KEY_present"),
        "sportmonks_configured": diag.get("SPORTMONKS_API_KEY_present"),
        "the_odds_api_configured": diag.get("THE_ODDS_API_KEY_present"),
    }


@router.get("/version")
def version() -> dict[str, str]:
    return {"project": PROJECT_NAME, "version": API_VERSION}
