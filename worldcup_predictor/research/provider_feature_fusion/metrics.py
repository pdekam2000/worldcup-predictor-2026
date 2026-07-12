"""Evaluation metrics for shadow fusion experiments."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    brier_score_loss,
    log_loss,
    precision_recall_fscore_support,
)


def _safe_log_loss(y_true: list[str], proba: np.ndarray, classes: list[str]) -> float | None:
    if proba is None or not len(y_true):
        return None
    idx = {c: i for i, c in enumerate(classes)}
    mask = [i for i, yt in enumerate(y_true) if yt in idx]
    if not mask:
        return None
    y_idx = [idx[y_true[i]] for i in mask]
    pr = proba[mask]
    return float(log_loss(y_idx, pr, labels=list(range(len(classes)))))


def _multiclass_brier(y_true: list[str], proba: np.ndarray, classes: list[str]) -> float | None:
    if proba is None or not len(y_true):
        return None
    idx = {c: i for i, c in enumerate(classes)}
    rows = []
    for yt, row in zip(y_true, proba):
        if yt not in idx:
            continue
        onehot = np.zeros(len(classes))
        onehot[idx[yt]] = 1.0
        rows.append(np.sum((row - onehot) ** 2))
    return float(np.mean(rows)) if rows else None


def calibration_buckets(
    y_true: list[str],
    proba: np.ndarray,
    classes: list[str],
    *,
    bins: tuple[tuple[float, float], ...] = ((0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)),
) -> list[dict[str, Any]]:
    if proba is None:
        return []
    idx = {c: i for i, c in enumerate(classes)}
    out = []
    for lo, hi in bins:
        confs: list[float] = []
        hits: list[int] = []
        for yt, row in zip(y_true, proba):
            if yt not in idx:
                continue
            pred_i = int(np.argmax(row))
            conf = float(row[pred_i])
            if lo <= conf < hi:
                confs.append(conf)
                hits.append(1 if classes[pred_i] == yt else 0)
        if confs:
            out.append(
                {
                    "bin": f"{lo:.2f}-{hi:.2f}",
                    "count": len(confs),
                    "mean_confidence": round(float(np.mean(confs)), 4),
                    "accuracy": round(float(np.mean(hits)), 4),
                }
            )
    return out


def evaluate_classification(
    y_true: list[str],
    y_pred: list[str],
    proba: np.ndarray | None,
    classes: list[str],
) -> dict[str, Any]:
    prec, rec, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=classes, average="macro", zero_division=0
    )
    cal_err = None
    buckets = calibration_buckets(y_true, proba, classes) if proba is not None else []
    if buckets:
        cal_err = round(
            float(np.mean([abs(b["mean_confidence"] - b["accuracy"]) for b in buckets])),
            4,
        )
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "balanced_accuracy": round(float(balanced_accuracy_score(y_true, y_pred)), 4),
        "log_loss": _safe_log_loss(y_true, proba, classes),
        "brier_score": _multiclass_brier(y_true, proba, classes),
        "calibration_error": cal_err,
        "calibration_buckets": buckets,
        "precision_macro": round(float(prec), 4),
        "recall_macro": round(float(rec), 4),
        "f1_macro": round(float(f1), 4),
        "n": len(y_true),
    }


def evaluate_binary(
    y_true: list[int],
    y_pred: list[int],
    proba_pos: np.ndarray | None,
) -> dict[str, Any]:
    y_t = [str(v) for v in y_true]
    y_p = [str(v) for v in y_pred]
    out: dict[str, Any] = {
        "accuracy": round(float(accuracy_score(y_t, y_p)), 4),
        "balanced_accuracy": round(float(balanced_accuracy_score(y_t, y_p)), 4),
        "n": len(y_true),
    }
    if proba_pos is not None and len(proba_pos) == len(y_true):
        out["log_loss"] = float(log_loss(y_true, proba_pos, labels=[0, 1]))
        out["brier_score"] = float(brier_score_loss(y_true, proba_pos))
        buckets = []
        y_arr = np.asarray(y_true)
        p_arr = np.asarray(y_pred)
        for lo, hi in ((0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)):
            mask = (proba_pos >= lo) & (proba_pos < hi)
            if mask.any():
                buckets.append(
                    {
                        "bin": f"{lo:.2f}-{hi:.2f}",
                        "count": int(mask.sum()),
                        "mean_confidence": round(float(proba_pos[mask].mean()), 4),
                        "accuracy": round(float(np.mean(y_arr[mask] == p_arr[mask])), 4),
                    }
                )
        out["calibration_buckets"] = buckets
        if buckets:
            out["calibration_error"] = round(
                float(np.mean([abs(b["mean_confidence"] - b["accuracy"]) for b in buckets])),
                4,
            )
    return out


def _poisson_pmf(k: int, lam: float) -> float:
    lam = max(lam, 0.05)
    from math import exp, factorial

    return float(exp(-lam) * (lam**k) / factorial(k))


def poisson_score_topk(home_xg: float, away_xg: float, actual_h: int, actual_a: int, k: int = 5) -> dict[str, Any]:
    """ECSE proxy: Poisson scoreline ranking from xG or implied goal rates."""
    scores: list[tuple[str, float]] = []
    for h in range(6):
        for a in range(6):
            p = _poisson_pmf(h, home_xg) * _poisson_pmf(a, away_xg)
            scores.append((f"{h}-{a}", float(p)))
    scores.sort(key=lambda x: x[1], reverse=True)
    actual = f"{actual_h}-{actual_a}"
    top = [s for s, _ in scores[:k]]
    rank = next((i + 1 for i, s in enumerate(scores) if s[0] == actual), None)
    mass = sum(p for _, p in scores[:k])
    return {
        "actual_score": actual,
        "top_scores": top,
        f"top{k}_hit": actual in top,
        "actual_rank": rank,
        f"top{k}_mass": round(mass, 4),
    }
