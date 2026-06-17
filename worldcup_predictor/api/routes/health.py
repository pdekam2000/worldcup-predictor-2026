"""Health and version endpoints."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])

PROJECT_NAME = "WorldCup Predictor 2026"
API_VERSION = "1.0"


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/version")
def version() -> dict[str, str]:
    return {"project": PROJECT_NAME, "version": API_VERSION}
