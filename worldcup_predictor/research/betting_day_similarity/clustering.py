"""Regime clustering — research-only, prematch features only."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.metrics import silhouette_score
from sklearn.mixture import GaussianMixture


def choose_kmeans_k(
    X: np.ndarray,
    candidates: list[int],
    *,
    seed: int = 20260731,
) -> dict[str, Any]:
    scores = []
    best_k = candidates[0]
    best_sil = -1.0
    for k in candidates:
        if k < 2 or k >= len(X):
            continue
        km = KMeans(n_clusters=k, random_state=seed, n_init=10)
        labels = km.fit_predict(X)
        if len(set(labels)) < 2:
            continue
        sil = float(silhouette_score(X, labels))
        scores.append({"k": k, "silhouette": sil})
        if sil > best_sil:
            best_sil = sil
            best_k = k
    return {"best_k": best_k, "best_silhouette": best_sil, "scores": scores}


def fit_regimes(
    X: np.ndarray,
    *,
    method: str = "kmeans",
    n_clusters: int = 4,
    seed: int = 20260731,
) -> dict[str, Any]:
    method = method.lower()
    if method == "hierarchical":
        model = AgglomerativeClustering(n_clusters=n_clusters)
        labels = model.fit_predict(X)
        centroids = np.vstack([X[labels == i].mean(axis=0) for i in range(n_clusters)])
        return {"method": method, "labels": labels.tolist(), "centroids": centroids, "model": None}
    if method == "gmm":
        model = GaussianMixture(n_components=n_clusters, random_state=seed)
        labels = model.fit_predict(X)
        return {
            "method": method,
            "labels": labels.tolist(),
            "centroids": model.means_,
            "model": model,
        }
    model = KMeans(n_clusters=n_clusters, random_state=seed, n_init=10)
    labels = model.fit_predict(X)
    return {
        "method": "kmeans",
        "labels": labels.tolist(),
        "centroids": model.cluster_centers_,
        "model": model,
    }


def predict_regime(x: np.ndarray, centroids: np.ndarray) -> tuple[int, float]:
    dists = [float(np.linalg.norm(x - c)) for c in centroids]
    idx = int(np.argmin(dists))
    # confidence: inverse relative distance
    d0 = dists[idx]
    d1 = sorted(dists)[1] if len(dists) > 1 else d0 + 1.0
    conf = float(d1 / (d0 + d1 + 1e-9))
    return idx, conf


def describe_regime(
    feature_names: list[str],
    centroid: np.ndarray,
    global_mean: np.ndarray,
) -> dict[str, Any]:
    deltas = centroid - global_mean
    order = np.argsort(np.abs(deltas))[::-1][:6]
    drivers = []
    for i in order:
        drivers.append(
            {
                "feature": feature_names[int(i)],
                "centroid": round(float(centroid[int(i)]), 6),
                "delta_vs_mean": round(float(deltas[int(i)]), 6),
            }
        )
    # Human-readable heuristic tags (not hardcoded conclusions)
    tags = []
    name_to_idx = {n: i for i, n in enumerate(feature_names)}
    def g(n: str) -> float:
        return float(centroid[name_to_idx[n]]) if n in name_to_idx else 0.0

    if g("avg_wde_confidence") > float(global_mean[name_to_idx.get("avg_wde_confidence", 0)] if "avg_wde_confidence" in name_to_idx else 0):
        tags.append("elevated_confidence")
    if g("avg_ecse_entropy") > 0.3:  # standardized space often near 0
        tags.append("elevated_entropy")
    if g("league_concentration") > 0.2:
        tags.append("concentrated_leagues")
    if g("n_discovered_fixtures") < -0.2:
        tags.append("sparse_volume")
    if g("n_discovered_fixtures") > 0.2:
        tags.append("dense_volume")
    if g("avg_insurance_gain") > 0.2:
        tags.append("insurance_dependent")
    if g("bookmaker_completeness") < -0.2:
        tags.append("low_market_completeness")
    return {"top_drivers": drivers, "descriptive_tags": tags}
