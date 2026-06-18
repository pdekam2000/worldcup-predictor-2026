"""FastAPI application entry point."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from worldcup_predictor.api.routes.admin import router as admin_router
from worldcup_predictor.api.routes.auth import router as auth_router
from worldcup_predictor.api.routes.health import router as health_router
from worldcup_predictor.api.routes.matches import router as matches_router
from worldcup_predictor.api.routes.predictions import router as predictions_router
from worldcup_predictor.api.routes.user import router as user_router
from worldcup_predictor.config.production_guard import assert_production_ready
from worldcup_predictor.config.settings import get_settings

_DEV_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def _build_cors_origins() -> list[str]:
    extra = os.getenv("CORS_ALLOWED_ORIGINS", "")
    extra_list = [origin.strip() for origin in extra.split(",") if origin.strip()]
    if os.getenv("APP_ENV", "").strip().lower() == "production":
        return extra_list
    return _DEV_CORS_ORIGINS + extra_list


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    settings = get_settings()
    if settings.is_production:
        assert_production_ready(settings)
    yield


app = FastAPI(
    title="WorldCup Predictor 2026 API",
    description="HTTP bridge to the WorldCup Predictor prediction engine.",
    version="1.0",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_build_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(user_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(matches_router, prefix="/api")
app.include_router(predictions_router, prefix="/api")
