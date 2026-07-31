"""Feature stability and distribution drift — research-only forensic."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy import stats


def _col(X: np.ndarray, j: int) -> np.ndarray:
    v = X[:, j]
    return v[~np.isnan(v)]


def feature_stability_stats(
    train: np.ndarray,
    val: np.ndarray,
    hold: np.ndarray,
    feature_names: list[str],
) -> dict[str, Any]:
    rows = []
    for j, name in enumerate(feature_names):
        splits = {
            "train": _col(train, j),
            "validation": _col(val, j),
            "holdout": _col(hold, j),
        }
        split_stats = {}
        for sk, arr in splits.items():
            if len(arr) == 0:
                split_stats[sk] = {
                    "mean": None,
                    "median": None,
                    "variance": None,
                    "cv": None,
                    "missing_rate": 1.0,
                    "entropy": None,
                }
                continue
            mean = float(np.mean(arr))
            var = float(np.var(arr))
            std = float(np.std(arr))
            cv = float(std / abs(mean)) if abs(mean) > 1e-12 else float(std)
            # discrete entropy via histogram
            hist, _ = np.histogram(arr, bins=min(20, max(5, len(arr) // 5)))
            p = hist / max(1, hist.sum())
            p = p[p > 0]
            ent = float(-np.sum(p * np.log(p + 1e-12)))
            missing_rate = float(
                np.mean(
                    np.isnan(
                        np.concatenate(
                            [train[:, j], val[:, j], hold[:, j]]
                        )
                    )
                )
            )
            split_stats[sk] = {
                "mean": round(mean, 8),
                "median": round(float(np.median(arr)), 8),
                "variance": round(var, 8),
                "cv": round(cv, 8),
                "missing_rate": round(missing_rate, 8),
                "entropy": round(ent, 8),
            }
        # rolling variance proxy: variance of means across chronological thirds of train+val+hold
        all_v = np.concatenate([splits["train"], splits["validation"], splits["holdout"]])
        if len(all_v) >= 9:
            thirds = np.array_split(all_v, 3)
            rolling_var = float(np.var([np.mean(t) for t in thirds if len(t)]))
            seasonal_var = float(np.var([np.var(t) for t in thirds if len(t) > 1] or [0.0]))
        else:
            rolling_var = split_stats["train"].get("variance") or 0.0
            seasonal_var = rolling_var

        means = [split_stats[s]["mean"] for s in ("train", "validation", "holdout") if split_stats[s]["mean"] is not None]
        vars_ = [split_stats[s]["variance"] for s in ("train", "validation", "holdout") if split_stats[s]["variance"] is not None]
        drift_score = float(np.std(means) / (abs(np.mean(means)) + 1e-9)) if means else 0.0
        instability = float(
            0.35 * drift_score
            + 0.25 * (np.std(vars_) / (abs(np.mean(vars_)) + 1e-9) if vars_ else 0.0)
            + 0.20 * float(rolling_var)
            + 0.20 * float(split_stats["holdout"].get("cv") or 0.0)
        )
        rows.append(
            {
                "feature": name,
                "splits": split_stats,
                "rolling_variance": round(float(rolling_var), 8),
                "seasonal_variance": round(float(seasonal_var), 8),
                "drift_score": round(drift_score, 8),
                "instability_score": round(instability, 8),
            }
        )
    rows.sort(key=lambda r: -float(r["instability_score"]))
    return {
        "research_only": True,
        "n_features": len(feature_names),
        "ranked_by_instability": rows,
        "top_unstable": [r["feature"] for r in rows[:15]],
    }


def _psi(a: np.ndarray, b: np.ndarray, bins: int = 10) -> float:
    if len(a) < 5 or len(b) < 5:
        return 0.0
    qs = np.linspace(0, 100, bins + 1)
    edges = np.unique(np.percentile(a, qs))
    if len(edges) < 3:
        return 0.0
    ha, _ = np.histogram(a, bins=edges)
    hb, _ = np.histogram(b, bins=edges)
    pa = ha / max(1, ha.sum()) + 1e-6
    pb = hb / max(1, hb.sum()) + 1e-6
    return float(np.sum((pb - pa) * np.log(pb / pa)))


def _kl(a: np.ndarray, b: np.ndarray, bins: int = 10) -> float:
    if len(a) < 5 or len(b) < 5:
        return 0.0
    edges = np.unique(np.percentile(np.concatenate([a, b]), np.linspace(0, 100, bins + 1)))
    if len(edges) < 3:
        return 0.0
    ha, _ = np.histogram(a, bins=edges)
    hb, _ = np.histogram(b, bins=edges)
    pa = ha / max(1, ha.sum()) + 1e-6
    pb = hb / max(1, hb.sum()) + 1e-6
    return float(np.sum(pa * np.log(pa / pb)))


def _js(a: np.ndarray, b: np.ndarray, bins: int = 10) -> float:
    return 0.5 * _kl(a, b, bins) + 0.5 * _kl(b, a, bins)


def _ks(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 5 or len(b) < 5:
        return 0.0
    return float(stats.ks_2samp(a, b).statistic)


def _emd(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 5 or len(b) < 5:
        return 0.0
    return float(stats.wasserstein_distance(a, b))


def distribution_drift_report(
    train: np.ndarray,
    val: np.ndarray,
    hold: np.ndarray,
    feature_names: list[str],
) -> dict[str, Any]:
    rows = []
    for j, name in enumerate(feature_names):
        a = _col(train, j)
        b = _col(val, j)
        c = _col(hold, j)
        pair = {
            "feature": name,
            "train_vs_validation": {
                "psi": round(_psi(a, b), 8),
                "kl": round(_kl(a, b), 8),
                "js": round(_js(a, b), 8),
                "ks": round(_ks(a, b), 8),
                "emd": round(_emd(a, b), 8),
            },
            "train_vs_holdout": {
                "psi": round(_psi(a, c), 8),
                "kl": round(_kl(a, c), 8),
                "js": round(_js(a, c), 8),
                "ks": round(_ks(a, c), 8),
                "emd": round(_emd(a, c), 8),
            },
            "validation_vs_holdout": {
                "psi": round(_psi(b, c), 8),
                "kl": round(_kl(b, c), 8),
                "js": round(_js(b, c), 8),
                "ks": round(_ks(b, c), 8),
                "emd": round(_emd(b, c), 8),
            },
        }
        pair["drift_rank_score"] = round(
            float(pair["train_vs_holdout"]["psi"])
            + float(pair["train_vs_holdout"]["ks"])
            + 0.1 * float(pair["train_vs_holdout"]["emd"]),
            8,
        )
        rows.append(pair)
    rows.sort(key=lambda r: -float(r["drift_rank_score"]))
    return {
        "research_only": True,
        "ranked_by_train_holdout_drift": rows,
        "top_drifted": [r["feature"] for r in rows[:15]],
    }
