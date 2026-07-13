"""Calibration metrics for ECSE tail forensics."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any


def wilson_ci(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return 0.0, 0.0
    p = hits / n
    denom = 1 + z**2 / n
    centre = p + z**2 / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n)
    return round((centre - margin) / denom, 4), round((centre + margin) / denom, 4)


class CalibrationAccumulator:
    def __init__(self) -> None:
        self.buckets: dict[str, dict[str, float]] = defaultdict(lambda: {"predicted_mass": 0.0, "observed": 0, "n": 0})

    def add(self, bucket: str, predicted_prob: float, observed: bool) -> None:
        self.buckets[bucket]["predicted_mass"] += predicted_prob
        self.buckets[bucket]["n"] += 1
        if observed:
            self.buckets[bucket]["observed"] += 1

    def report(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for bucket, data in sorted(self.buckets.items()):
            n = int(data["n"])
            obs = int(data["observed"])
            pred_rate = data["predicted_mass"] / n if n else 0.0
            obs_rate = obs / n if n else 0.0
            gap = obs_rate - pred_rate
            lo, hi = wilson_ci(obs, n)
            out[bucket] = {
                "sample_count": n,
                "expected_mass": round(pred_rate, 6),
                "observed_frequency": round(obs_rate, 6),
                "calibration_gap": round(gap, 6),
                "confidence_interval_95": [lo, hi],
                "verdict": "overpredicted" if gap < -0.01 else ("underpredicted" if gap > 0.01 else "calibrated"),
            }
        return out


def log_loss(prob_actual: float) -> float:
    return -math.log(max(prob_actual, 1e-12))


def brier_score(prob_actual: float) -> float:
    return (1.0 - prob_actual) ** 2


def entropy(probs: list[float]) -> float:
    s = 0.0
    for p in probs:
        if p > 0:
            s -= p * math.log(p)
    return round(s, 6)
