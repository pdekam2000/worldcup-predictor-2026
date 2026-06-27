"""Phase A23 blueprint — goal_timing.range_probabilities schema."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.goal_timing.config import GOAL_TIMING_MINUTE_RANGES

# Public API keys (underscore) ↔ internal EGIE keys (hyphen)
RANGE_PROB_KEYS: tuple[str, ...] = tuple(
    k.replace("-", "_").replace("+", "") for k in GOAL_TIMING_MINUTE_RANGES
)

_INTERNAL_TO_PUBLIC = {
    "0-15": "0_15",
    "16-30": "16_30",
    "31-45+": "31_45",
    "46-60": "46_60",
    "61-75": "61_75",
    "76-90+": "76_90",
}

_PUBLIC_TO_INTERNAL = {v: k for k, v in _INTERNAL_TO_PUBLIC.items()}


def normalize_range_probabilities(raw: dict[str, Any] | None) -> dict[str, float]:
    """Normalize to public underscore keys; values sum to ~1.0."""
    if not raw:
        return {}
    out: dict[str, float] = {}
    for key, value in raw.items():
        try:
            prob = float(value)
        except (TypeError, ValueError):
            continue
        pub = key if key in _PUBLIC_TO_INTERNAL else _INTERNAL_TO_PUBLIC.get(key.replace("_", "-"))
        if pub:
            out[pub] = round(prob, 4)
    total = sum(out.values())
    if total <= 0:
        return {}
    if abs(total - 1.0) > 0.05:
        out = {k: round(v / total, 4) for k, v in out.items()}
    return out


def to_internal_range_probs(public: dict[str, float]) -> dict[str, float]:
    internal: dict[str, float] = {}
    for pub, prob in public.items():
        internal_key = _PUBLIC_TO_INTERNAL.get(pub)
        if internal_key:
            internal[internal_key] = prob
    return internal
