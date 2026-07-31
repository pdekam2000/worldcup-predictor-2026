"""Out-of-distribution detection — research-only."""

from __future__ import annotations

from typing import Any

import numpy as np


def ood_status(
    x: np.ndarray,
    *,
    nn_distance: float,
    nn_p95: float,
    centroid_distance: float,
    centroid_p95: float,
    train_min: np.ndarray,
    train_max: np.ndarray,
    missing_ratio: float,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    range_violations = int(np.sum((x < train_min) | (x > train_max)))
    strong = False
    mild = False
    reasons = []
    if nn_distance > float(cfg.get("ood_nn_distance_p95_multiplier", 1.25)) * max(nn_p95, 1e-6):
        strong = True
        reasons.append("nn_distance_above_p95")
    if centroid_distance > float(cfg.get("ood_centroid_distance_p95_multiplier", 1.35)) * max(
        centroid_p95, 1e-6
    ):
        mild = True
        reasons.append("centroid_distance_above_p95")
    if range_violations >= int(cfg.get("ood_range_violation_strong", 5)):
        strong = True
        reasons.append("feature_range_violations_strong")
    elif range_violations >= int(cfg.get("ood_range_violation_mild", 2)):
        mild = True
        reasons.append("feature_range_violations_mild")
    if missing_ratio >= float(cfg.get("ood_missing_ratio_strong", 0.35)):
        strong = True
        reasons.append("missing_feature_ratio_strong")
    elif missing_ratio >= float(cfg.get("ood_missing_ratio_mild", 0.15)):
        mild = True
        reasons.append("missing_feature_ratio_mild")

    if strong:
        level = "strongly_out_of_distribution"
    elif mild:
        level = "mildly_out_of_distribution"
    else:
        level = "in_distribution"
    return {
        "ood_level": level,
        "in_distribution": level == "in_distribution",
        "nn_distance": round(nn_distance, 8),
        "centroid_distance": round(centroid_distance, 8),
        "range_violations": range_violations,
        "missing_ratio": round(missing_ratio, 8),
        "reasons": reasons,
    }
