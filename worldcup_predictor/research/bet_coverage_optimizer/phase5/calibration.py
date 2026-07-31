"""Confidence / entropy / residual-risk calibration (research-only)."""

from __future__ import annotations

from typing import Any


def _hit(scores: list[str], actual: str) -> bool:
    a = str(actual).replace(" ", "")
    return a in {str(s).replace(" ", "") for s in scores}


def _quantile_bins(values: list[float], n_bins: int = 5) -> list[tuple[float, float]]:
    if not values:
        return []
    xs = sorted(values)
    edges = []
    for i in range(n_bins):
        lo = xs[int(i * len(xs) / n_bins)]
        hi = xs[min(len(xs) - 1, int((i + 1) * len(xs) / n_bins) - 1)]
        if i == n_bins - 1:
            hi = xs[-1]
        edges.append((lo, hi))
    return edges


def _assign(v: float, edges: list[tuple[float, float]]) -> int:
    for i, (lo, hi) in enumerate(edges):
        if i == len(edges) - 1:
            if lo <= v <= hi:
                return i
        elif lo <= v <= hi:
            return i
    return len(edges) - 1


def run_calibration_report(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    conf = [float(f.get("confidence") or 0.0) for f in fixtures]
    ent = [float(f.get("entropy") or 0.0) for f in fixtures]
    cov = [float(f.get("coverage_ratio_primary") or 0.0) for f in fixtures]
    res = [float(f.get("residual_mass") or 0.0) for f in fixtures]

    dimensions = {
        "model_confidence": (conf, _quantile_bins(conf)),
        "entropy": (ent, _quantile_bins(ent)),
        "coverage_mass": (cov, _quantile_bins(cov)),
        "residual_risk": (res, _quantile_bins(res)),
    }

    diagrams = {}
    for name, (vals, edges) in dimensions.items():
        bins = [
            {"bin": i, "lo": edges[i][0], "hi": edges[i][1], "n": 0, "hit_rate": 0.0, "hits": 0}
            for i in range(len(edges))
        ]
        for fx, v in zip(fixtures, vals):
            if not edges:
                continue
            bi = _assign(v, edges)
            exact3 = list(fx.get("exact3") or [])
            main = exact3 + list(fx.get("main_coverage_scores") or [])
            ins = main + list(fx.get("insurance_scores") or [])
            bins[bi]["n"] += 1
            if _hit(ins, fx["actual_score"]):
                bins[bi]["hits"] += 1
        for b in bins:
            b["hit_rate"] = round(b["hits"] / b["n"], 8) if b["n"] else None
        # Monotonicity check: higher confidence / coverage should improve hit rate
        rates = [b["hit_rate"] for b in bins if b["hit_rate"] is not None]
        improving = None
        if len(rates) >= 2:
            if name in {"model_confidence", "coverage_mass"}:
                improving = rates[-1] >= rates[0]
            elif name in {"entropy", "residual_risk"}:
                improving = rates[-1] <= rates[0]
        diagrams[name] = {
            "bins": bins,
            "higher_is_better_aligned": improving,
        }

    return {
        "research_only": True,
        "reliability_diagrams": diagrams,
        "higher_confidence_better": diagrams.get("model_confidence", {}).get("higher_is_better_aligned"),
        "note": "Reliability diagrams use quantile bins of frozen/replay features vs Main+Insurance hit.",
    }
