"""FastAPI bridge for WorldCup Predictor 2026 — UI-facing HTTP layer only."""

from __future__ import annotations

from typing import Any

__all__ = ["app"]


def __getattr__(name: str) -> Any:
    if name == "app":
        from worldcup_predictor.api.main import app as fastapi_app

        return fastapi_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
