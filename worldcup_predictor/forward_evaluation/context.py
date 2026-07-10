"""Phase 7B Part K — Analysis dimension bucketing."""

from __future__ import annotations

import math
from typing import Any


def _bucket(value: float | None, cuts: list[tuple[float, str]], default: str = "unknown") -> str:
    if value is None:
        return default
    for cut, label in cuts:
        if value <= cut:
            return label
    return cuts[-1][1] if cuts else default


def entropy_from_scores(scores: list[dict[str, Any]]) -> float | None:
    probs = []
    for row in scores:
        p = row.get("probability")
        if p is None:
            continue
        try:
            pv = float(p)
        except (TypeError, ValueError):
            continue
        if pv > 1:
            pv /= 100.0
        if pv > 0:
            probs.append(pv)
    if not probs:
        return None
    total = sum(probs)
    if total <= 0:
        return None
    ent = 0.0
    for p in probs:
        pn = p / total
        ent -= pn * math.log(pn + 1e-15)
    return round(ent, 6)


def mass_from_scores(scores: list[dict[str, Any]], n: int) -> float | None:
    if not scores:
        return None
    total = 0.0
    for row in scores[:n]:
        p = row.get("probability")
        if p is None:
            continue
        try:
            pv = float(p)
        except (TypeError, ValueError):
            continue
        total += pv / 100.0 if pv > 1 else pv
    return round(total, 6) if total > 0 else None


def odds_regime(home: float | None, draw: float | None, away: float | None) -> str:
    if home is None or away is None:
        return "unknown"
    try:
        h, a = float(home), float(away)
    except (TypeError, ValueError):
        return "unknown"
    if h < 1.8 and a >= 3.0:
        return "home_favorite"
    if a < 1.8 and h >= 3.0:
        return "away_favorite"
    if 2.0 <= h <= 3.5 and 2.0 <= a <= 3.5:
        return "balanced"
    return "mixed"


def favorite_class(home: float | None, away: float | None) -> str:
    if home is None or away is None:
        return "unknown"
    try:
        h, a = float(home), float(away)
    except (TypeError, ValueError):
        return "unknown"
    if h < a:
        return "home_favorite"
    if a < h:
        return "away_favorite"
    return "balanced"


def lambda_bucket(total_lambda: float | None) -> str:
    return _bucket(
        total_lambda,
        [(2.2, "low"), (2.8, "medium"), (999.0, "high")],
        default="unknown",
    )


def entropy_bucket(entropy: float | None) -> str:
    return _bucket(entropy, [(2.0, "low"), (2.8, "medium"), (999.0, "high")], default="unknown")


def mass_bucket(mass: float | None) -> str:
    if mass is None:
        return "unknown"
    pct = mass * 100 if mass <= 1 else mass
    return _bucket(pct, [(25.0, "low"), (40.0, "medium"), (999.0, "high")])


def conflict_class(wde_decision: str | None, ft_marginal: str | None, ecse_top1_side: str | None) -> str:
    parts = []
    if wde_decision and ft_marginal and wde_decision != ft_marginal:
        parts.append("wde_ft_mismatch")
    if wde_decision and ecse_top1_side and wde_decision != ecse_top1_side:
        parts.append("wde_ecse_mismatch")
    if ft_marginal and ecse_top1_side and ft_marginal != ecse_top1_side:
        parts.append("ft_ecse_mismatch")
    return "|".join(parts) if parts else "aligned"


def market_agreement_class(wde_decision: str | None, market_favorite: str | None) -> str:
    if not wde_decision or not market_favorite or market_favorite == "unknown":
        return "unknown"
    if wde_decision.replace("_win", "") == market_favorite.replace("_favorite", ""):
        return "agree"
    if market_favorite == "balanced":
        return "balanced_market"
    return "conflict"


def scoreline_side(score: str | None) -> str | None:
    if not score or "-" not in str(score):
        return None
    try:
        h, a = [int(x) for x in str(score).split("-", 1)]
    except ValueError:
        return None
    if h > a:
        return "home_win"
    if a > h:
        return "away_win"
    return "draw"


def build_prediction_context(frozen: dict[str, Any]) -> dict[str, Any]:
    return {
        "prediction_id": frozen.get("prediction_id"),
        "competition": frozen.get("competition"),
        "tier": frozen.get("tier"),
        "odds_regime": odds_regime(
            frozen.get("odds_home"), frozen.get("odds_draw"), frozen.get("odds_away")
        ),
        "entropy_bucket": entropy_bucket(frozen.get("entropy")),
        "top3_mass_bucket": mass_bucket(frozen.get("top3_mass")),
        "top5_mass_bucket": mass_bucket(frozen.get("top5_mass")),
        "conflict_class": conflict_class(
            frozen.get("wde_decision"),
            frozen.get("ft_marginal_direction"),
            scoreline_side(frozen.get("rank_1_score")),
        ),
        "market_agreement_class": market_agreement_class(
            frozen.get("wde_decision"),
            favorite_class(frozen.get("odds_home"), frozen.get("odds_away")),
        ),
        "data_quality_class": str(frozen.get("data_quality") or "unknown").lower(),
        "freshness_class": str(frozen.get("odds_freshness") or "unknown").lower(),
        "bookmaker_count_bucket": _bucket(
            float(frozen["bookmaker_count"]) if frozen.get("bookmaker_count") is not None else None,
            [(3.0, "low"), (8.0, "medium"), (999.0, "high")],
        ),
        "lambda_bucket": lambda_bucket(frozen.get("total_lambda")),
        "favorite_class": favorite_class(frozen.get("odds_home"), frozen.get("odds_away")),
    }
