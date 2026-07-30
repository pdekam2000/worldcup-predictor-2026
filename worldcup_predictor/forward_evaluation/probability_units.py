"""Canonical probability unit contract for freeze / API / evaluation layers.

Internal canonical representation: fractions in [0, 1].
Presentation percentages must be explicitly named (*_pct) or converted once.
"""

from __future__ import annotations

import math
from typing import Any

PROBABILITY_UNIT_FRACTION = "fraction"
PROBABILITY_UNIT_PERCENT = "percent"
FEATURE_SCHEMA_VERSION = "freeze-meta-v3"


class ProbabilityUnitError(ValueError):
    """Raised when a probability value violates the unit contract."""


def is_finite_number(value: Any) -> bool:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(v)


def to_fraction(value: Any, *, field: str = "probability", allow_none: bool = True) -> float | None:
    """Normalize a probability-like value to a fraction in [0, 1].

    Values > 1.0 are treated as percentages (e.g. 45.2 → 0.452).
    """
    if value is None or value == "":
        if allow_none:
            return None
        raise ProbabilityUnitError(f"{field}: missing required probability")
    if not is_finite_number(value):
        raise ProbabilityUnitError(f"{field}: non-finite probability {value!r}")
    v = float(value)
    if v < 0:
        raise ProbabilityUnitError(f"{field}: probability < 0 ({v})")
    if v > 100:
        raise ProbabilityUnitError(f"{field}: percentage > 100 ({v})")
    if v > 1.0:
        v = v / 100.0
    if v > 1.0 + 1e-12:
        raise ProbabilityUnitError(f"{field}: fraction > 1 after normalization ({v})")
    return max(0.0, min(1.0, v))


def to_percent(value: Any, *, field: str = "probability", allow_none: bool = True) -> float | None:
    frac = to_fraction(value, field=field, allow_none=allow_none)
    if frac is None:
        return None
    return round(frac * 100.0, 6)


def assert_fraction(value: Any, *, field: str = "probability") -> float:
    frac = to_fraction(value, field=field, allow_none=False)
    assert frac is not None
    if not (0.0 <= frac <= 1.0):
        raise ProbabilityUnitError(f"{field}: fraction out of range ({frac})")
    return frac


def normalize_score_probability_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return copies with probability coerced to fraction units."""
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        if "probability" in item:
            item["probability"] = to_fraction(item.get("probability"), field="score.probability")
        out.append(item)
    return out


def top_mass(rows: list[dict[str, Any]], n: int) -> float | None:
    probs = []
    for row in rows[:n]:
        p = to_fraction(row.get("probability"), field="mass.probability")
        if p is not None:
            probs.append(p)
    if not probs:
        return None
    return round(sum(probs), 6)


def validate_probability_payload(payload: dict[str, Any]) -> list[str]:
    """Return list of unit-contract violations (empty if OK)."""
    issues: list[str] = []
    for key in ("home_probability", "draw_probability", "away_probability"):
        if key not in payload:
            continue
        try:
            to_fraction(payload.get(key), field=key)
        except ProbabilityUnitError as exc:
            issues.append(str(exc))
    for row in payload.get("rank_rows") or payload.get("top5") or []:
        if not isinstance(row, dict):
            continue
        try:
            to_fraction(row.get("probability"), field="rank.probability")
        except ProbabilityUnitError as exc:
            issues.append(str(exc))
    return issues
