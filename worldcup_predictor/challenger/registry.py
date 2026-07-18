"""Challenger model registry."""

from __future__ import annotations

from typing import Any

_REGISTRY: dict[str, dict[str, Any]] = {}


def register_model(model_id: str, meta: dict[str, Any]) -> None:
    _REGISTRY[model_id] = dict(meta)


def get_model(model_id: str) -> dict[str, Any] | None:
    return _REGISTRY.get(model_id)


def list_models() -> list[dict[str, Any]]:
    return [dict(v) for v in _REGISTRY.values()]
