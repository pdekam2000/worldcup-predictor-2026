"""ML model placeholder — LightGBM/CatBoost when sufficient data (Phase 51G)."""

from __future__ import annotations

from typing import Any


class GoalTimingMLModel:
    def is_trained(self) -> bool:
        return False

    def predict(self, features: dict[str, Any]) -> dict[str, Any] | None:
        return None
