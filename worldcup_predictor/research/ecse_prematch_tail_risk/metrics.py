"""Detector evaluation metrics — ROC, PR, calibration."""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def binary_metrics(y_true: list[int], y_prob: list[float], *, threshold: float = 0.45) -> dict[str, Any]:
    y = np.array(y_true, dtype=int)
    p = np.array(y_prob, dtype=float)
    pred = (p >= threshold).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    tn = int(((pred == 0) & (y == 0)).sum())
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    base_rate = float(y.mean()) if len(y) else 0.0
    brier = float(np.mean((p - y) ** 2)) if len(y) else 0.0

    try:
        from sklearn.metrics import average_precision_score, roc_auc_score

        roc = float(roc_auc_score(y, p)) if len(set(y)) > 1 else None
        pr = float(average_precision_score(y, p)) if y.sum() else None
    except Exception:
        roc = pr = None

    # Calibration bins
    bins = np.linspace(0, 1, 11)
    cal_errors = []
    for i in range(len(bins) - 1):
        mask = (p >= bins[i]) & (p < bins[i + 1])
        if mask.sum() >= 10:
            cal_errors.append(abs(p[mask].mean() - y[mask].mean()))
    ece = float(np.mean(cal_errors)) if cal_errors else None

    return {
        "n": len(y),
        "base_rate": round(base_rate, 4),
        "threshold": threshold,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "roc_auc": round(roc, 4) if roc is not None else None,
        "pr_auc": round(pr, 4) if pr is not None else None,
        "brier_score": round(brier, 4),
        "calibration_error": round(ece, 4) if ece is not None else None,
        "detector_positive_count": int(pred.sum()),
        "false_positive_rate": round(fp / (fp + tn), 4) if (fp + tn) else 0.0,
        "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "precision_above_base_multiple": round(precision / base_rate, 4) if base_rate > 0 and precision else None,
    }


def tier_metrics(y_true: list[int], tiers: list[str]) -> dict[str, Any]:
    high_mask = [t in ("HIGH", "VERY_HIGH") for t in tiers]
    y = np.array(y_true, dtype=int)
    m = np.array(high_mask, dtype=bool)
    if m.sum() == 0:
        return {"high_tier_count": 0, "high_tier_precision": None, "high_tier_recall": None}
    tp = int((m & (y == 1)).sum())
    fp = int((m & (y == 0)).sum())
    fn = int((~m & (y == 1)).sum())
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    return {
        "high_tier_count": int(m.sum()),
        "high_tier_precision": round(prec, 4),
        "high_tier_recall": round(rec, 4),
        "high_tier_coverage_of_true_tails": round(rec, 4),
    }
