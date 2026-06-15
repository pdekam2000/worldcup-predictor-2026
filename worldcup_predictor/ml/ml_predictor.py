"""ML signal layer — supplementary to rule engine, not a replacement."""

from __future__ import annotations

from dataclasses import dataclass

from worldcup_predictor.ml.feature_builder import FEATURE_COLUMNS, FeatureBuilder
from worldcup_predictor.ml.model_registry import ModelRegistry


@dataclass
class MLSignal:
    market: str
    probability: float
    confidence: float
    model_type: str
    uncertainty_note: str
    available: bool = True


class MLPredictor:
    """Produce additional ML signals with explicit uncertainty."""

    def __init__(self) -> None:
        self._registry = ModelRegistry()
        self._builder = FeatureBuilder()

    def predict_market(
        self,
        *,
        market: str,
        competition_key: str | None,
        features: dict[str, float],
    ) -> MLSignal:
        loaded = self._registry.load(market, competition_key=competition_key)
        if loaded is None:
            return MLSignal(
                market=market,
                probability=0.5,
                confidence=0.0,
                model_type="none",
                uncertainty_note="No trained model — ML signal unavailable.",
                available=False,
            )

        model, model_type = loaded
        import pandas as pd

        row = {col: features.get(col, 0.0) for col in FEATURE_COLUMNS}
        frame = pd.DataFrame([row])
        try:
            proba = model.predict_proba(frame)[0]
            p = float(max(proba))
        except Exception:  # noqa: BLE001
            pred = model.predict(frame)[0]
            p = float(pred)

        confidence = min(100.0, p * 100)
        return MLSignal(
            market=market,
            probability=round(p, 4),
            confidence=round(confidence, 2),
            model_type=model_type,
            uncertainty_note=(
                "ML signal is supplementary — combine with rule engine and weighted decision. "
                "Historical training accuracy does not guarantee future outcomes."
            ),
            available=True,
        )

    def status(self) -> list[dict]:
        return self._registry.list_models()
