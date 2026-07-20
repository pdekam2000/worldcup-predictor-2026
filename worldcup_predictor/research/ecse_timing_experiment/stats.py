"""Statistical helpers for timing experiment reports."""

from __future__ import annotations

import math
from typing import Any


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if n <= 0:
        return None, None
    p = successes / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = p + z2 / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z2 / (4 * n)) / n)
    lo = (centre - margin) / denom
    hi = (centre + margin) / denom
    return round(max(0.0, lo), 6), round(min(1.0, hi), 6)


def rate_block(successes: int, n: int) -> dict[str, Any]:
    lo, hi = wilson_interval(successes, n)
    return {
        "successes": int(successes),
        "n": int(n),
        "rate": None if n <= 0 else round(successes / n, 6),
        "wilson_lo": lo,
        "wilson_hi": hi,
    }


def mcnemar_exact(b: int, c: int) -> dict[str, Any]:
    """Exact McNemar two-sided p-value for discordant pairs (b, c).

    b = only first method correct, c = only second method correct.
    """
    n = b + c
    if n == 0:
        return {"b": b, "c": c, "n_discordant": 0, "p_value": 1.0, "note": "no_discordant_pairs"}
    # Two-sided exact binomial under p=0.5
    k = min(b, c)
    # P(X<=k) + P(X>=n-k) with X~Bin(n,0.5); for two-sided use 2*cdf but cap at 1
    cdf = sum(math.comb(n, i) for i in range(0, k + 1)) / (2**n)
    p = min(1.0, 2.0 * cdf)
    return {"b": b, "c": c, "n_discordant": n, "p_value": round(p, 6)}


def interpretation_band(n_finished_paired: int) -> str:
    from worldcup_predictor.research.ecse_timing_experiment.constants import INTERPRETATION_BANDS

    for lo, hi, label in INTERPRETATION_BANDS:
        if lo <= n_finished_paired <= hi:
            return label
    return "descriptive_only"
