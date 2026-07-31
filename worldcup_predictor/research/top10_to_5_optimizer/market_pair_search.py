"""Exhaustive two-market set-cover search over real markets."""

from __future__ import annotations

import itertools
from typing import Any

from worldcup_predictor.research.top10_to_5_optimizer.market_semantics import covered_scores_for_market
from worldcup_predictor.research.top10_to_5_optimizer.models import MarketCandidate
from worldcup_predictor.research.top10_to_5_optimizer.pair_scoring import score_market_pair
from worldcup_predictor.research.top10_to_5_optimizer.scenario_engine import evaluate_top10_scenarios
from worldcup_predictor.research.top10_to_5_optimizer.stake_optimizer import allocate_stakes


def _prob_map(top10: list[dict[str, Any]]) -> dict[str, float]:
    return {str(r.get("scoreline") or r.get("score")).replace(" ", ""): float(r.get("probability") or 0.0) for r in top10}


def _direction_set(scores: list[str]) -> set[str]:
    out = set()
    for sc in scores:
        parts = sc.split("-")
        if len(parts) != 2:
            continue
        try:
            h, a = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        out.add("home" if h > a else ("away" if a > h else "draw"))
    return out


def analyze_pair(
    m1: MarketCandidate,
    m2: MarketCandidate,
    *,
    top10: list[dict[str, Any]],
    exact_scores: list[str],
    stakes: dict[str, float],
    exact_odds: dict[str, float | None],
    weights: dict[str, float] | None,
) -> dict[str, Any]:
    scores = [str(r.get("scoreline") or r.get("score")).replace(" ", "") for r in top10]
    pmap = _prob_map(top10)
    c1 = covered_scores_for_market(m1.market_type, m1.market_parameters, scores) or []
    c2 = covered_scores_for_market(m2.market_type, m2.market_parameters, scores) or []
    union = sorted(set(c1) | set(c2))
    uncovered = [s for s in scores if s not in set(union) and s not in set(exact_scores)]
    covered_mass = sum(pmap.get(s, 0.0) for s in union)
    uncovered_mass = sum(pmap.get(s, 0.0) for s in uncovered)
    exact_set = set(exact_scores)
    overlap_exact = {
        "exact_1": exact_scores[0] in set(union) if len(exact_scores) > 0 else False,
        "exact_2": exact_scores[1] in set(union) if len(exact_scores) > 1 else False,
        "exact_3": exact_scores[2] in set(union) if len(exact_scores) > 2 else False,
    }
    overlap_markets = sorted(set(c1) & set(c2))
    incr1 = sorted(set(c1) - exact_set)
    incr2 = sorted(set(c2) - exact_set - set(c1))
    incr_mass = sum(pmap.get(s, 0.0) for s in sorted(set(incr1) | set(incr2)))
    duplicate_only = sorted(set(overlap_markets) & exact_set)

    scenarios = evaluate_top10_scenarios(
        top10,
        exact_scores=exact_scores,
        market1=m1,
        market2=m2,
        stakes=stakes,
        exact_odds=exact_odds,
    )

    implied1 = (1.0 / float(m1.decimal_odds)) if m1.decimal_odds and m1.decimal_odds > 1 else None
    implied2 = (1.0 / float(m2.decimal_odds)) if m2.decimal_odds and m2.decimal_odds > 1 else None
    mod1 = float(m1.modeled_probability) if m1.modeled_probability is not None else (covered_mass / 2.0)
    mod2 = float(m2.modeled_probability) if m2.modeled_probability is not None else (covered_mass / 2.0)
    edge1 = (mod1 - implied1) if implied1 is not None else None
    edge2 = (mod2 - implied2) if implied2 is not None else None
    est_edge = None
    if edge1 is not None and edge2 is not None:
        est_edge = (edge1 + edge2) / 2.0
    elif edge1 is not None:
        est_edge = edge1
    elif edge2 is not None:
        est_edge = edge2

    redundancy = len(overlap_markets) / max(1, len(union))
    dirs = _direction_set(union)
    features = {
        "covered_top10_probability_mass": covered_mass,
        "profitable_top10_mass": scenarios.get("profitable_outcome_coverage_mass") or 0.0,
        "incremental_uncovered_mass": incr_mass,
        "modeled_expected_return": scenarios.get("expected_net") or 0.0,
        "estimated_edge": est_edge or 0.0,
        "worst_case_top10_loss": scenarios.get("worst_top10_loss") or 0.0,
        "market_redundancy": redundancy,
        "concentration": max(float(stakes.get("market_1") or 0), float(stakes.get("market_2") or 0))
        / max(1e-9, sum(stakes.values())),
        "total_stake": sum(stakes.values()),
    }
    scored = score_market_pair(features, weights)

    return {
        "market_1": m1.to_dict(),
        "market_2": m2.to_dict(),
        "union_covered_scorelines": union,
        "covered_top10_count": len(union),
        "covered_top10_probability_mass": round(covered_mass, 8),
        "uncovered_top10_scorelines": uncovered,
        "uncovered_top10_probability_mass": round(uncovered_mass, 8),
        "overlap_with_exact": overlap_exact,
        "overlap_between_coverage_markets": overlap_markets,
        "incremental_coverage_market_1": incr1,
        "incremental_coverage_market_2": incr2,
        "duplicate_only_coverage": duplicate_only,
        "direction_diversity": sorted(dirs),
        "goal_profile_diversity": sorted({sum(map(int, s.split("-"))) for s in union if "-" in s}),
        "bookmaker_odds": [m1.decimal_odds, m2.decimal_odds],
        "modeled_market_probability": [mod1, mod2],
        "implied_probability": [implied1, implied2],
        "estimated_edge": est_edge,
        "freshness_status": [m1.freshness, m2.freshness],
        "scenarios": scenarios,
        "pair_score": scored["pair_score"],
        "pair_score_is_probability": False,
        "pair_score_detail": scored,
        "features": features,
    }


