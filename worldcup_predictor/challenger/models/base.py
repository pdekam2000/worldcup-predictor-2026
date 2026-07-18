"""Challenger model base interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ChallengerModel(ABC):
    model_id: str
    model_version: str
    target_markets: tuple[str, ...] = ("1x2", "btts", "ou25", "exact_score")

    @abstractmethod
    def required_features(self) -> tuple[str, ...]:
        raise NotImplementedError

    @abstractmethod
    def fit(self, X, y_home, y_away, *, sample_meta: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def predict(self, X) -> dict[str, Any]:
        raise NotImplementedError

    def predict_proba(self, X) -> dict[str, Any]:
        return self.predict(X)

    def serialize_metadata(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "target_markets": list(self.target_markets),
            "is_shadow": True,
            "final_decision_authority": False,
            "public_visible": False,
        }
