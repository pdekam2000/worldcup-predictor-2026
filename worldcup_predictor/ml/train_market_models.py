"""Train simple scikit-learn market models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from worldcup_predictor.ml.feature_builder import FeatureBuilder
from worldcup_predictor.ml.model_registry import ModelRegistry

MIN_SAMPLES = 30


@dataclass
class TrainResult:
    market: str
    model_type: str
    samples: int
    trained: bool = False
    accuracy: float | None = None
    warnings: list[str] = field(default_factory=list)


def train_market_models(
    *,
    competition_key: str | None = None,
    markets: tuple[str, ...] = ("1x2", "over_under_2_5"),
) -> list[TrainResult]:
    try:
        from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import cross_val_score
    except ImportError:
        return [
            TrainResult(
                market=m,
                model_type="none",
                samples=0,
                trained=False,
                warnings=["scikit-learn not installed — run: pip install scikit-learn"],
            )
            for m in markets
        ]

    builder = FeatureBuilder()
    df = builder.build_training_frame(competition_key=competition_key)
    registry = ModelRegistry()
    results: list[TrainResult] = []

    model_candidates = [
        ("logistic_regression", LogisticRegression(max_iter=500)),
        ("random_forest", RandomForestClassifier(n_estimators=100, random_state=42)),
        ("gradient_boosting", GradientBoostingClassifier(random_state=42)),
    ]

    for market in markets:
        market_df = df[df["market"] == market] if not df.empty else df
        result = TrainResult(market=market, model_type="none", samples=len(market_df))
        if len(market_df) < MIN_SAMPLES:
            result.warnings.append(
                f"Only {len(market_df)} samples — minimum {MIN_SAMPLES} required for stable ML training."
            )
            results.append(result)
            continue

        x = builder.feature_matrix(market_df)
        y = market_df["label"]
        best_score = -1.0
        best_name = ""
        best_model = None
        for name, model in model_candidates:
            try:
                scores = cross_val_score(model, x, y, cv=min(5, len(market_df)), scoring="accuracy")
                avg = float(scores.mean())
                if avg > best_score:
                    best_score = avg
                    best_name = name
                    best_model = model
            except Exception as exc:  # noqa: BLE001
                result.warnings.append(f"{name} failed: {exc}")

        if best_model is None:
            result.warnings.append("No model converged.")
            results.append(result)
            continue

        best_model.fit(x, y)
        registry.save(market, best_name, best_model, competition_key=competition_key)
        result.trained = True
        result.model_type = best_name
        result.accuracy = round(best_score, 4)
        results.append(result)

    return results
