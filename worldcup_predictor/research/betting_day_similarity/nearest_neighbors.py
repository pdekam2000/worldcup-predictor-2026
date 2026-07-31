"""Nearest-neighbor day analogs — research-only."""

from __future__ import annotations

from typing import Any

import numpy as np

from worldcup_predictor.research.betting_day_similarity.distance_metrics import (
    cosine_distance,
    euclidean,
    mahalanobis,
    manhattan,
    mixed_distance,
)


def knn_indices(
    query: np.ndarray,
    library: np.ndarray,
    *,
    k: int = 10,
    method: str = "mixed",
    inv_cov: np.ndarray | None = None,
    weights: np.ndarray | None = None,
) -> list[tuple[int, float]]:
    dists = []
    for i in range(library.shape[0]):
        if method == "manhattan":
            d = manhattan(query, library[i])
        elif method == "cosine":
            d = cosine_distance(query, library[i])
        elif method == "mahalanobis":
            d = mahalanobis(query, library[i], inv_cov)
        elif method == "mixed":
            d = mixed_distance(query, library[i], weights=weights)
        else:
            d = euclidean(query, library[i])
        dists.append((i, float(d)))
    dists.sort(key=lambda x: (x[1], x[0]))
    return dists[: max(1, k)]


def format_analogs(
    neighbor_pairs: list[tuple[int, float]],
    library_days: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    out = []
    for idx, dist in neighbor_pairs:
        d = library_days[idx]
        labels = d.get("labels") or {}
        out.append(
            {
                "analog_day_id": d.get("day_id"),
                "vienna_date": d.get("vienna_date"),
                "distance": round(dist, 8),
                "similarity_score": round(1.0 / (1.0 + dist), 8),
                "baseline_action": d.get("baseline_action"),
                "calibrated_action": d.get("calibrated_action"),
                "historical_roi_evaluation_only": labels.get("realized_roi"),
                "coupon_survival": labels.get("coupon_survival"),
                "insurance_rescue_count": labels.get("insurance_rescue_count"),
                "complete_coupon_failure": labels.get("complete_coupon_failure"),
                "shared_characteristics": _shared(d.get("features") or {}, None),
            }
        )
    return out


def _shared(a: dict[str, Any], b: dict[str, Any] | None) -> list[str]:
    # Placeholder shared tags from feature magnitude
    tags = []
    if float(a.get("league_concentration") or 0) > 0.5:
        tags.append("high_league_concentration")
    if float(a.get("avg_ecse_entropy") or 0) > 2.5:
        tags.append("high_entropy")
    if float(a.get("avg_wde_confidence") or 0) > 0.65:
        tags.append("high_confidence")
    if float(a.get("n_discovered_fixtures") or 0) <= 2:
        tags.append("sparse_slate")
    if float(a.get("n_discovered_fixtures") or 0) >= 5:
        tags.append("dense_slate")
    return tags
