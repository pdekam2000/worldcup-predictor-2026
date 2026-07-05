"""Neighbor search in normalized implied-probability space."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Sequence

from worldcup_predictor.research.ecse_market_prior.types import MarketPriorRow

DistanceMetric = Literal["euclidean", "weighted_euclidean", "mahalanobis"]
WeightScheme = Literal["uniform", "gaussian"]


@dataclass
class NeighborMatch:
    row: MarketPriorRow
    distance: float
    weight: float = 1.0


def euclidean_distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def weighted_euclidean_distance(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    weights: tuple[float, float, float] = (1.0, 0.85, 1.0),
) -> float:
    return math.sqrt(sum(w * (x - y) ** 2 for w, x, y in zip(weights, a, b)))


def _regularized_cov_inverse(vectors: Sequence[tuple[float, float, float]]) -> list[list[float]]:
    if len(vectors) < 3:
        return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    dims = 3
    mean = [sum(v[i] for v in vectors) / len(vectors) for i in range(dims)]
    cov = [[0.0] * dims for _ in range(dims)]
    for v in vectors:
        for i in range(dims):
            for j in range(dims):
                cov[i][j] += (v[i] - mean[i]) * (v[j] - mean[j])
    n = max(len(vectors) - 1, 1)
    for i in range(dims):
        cov[i][i] = cov[i][i] / n + 1e-4
        for j in range(dims):
            if i != j:
                cov[i][j] /= n
    # invert 3x3
    a, b, c = cov[0]
    d, e, f = cov[1]
    g, h, i = cov[2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) < 1e-12:
        return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    inv_det = 1.0 / det
    return [
        [(e * i - f * h) * inv_det, (c * h - b * i) * inv_det, (b * f - c * e) * inv_det],
        [(f * g - d * i) * inv_det, (a * i - c * g) * inv_det, (c * d - a * f) * inv_det],
        [(d * h - e * g) * inv_det, (b * g - a * h) * inv_det, (a * e - b * d) * inv_det],
    ]


def mahalanobis_distance(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    cov_inv: list[list[float]],
) -> float:
    diff = [a[i] - b[i] for i in range(3)]
    tmp = [sum(cov_inv[i][j] * diff[j] for j in range(3)) for i in range(3)]
    val = sum(diff[i] * tmp[i] for i in range(3))
    return math.sqrt(max(val, 0.0))


def compute_distance(
    target_vec: tuple[float, float, float],
    row_vec: tuple[float, float, float],
    *,
    metric: DistanceMetric,
    cov_inv: list[list[float]] | None = None,
) -> float:
    if metric == "euclidean":
        return euclidean_distance(target_vec, row_vec)
    if metric == "weighted_euclidean":
        return weighted_euclidean_distance(target_vec, row_vec)
    if metric == "mahalanobis":
        return mahalanobis_distance(target_vec, row_vec, cov_inv or [[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    raise ValueError(metric)


def gaussian_kernel(distance: float, bandwidth: float) -> float:
    bw = max(bandwidth, 1e-6)
    return math.exp(-0.5 * (distance / bw) ** 2)


def effective_sample_size(weights: Sequence[float]) -> float:
    w = [max(float(x), 0.0) for x in weights]
    s = sum(w)
    if s <= 0:
        return 0.0
    return (s * s) / sum(x * x for x in w)


def find_neighbors(
    target: MarketPriorRow,
    pool: Sequence[MarketPriorRow],
    *,
    k: int,
    metric: DistanceMetric = "euclidean",
    weight_scheme: WeightScheme = "uniform",
    bandwidth: float = 0.05,
    cov_inv: list[list[float]] | None = None,
) -> list[NeighborMatch]:
    target_vec = (target.prob_fav, target.prob_draw, target.prob_dog)
    scored: list[tuple[float, MarketPriorRow]] = []
    for row in pool:
        vec = (row.prob_fav, row.prob_draw, row.prob_dog)
        dist = compute_distance(target_vec, vec, metric=metric, cov_inv=cov_inv)
        scored.append((dist, row))
    scored.sort(key=lambda x: x[0])
    top = scored[: max(k, 1)]
    if weight_scheme == "gaussian":
        matches = [
            NeighborMatch(row=r, distance=d, weight=gaussian_kernel(d, bandwidth)) for d, r in top
        ]
    else:
        matches = [NeighborMatch(row=r, distance=d, weight=1.0) for d, r in top]
    return matches


def adaptive_kernel_neighbors(
    target: MarketPriorRow,
    pool: Sequence[MarketPriorRow],
    *,
    bandwidth: float = 0.05,
    min_neighbors: int = 25,
    max_neighbors: int = 1000,
    metric: DistanceMetric = "euclidean",
) -> list[NeighborMatch]:
    all_matches = find_neighbors(
        target,
        pool,
        k=len(pool),
        metric=metric,
        weight_scheme="gaussian",
        bandwidth=bandwidth,
    )
    positive = [m for m in all_matches if m.weight > 1e-6]
    if len(positive) < min_neighbors:
        return all_matches[:min_neighbors]
    return positive[:max_neighbors]