def search_market_pairs(
    markets: list[MarketCandidate],
    *,
    top10: list[dict[str, Any]],
    exact_scores: list[str],
    stake_plan: dict[str, Any],
    exact_odds: dict[str, float | None] | None = None,
    weights: dict[str, float] | None = None,
    max_candidates: int = 5000,
) -> dict[str, Any]:
    """Search actual pair space (all unordered pairs)."""
    eligible = [m for m in markets if m.decimal_odds is not None and float(m.decimal_odds) > 1.0]
    stakes = dict(stake_plan.get("stakes") or {})
    exact_odds = exact_odds or {}
    results: list[dict[str, Any]] = []
    n = 0
    for a, b in itertools.combinations(eligible, 2):
        if a.market_key and b.market_key and a.market_key == b.market_key:
            continue
        # Skip pairs that cannot settle any Top10 score
        scores = [str(r.get("scoreline") or r.get("score")).replace(" ", "") for r in top10]
        if covered_scores_for_market(a.market_type, a.market_parameters, scores) is None:
            continue
        if covered_scores_for_market(b.market_type, b.market_parameters, scores) is None:
            continue
        row = analyze_pair(
            a,
            b,
            top10=top10,
            exact_scores=exact_scores,
            stakes=stakes,
            exact_odds=exact_odds,
            weights=weights,
        )
        results.append(row)
        n += 1
        if n >= max_candidates:
            break

    results.sort(
        key=lambda r: (
            -float(r.get("pair_score") or 0),
            -float(r.get("scenarios", {}).get("profitable_outcome_coverage_mass") or 0),
            -float(r.get("covered_top10_probability_mass") or 0),
            str(r["market_1"].get("market_key")),
            str(r["market_2"].get("market_key")),
        )
    )
    selected = results[0] if results else None
    rejected = []
    if selected and len(results) > 1:
        for r in results[1:]:
            rejected.append(
                {
                    "market_1": r["market_1"].get("label"),
                    "market_2": r["market_2"].get("label"),
                    "pair_score": r.get("pair_score"),
                    "reason_lost": _reject_reason(selected, r),
                    "delta_profitable_mass": round(
                        float(selected["scenarios"].get("profitable_outcome_coverage_mass") or 0)
                        - float(r["scenarios"].get("profitable_outcome_coverage_mass") or 0),
                        8,
                    ),
                    "delta_worst_case_loss": _delta_worst(selected, r),
                    "delta_expected_return": round(
                        float(selected["scenarios"].get("expected_net") or 0)
                        - float(r["scenarios"].get("expected_net") or 0),
                        8,
                    ),
                }
            )

    return {
        "n_eligible_markets": len(eligible),
        "n_pairs_evaluated": len(results),
        "selected": selected,
        "candidates": results[:50],
        "rejected": rejected[:100],
        "search_mode": "exhaustive_combinations",
    }


def _delta_worst(best: dict[str, Any], other: dict[str, Any]) -> float | None:
    a = best["scenarios"].get("worst_top10_loss")
    b = other["scenarios"].get("worst_top10_loss")
    if a is None or b is None:
        return None
    return round(float(a) - float(b), 8)


def _reject_reason(best: dict[str, Any], other: dict[str, Any]) -> str:
    if float(other.get("pair_score") or 0) < float(best.get("pair_score") or 0):
        return "lower_pair_score"
    bp = float(best["scenarios"].get("profitable_outcome_coverage_mass") or 0)
    op = float(other["scenarios"].get("profitable_outcome_coverage_mass") or 0)
    if op < bp:
        return "lower_profitable_top10_mass"
    if float(other.get("covered_top10_probability_mass") or 0) < float(best.get("covered_top10_probability_mass") or 0):
        return "lower_raw_covered_mass"
    return "tie_break_deterministic_order"
