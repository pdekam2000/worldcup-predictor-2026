"""Competition segment hierarchy and fallback rules."""

from __future__ import annotations

from typing import Sequence

from worldcup_predictor.research.ecse_market_prior.types import MarketPriorRow

def segment_hierarchy(target: MarketPriorRow) -> list[tuple[str, str | None]]:
    """Return ordered (segment_kind, key) filters from strictest to global."""
    out: list[tuple[str, str | None]] = [("exact_competition", target.league)]
    seg = target.segment
    if seg == "national_teams":
        out.append(("national_teams", None))
    elif seg == "uefa_club":
        out.append(("uefa_club", None))
    elif seg == "domestic_leagues":
        out.append(("domestic_leagues", None))
    elif seg == "world_cup_major":
        out.append(("world_cup_major", None))
    out.append(("global", None))
    return out


def filter_pool_by_segment(
    pool: Sequence[MarketPriorRow],
    target: MarketPriorRow,
    *,
    min_n: int,
) -> tuple[list[MarketPriorRow], str, bool]:
    """Return filtered pool, segment label used, and whether fallback was required."""
    for kind, key in segment_hierarchy(target):
        if kind == "exact_competition":
            filtered = [r for r in pool if r.league == key]
            label = f"exact:{key}"
        elif kind == "global":
            filtered = list(pool)
            label = "global"
        else:
            filtered = [r for r in pool if r.segment == kind]
            label = kind
        if len(filtered) >= min_n:
            return filtered, label, kind != segment_hierarchy(target)[0][0]
    return list(pool), "global_forced", True


def segment_confidence_penalty(segment_used: str, fallback: bool, n_neighbors: int, min_n: int) -> float:
    if not fallback and segment_used.startswith("exact:"):
        return 1.0
    if segment_used == "national_teams":
        return 0.95
    if segment_used == "domestic_leagues":
        return 0.85 if n_neighbors >= min_n else 0.65
    if n_neighbors < min_n:
        return 0.5
    return 0.75
