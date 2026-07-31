"""Distance metrics for day similarity — research-only, outcomes unused."""

from __future__ import annotations

import numpy as np


def euclidean(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(a - b))


def manhattan(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.sum(np.abs(a - b)))


def cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na < 1e-12 or nb < 1e-12:
        return 1.0
    sim = float(np.dot(a, b) / (na * nb))
    return float(1.0 - sim)


def mahalanobis(a: np.ndarray, b: np.ndarray, inv_cov: np.ndarray | None) -> float:
    if inv_cov is None:
        return euclidean(a, b)
    d = a - b
    try:
        return float(np.sqrt(max(0.0, d @ inv_cov @ d)))
    except Exception:
        return euclidean(a, b)


def mixed_distance(
    a: np.ndarray,
    b: np.ndarray,
    *,
    weights: np.ndarray | None = None,
    categorical_mask: np.ndarray | None = None,
) -> float:
    """Weighted L2 on numeric + absolute diff on categorical dims."""
    w = weights if weights is not None else np.ones(len(a))
    if categorical_mask is None:
        categorical_mask = np.zeros(len(a), dtype=bool)
    num = ~categorical_mask
    dist = 0.0
    if np.any(num):
        diff = (a[num] - b[num]) * w[num]
        dist += float(np.sum(diff ** 2))
    if np.any(categorical_mask):
        dist += float(np.sum(np.abs(a[categorical_mask] - b[categorical_mask]) * w[categorical_mask]))
    return float(np.sqrt(max(0.0, dist)))


def pairwise_distances(
    X: np.ndarray,
    method: str = "euclidean",
    *,
    inv_cov: np.ndarray | None = None,
    weights: np.ndarray | None = None,
) -> np.ndarray:
    n = X.shape[0]
    D = np.zeros((n, n), dtype=float)
    for i in range(n):
        for j in range(i + 1, n):
            if method == "manhattan":
                d = manhattan(X[i], X[j])
            elif method == "cosine":
                d = cosine_distance(X[i], X[j])
            elif method == "mahalanobis":
                d = mahalanobis(X[i], X[j], inv_cov)
            elif method == "mixed":
                d = mixed_distance(X[i], X[j], weights=weights)
            else:
                d = euclidean(X[i], X[j])
            D[i, j] = D[j, i] = d
    return D


def stable_inv_cov(X: np.ndarray) -> np.ndarray | None:
    if X.shape[0] < X.shape[1] + 2:
        return None
    cov = np.cov(X, rowvar=False)
    if cov.ndim < 2:
        return None
    cov = cov + np.eye(cov.shape[0]) * 1e-6
    try:
        return np.linalg.pinv(cov)
    except Exception:
        return None
