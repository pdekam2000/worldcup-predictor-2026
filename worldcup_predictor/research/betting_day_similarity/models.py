"""Lightweight model container for locked similarity research state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from worldcup_predictor.research.betting_day_similarity.preprocessing import FeatureScaler


@dataclass
class LockedSimilarityModel:
    method: str
    k: int
    n_regimes: int
    regime_method: str
    feature_names: list[str]
    scaler: FeatureScaler
    centroids: np.ndarray
    inv_cov: np.ndarray | None
    train_min: np.ndarray
    train_max: np.ndarray
    nn_p95: float
    centroid_p95: float
    overlay_cfg: dict[str, Any] = field(default_factory=dict)
    seed: int = 20260731
    research_only: bool = True
