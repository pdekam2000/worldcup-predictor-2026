"""Training-only preprocessing — research-only."""

from __future__ import annotations

from typing import Any

import numpy as np


class FeatureScaler:
    """Deterministic z-score scaler fit on training only."""

    def __init__(self) -> None:
        self.mean_: np.ndarray | None = None
        self.std_: np.ndarray | None = None
        self.feature_names: list[str] = []
        self.fitted = False

    def fit(self, X: np.ndarray, feature_names: list[str]) -> "FeatureScaler":
        self.feature_names = list(feature_names)
        self.mean_ = np.nanmean(X, axis=0)
        self.std_ = np.nanstd(X, axis=0)
        self.std_ = np.where(self.std_ < 1e-9, 1.0, self.std_)
        self.fitted = True
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        if not self.fitted or self.mean_ is None or self.std_ is None:
            raise RuntimeError("Scaler not fit")
        X2 = np.where(np.isnan(X), self.mean_, X)
        return (X2 - self.mean_) / self.std_


class CategoricalEncoder:
    """Deterministic ordinal encoding fit on training categories only."""

    def __init__(self) -> None:
        self.maps: dict[str, dict[str, int]] = {}
        self.fitted = False

    def fit(self, rows: list[dict[str, Any]], keys: list[str]) -> "CategoricalEncoder":
        for k in keys:
            vals = sorted({str(r.get(k, "UNK")) for r in rows})
            self.maps[k] = {v: i for i, v in enumerate(vals)}
        self.fitted = True
        return self

    def transform_row(self, row: dict[str, Any]) -> dict[str, float]:
        out = {}
        for k, mp in self.maps.items():
            v = str(row.get(k, "UNK"))
            out[k] = float(mp.get(v, -1))
        return out


def matrix_from_days(
    days: list[dict[str, Any]],
    feature_names: list[str],
) -> np.ndarray:
    rows = []
    for d in days:
        feats = d.get("features") or {}
        rows.append([float(feats.get(n, np.nan)) for n in feature_names])
    return np.asarray(rows, dtype=float)


def train_impute(X: np.ndarray, train_mean: np.ndarray) -> np.ndarray:
    """Impute missing with training means only — no future data."""
    return np.where(np.isnan(X), train_mean, X)
