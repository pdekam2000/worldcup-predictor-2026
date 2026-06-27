"""Health and version endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from worldcup_predictor.config.app_version import build_version_payload
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
def version() -> dict[str, Any]:
    """Application deploy version — used by global UI badge (Hotfix Pack 4)."""
    payload = build_version_payload()
    return {
        **payload,
        "project": PROJECT_NAME,
        "api_version": API_VERSION,
    }
