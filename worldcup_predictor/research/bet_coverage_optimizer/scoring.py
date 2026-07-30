"""Configurable coverage_score for smart market selection."""

from __future__ import annotations

import math
from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.models import ScoringWeights
from worldcup_predictor.research.multi_market_odds_loader import FRESH_OK


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def normalize_batch(values: list[float | None]) -> list[float]:
    nums = [float(v) if v is not None else 0.0 for v in values]
    if not nums:
        return []
    lo, hi = min(nums), max(nums)
    if hi - lo < 1e-12:
        return [0.5 for _ in nums]
    return [(v - lo) / (hi - lo) for v in nums]


def compute_coverage_metrics(
    *,
    target_scores: list[tuple[str, float]],
    covered_scores: list[str],
    exact_scores: list[str],
    odds: float | None,
) -> dict[str, Any]:
    target_map = {str(s): float(p) for s, p in target_scores}
    covered = [s for s in covered_scores if s in target_map]
    exact_set = {str(s) for s in exact_scores}
    exact_overlap = [s for s in covered if s in exact_set]
    non_exact = [s for s in covered if s not in exact_set]
    covered_mass = sum(target_map[s] for s in covered)
    exact_mass = sum(target_map[s] for s in exact_overlap)
    non_exact_mass = sum(target_map[s] for s in non_exact)
    implied = (1.0 / float(odds)) if odds and odds > 1.0 else None
    # Model probability estimated as covered Top-N mass (lower bound, not full market p)
    model_p = covered_mass
    edge = (model_p - implied) if implied is not None else None
    return {
        "covered_scores": covered,
        "covered_top8_count": len(covered),
        "covered_probability_mass": round(covered_mass, 8),
        "exact_overlap_scores": exact_overlap,
        "exact_overlap_count": len(exact_overlap),
        "exact_overlap_probability_mass": round(exact_mass, 8),
        "non_exact_covered_scores": non_exact,
        "non_exact_coverage_count": len(non_exact),
        "non_exact_coverage_probability_mass": round(non_exact_mass, 8),
        "implied_probability": round(implied, 8) if implied is not None else None,
        "estimated_model_probability": round(model_p, 8),
        "estimated_edge": round(edge, 8) if edge is not None else None,
    }


def score_candidates(
    candidates: list[dict[str, Any]],
    *,
    weights: ScoringWeights | None = None,
    require_fresh: bool = True,
) -> list[dict[str, Any]]:
    """
    Attach coverage_score (NOT a probability/confidence) using configurable weights.
    Mutates and returns the same list sorted by coverage_score desc.
    """
    w = weights or ScoringWeights()
    masses = [c.get("covered_probability_mass") for c in candidates]
    non_exact = [c.get("non_exact_coverage_probability_mass") for c in candidates]
    overlaps = [c.get("exact_overlap_probability_mass") for c in candidates]
    edges = [c.get("estimated_edge") if c.get("estimated_edge") is not None else -1.0 for c in candidates]
    log_odds = []
    for c in candidates:
        o = c.get("odds")
        log_odds.append(math.log(float(o)) if o and float(o) > 1.0 else 0.0)

    n_mass = normalize_batch(masses)
    n_non = normalize_batch(non_exact)
    n_ov = normalize_batch(overlaps)
    n_edge = normalize_batch(edges)
    n_log = normalize_batch(log_odds)

    stale_labels = {"STALE_ODDS", "REQUIRES_FRESH_ODDS", "stale", "STALE"}

    for i, c in enumerate(candidates):
        reasons: list[str] = list(c.get("rejection_reasons") or [])
        odds = c.get("odds")
        freshness = str(c.get("odds_freshness_status") or "")
        eligible = bool(c.get("eligible", True))

        if odds is None:
            eligible = False
            reasons.append("MISSING_ODDS")
        elif float(odds) < float(w.min_odds):
            eligible = False
            reasons.append(f"ODDS_BELOW_MIN:{w.min_odds}")

        if freshness in stale_labels:
            eligible = False
            reasons.append("STALE_ODDS")
        elif require_fresh and freshness not in FRESH_OK:
            eligible = False
            reasons.append("STALE_OR_UNKNOWN_ODDS")

        if c.get("unsupported_semantics"):
            eligible = False
            reasons.append("UNSUPPORTED_MARKET_SEMANTICS")

        if c.get("incomplete_mapping"):
            eligible = False
            reasons.append("INCOMPLETE_SETTLEMENT_MAPPING")

        covered_mass = float(c.get("covered_probability_mass") or 0.0)
        non_exact_mass = float(c.get("non_exact_coverage_probability_mass") or 0.0)
        if covered_mass <= 0:
            eligible = False
            reasons.append("ZERO_TOPN_COVERAGE")
        if non_exact_mass <= 0 and float(c.get("exact_overlap_probability_mass") or 0.0) > 0:
            # Pure duplication of exact legs — still allow but penalize
            reasons.append("REDUNDANT_EXACT_ONLY_COVERAGE")

        base = (
            w.covered_mass * n_mass[i]
            + w.non_exact_mass * n_non[i]
            + w.exact_overlap_mass * n_ov[i]
            + w.estimated_edge * n_edge[i]
            + w.log_odds * n_log[i]
        )
        penalty = 0.0
        if "REDUNDANT_EXACT_ONLY_COVERAGE" in reasons:
            penalty += w.redundant_penalty
        if covered_mass < w.narrow_mass_threshold:
            penalty += w.narrow_mass_penalty
            reasons.append("EXCESSIVELY_NARROW_MASS")
        if freshness in stale_labels:
            penalty += w.stale_penalty

        coverage_score = round(max(0.0, base - penalty), 8) if eligible else None
        c["coverage_score"] = coverage_score
        c["eligible"] = eligible
        c["rejection_reasons"] = sorted(set(reasons))
        c["score_components"] = {
            "normalized_covered_probability_mass": round(n_mass[i], 8),
            "normalized_non_exact_coverage_probability_mass": round(n_non[i], 8),
            "normalized_exact_overlap_probability_mass": round(n_ov[i], 8),
            "normalized_estimated_edge": round(n_edge[i], 8),
            "normalized_log_odds": round(n_log[i], 8),
            "penalty": round(penalty, 8),
            "note": "coverage_score is a ranking utility, not a probability or confidence",
        }

    candidates.sort(
        key=lambda c: (
            0 if c.get("eligible") else 1,
            -(c.get("coverage_score") if c.get("coverage_score") is not None else -1.0),
            -(c.get("covered_probability_mass") or 0.0),
            str(c.get("market_key") or ""),
        )
    )
    return candidates
