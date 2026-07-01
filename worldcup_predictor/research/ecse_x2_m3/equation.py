"""PHASE ECSE-X2-M3 — log_home_prob_phi equation."""

from __future__ import annotations

import math
from typing import Any

from worldcup_predictor.research.ecse_x2_m3.constants import EQUATION_NAME, LOG_PHI


def compute_log_home_prob_phi(probs: dict[str, float | None]) -> float | None:
    home = probs.get("ft_home")
    if home is None or home <= 0 or not math.isfinite(home):
        return None
    val = math.log(home) / LOG_PHI
    if not math.isfinite(val):
        return None
    return float(val)


def equation_payload(probs: dict[str, float | None]) -> dict[str, Any]:
    val = compute_log_home_prob_phi(probs)
    return {
        "equation_name": EQUATION_NAME,
        "equation_value": round(val, 8) if val is not None else None,
        "eligible": val is not None,
    }
