"""Calibration research for goalscorer ML shadow."""

from __future__ import annotations

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from worldcup_predictor.egie.goalscorer_ml_shadow.models import CalibrationMetrics


def expected_calibration_error(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    if len(y_true) == 0:
        return 0.0
    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (y_prob >= lo) & (y_prob < hi if i < n_bins - 1 else y_prob <= hi)
        if not mask.any():
            continue
        ece += mask.mean() * abs(float(y_true[mask].mean()) - float(y_prob[mask].mean()))
    return round(float(ece), 4)


def brier_score(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    if len(y_true) == 0:
        return 0.0
    from sklearn.metrics import brier_score_loss

    return round(float(brier_score_loss(y_true, y_prob)), 4)


def calibration_curve_bins(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> list[dict]:
    bins = np.linspace(0, 1, n_bins + 1)
    rows = []
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (y_prob >= lo) & (y_prob < hi if i < n_bins - 1 else y_prob <= hi)
        if not mask.any():
            continue
        rows.append({
            "bin": f"{lo:.2f}-{hi:.2f}",
            "n": int(mask.sum()),
            "mean_pred": round(float(y_prob[mask].mean()), 4),
            "actual_rate": round(float(y_true[mask].mean()), 4),
        })
    return rows


def platt_calibrate(y_val: np.ndarray, p_val: np.ndarray, p_test: np.ndarray) -> np.ndarray:
    lr = LogisticRegression(max_iter=500)
    lr.fit(p_val.reshape(-1, 1), y_val)
    return lr.predict_proba(p_test.reshape(-1, 1))[:, 1]


def isotonic_calibrate(y_val: np.ndarray, p_val: np.ndarray, p_test: np.ndarray) -> np.ndarray:
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(p_val, y_val)
    return iso.predict(p_test)


def evaluate_calibration_methods(
    y_val: np.ndarray,
    p_val: np.ndarray,
    y_test: np.ndarray,
    p_test: np.ndarray,
    *,
    market: str,
    model: str,
) -> tuple[list[CalibrationMetrics], dict[str, list[dict]]]:
    methods = {
        "raw": p_test,
        "platt": platt_calibrate(y_val, p_val, p_test),
        "isotonic": isotonic_calibrate(y_val, p_val, p_test),
    }
    metrics: list[CalibrationMetrics] = []
    curves: dict[str, list[dict]] = {}
    for name, probs in methods.items():
        metrics.append(
            CalibrationMetrics(
                market=market,
                model=model,
                method=name,
                ece=expected_calibration_error(y_test, probs),
                brier=brier_score(y_test, probs),
                n_samples=len(y_test),
            )
        )
        curves[name] = calibration_curve_bins(y_test, probs)
    return metrics, curves
