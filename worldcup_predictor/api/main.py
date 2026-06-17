"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from worldcup_predictor.api.routes.health import router as health_router
from worldcup_predictor.api.routes.matches import router as matches_router
from worldcup_predictor.api.routes.predictions import router as predictions_router

# Local Base44 / Vite dev servers — do not use "*" in production.
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app = FastAPI(
    title="WorldCup Predictor 2026 API",
    description="HTTP bridge to the WorldCup Predictor prediction engine.",
    version="1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(matches_router, prefix="/api")
app.include_router(predictions_router, prefix="/api")
