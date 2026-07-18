"""Temperature / Platt calibration for 1X2 (fit on validation only)."""

from __future__ import annotations

import math
from typing import Any


def _softmax(logits: list[float], T: float) -> list[float]:
    scaled = [x / max(1e-6, T) for x in logits]
    m = max(scaled)
    exps = [math.exp(x - m) for x in scaled]
    z = sum(exps) or 1.0
    return [e / z for e in exps]


def _probs_to_logits(hda: dict[str, float], eps: float = 1e-6) -> list[float]:
    labs = ("home", "draw", "away")
    ps = [max(eps, float(hda.get(l, eps))) for l in labs]
    z = sum(ps)
    ps = [p / z for p in ps]
    return [math.log(p) for p in ps]


def fit_temperature(val_rows: list[dict], val_preds: list[dict], *, grid: list[float] | None = None) -> float:
    from worldcup_predictor.challenger.backtest.metrics import multiclass_logloss

    grid = grid or [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0]
    y = [r["actual_1x2"] for r in val_rows]
    best_t, best_ll = 1.0, 1e9
    for t in grid:
        probs = []
        for p in val_preds:
            logits = _probs_to_logits(p["hda"])
            soft = _softmax(logits, t)
            probs.append({"home": soft[0], "draw": soft[1], "away": soft[2]})
        ll = multiclass_logloss(y, probs) or 1e9
        if ll < best_ll:
            best_ll = ll
            best_t = t
    return best_t


def apply_temperature(pred: dict[str, Any], temperature: float) -> dict[str, Any]:
    out = dict(pred)
    logits = _probs_to_logits(pred["hda"])
    soft = _softmax(logits, temperature)
    hda = {"home": round(soft[0], 4), "draw": round(soft[1], 4), "away": round(soft[2], 4)}
    out["hda"] = hda
    out["decision_1x2"] = max(hda.items(), key=lambda kv: kv[1])[0]
    out["calibration"] = {"method": "temperature", "T": temperature}
    return out


def fit_platt_binary(y: list[int], p: list[float]) -> tuple[float, float]:
    """Simple 1D Platt on logit(p) via grid search (no sklearn dependency)."""
    eps = 1e-6
    best = (1.0, 0.0)
    best_ll = 1e9
    for a in [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]:
        for b in [-1.0, -0.5, 0.0, 0.5, 1.0]:
            ll = 0.0
            for yi, pi in zip(y, p):
                pi = min(1 - eps, max(eps, float(pi)))
                z = a * math.log(pi / (1 - pi)) + b
                q = 1.0 / (1.0 + math.exp(-z))
                q = min(1 - eps, max(eps, q))
                ll += -(yi * math.log(q) + (1 - yi) * math.log(1 - q))
            ll /= max(1, len(y))
            if ll < best_ll:
                best_ll = ll
                best = (a, b)
    return best


def apply_platt(p: float, a: float, b: float) -> float:
    eps = 1e-6
    pi = min(1 - eps, max(eps, float(p)))
    z = a * math.log(pi / (1 - pi)) + b
    return 1.0 / (1.0 + math.exp(-z))
