"""Global coupon optimizer — research-only.

Evaluates coverage-market combinations across three fixtures jointly
to maximize coupon EV (not independent per-fixture argmax).
"""

from __future__ import annotations

import itertools
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.generate_tickets import (
    generate_64_tickets,
    write_tickets_artifacts,
)
from worldcup_predictor.research.bet_coverage_optimizer.models import (
    CoverageMarketEvaluation,
    CoverageRecommendation,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


@dataclass
class CouponOptimizerConfig:
    candidate_pool_per_fixture: int = 5
    stake_per_ticket: float = 1.0
    diversification_weight: float = 0.15
    overlap_penalty_weight: float = 0.20
    ev_weight: float = 0.65

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "CouponOptimizerConfig":
        d = dict(raw or {})
        return cls(
            candidate_pool_per_fixture=int(d.get("candidate_pool_per_fixture") or 5),
            stake_per_ticket=float(d.get("stake_per_ticket") or 1.0),
            diversification_weight=float(d.get("diversification_weight") or 0.15),
            overlap_penalty_weight=float(d.get("overlap_penalty_weight") or 0.20),
            ev_weight=float(d.get("ev_weight") or 0.65),
        )


@dataclass
class CouponOptimizationResult:
    coupon_score: float
    expected_coupon_value: float
    diversification_score: float
    overlap_penalty: float
    selected_coverage_by_fixture: dict[str, dict[str, Any]]
    recommendations: list[CoverageRecommendation]
    tickets: dict[str, Any]
    independent_baseline: dict[str, Any]
    research_only: bool = True
    owner_only: bool = True
    generated_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "coupon_score": self.coupon_score,
            "expected_coupon_value": self.expected_coupon_value,
            "diversification_score": self.diversification_score,
            "overlap_penalty": self.overlap_penalty,
            "selected_coverage_by_fixture": self.selected_coverage_by_fixture,
            "recommendations": [r.to_dict() for r in self.recommendations],
            "tickets": self.tickets,
            "independent_baseline": self.independent_baseline,
            "research_only": True,
            "owner_only": True,
            "generated_at": self.generated_at,
        }


def _coverage_pool(rec: CoverageRecommendation, *, pool: int) -> list[CoverageMarketEvaluation | None]:
    """Eligible coverage candidates (ranked) plus None for COVERAGE_MARKET_UNAVAILABLE."""
    out: list[CoverageMarketEvaluation | None] = []
    seen: set[str] = set()
    # Prefer ranked eligible
    key_to_ev = {e.market_key: e for e in ([rec.selected_coverage_market] if rec.selected_coverage_market else []) + list(rec.rejected_candidates)}
    for row in rec.ranked_candidates:
        key = str(row.get("market_key") or "")
        ev = key_to_ev.get(key)
        if not ev or not ev.eligible or ev.coverage_score is None:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(ev)
        if len(out) >= int(pool):
            break
    if not out:
        out = [None]
    return out


def _leg_model_prob(kind: str, *, exact: Any | None = None, coverage: CoverageMarketEvaluation | None = None) -> float:
    if kind == "exact" and exact is not None:
        return max(0.0, float(getattr(exact, "weighted_probability", 0.0) or 0.0))
    if kind == "coverage" and coverage is not None:
        return max(0.0, float(coverage.estimated_model_probability or 0.0))
    return 0.0


def _leg_odds(kind: str, *, exact: Any | None = None, coverage: CoverageMarketEvaluation | None = None) -> float | None:
    if kind == "exact" and exact is not None:
        o = getattr(exact, "odds", None)
        return float(o) if o and float(o) > 1.0 else None
    if kind == "coverage" and coverage is not None:
        o = coverage.odds
        return float(o) if o and float(o) > 1.0 else None
    return None


def estimate_coupon_ev(
    recommendations: list[CoverageRecommendation],
    coverages: list[CoverageMarketEvaluation | None],
    *,
    stake_per_ticket: float = 1.0,
) -> dict[str, float]:
    """
    Research EV under independence.

    - monetary_ev: sum over fully-priced tickets of p*combined_odds*stake - stake
      (never fabricates missing odds).
    - hit_mass: sum of ticket model probabilities (odds-independent research utility).
    - expected_coupon_value: monetary_ev when any ticket is fully priced, else hit_mass.
    """
    if len(recommendations) != 3 or len(coverages) != 3:
        raise ValueError("exactly 3 fixtures required")

    legs_per: list[list[tuple[str, float, float | None]]] = []
    for rec, cov in zip(recommendations, coverages):
        legs: list[tuple[str, float, float | None]] = []
        for ex in rec.selected_exact_scores[:3]:
            legs.append(("exact", _leg_model_prob("exact", exact=ex), _leg_odds("exact", exact=ex)))
        while len(legs) < 3:
            legs.append(("exact", 0.0, None))
        legs.append(("coverage", _leg_model_prob("coverage", coverage=cov), _leg_odds("coverage", coverage=cov)))
        legs_per.append(legs[:4])

    monetary_ev = 0.0
    hit_mass = 0.0
    priced_tickets = 0
    stake = float(stake_per_ticket)
    for combo in itertools.product(*legs_per):
        p = 1.0
        odds_vals: list[float] = []
        complete = True
        for _kind, prob, odd in combo:
            p *= float(prob)
            if odd is None or float(odd) <= 1.0:
                complete = False
            else:
                odds_vals.append(float(odd))
        hit_mass += p
        if complete and len(odds_vals) == 3:
            combined = odds_vals[0] * odds_vals[1] * odds_vals[2]
            monetary_ev += p * combined * stake - stake
            priced_tickets += 1

    expected = round(monetary_ev, 8) if priced_tickets > 0 else round(hit_mass, 8)
    return {
        "expected_coupon_value": expected,
        "monetary_ev": round(monetary_ev, 8),
        "hit_mass": round(hit_mass, 8),
        "priced_tickets": float(priced_tickets),
    }


def diversification_score(coverages: list[CoverageMarketEvaluation | None]) -> float:
    """Higher when market types / labels differ across fixtures."""
    types = [c.market_type if c else "unavailable" for c in coverages]
    labels = [c.market_label if c else "unavailable" for c in coverages]
    type_div = len(set(types)) / max(1, len(types))
    label_div = len(set(labels)) / max(1, len(labels))
    return round(0.6 * type_div + 0.4 * label_div, 8)


def overlap_penalty(coverages: list[CoverageMarketEvaluation | None]) -> float:
    """Penalty when coverage markets share type or heavily overlapping semantics."""
    types = [c.market_type if c else None for c in coverages if c is not None]
    if len(types) < 2:
        return 0.0
    # Fraction of pairwise same-type pairs
    pairs = list(itertools.combinations(types, 2))
    same = sum(1 for a, b in pairs if a == b)
    return round(same / max(1, len(pairs)), 8)


def _normalize_ev(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if abs(hi - lo) < 1e-12:
        return [0.5 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def apply_coverage_choice(
    rec: CoverageRecommendation,
    coverage: CoverageMarketEvaluation | None,
) -> CoverageRecommendation:
    """Return a shallow-copied recommendation with the chosen fourth market."""
    out = deepcopy(rec)
    out.selected_coverage_market = coverage
    if coverage is None:
        from worldcup_predictor.research.bet_coverage_optimizer import STATUS_COVERAGE_UNAVAILABLE

        out.status = STATUS_COVERAGE_UNAVAILABLE
        out.blockers = list(dict.fromkeys(list(out.blockers) + [STATUS_COVERAGE_UNAVAILABLE]))
        covered = [e.score for e in out.selected_exact_scores]
    else:
        from worldcup_predictor.research.bet_coverage_optimizer import STATUS_OK

        out.status = STATUS_OK
        out.blockers = [b for b in out.blockers if b != "COVERAGE_MARKET_UNAVAILABLE"]
        covered = list(dict.fromkeys(list(coverage.covered_scores) + [e.score for e in out.selected_exact_scores]))
    out.covered_top_n_scores = covered
    out.uncovered_top_n_scores = [s.score for s in out.top_n_scores_list if s.score not in set(covered)]
    return out


def optimize_coupon(
    recommendations: list[CoverageRecommendation],
    *,
    config: CouponOptimizerConfig | dict[str, Any] | None = None,
) -> CouponOptimizationResult:
    if len(recommendations) != 3:
        raise ValueError("coupon_optimizer requires exactly 3 fixture recommendations")
    cfg = config if isinstance(config, CouponOptimizerConfig) else CouponOptimizerConfig.from_dict(config)

    pools = [_coverage_pool(r, pool=cfg.candidate_pool_per_fixture) for r in recommendations]

    # Independent baseline = currently selected fourth markets
    baseline_cov = [r.selected_coverage_market for r in recommendations]
    baseline_metrics = estimate_coupon_ev(recommendations, baseline_cov, stake_per_ticket=cfg.stake_per_ticket)
    baseline_ev = float(baseline_metrics["expected_coupon_value"])
    baseline_div = diversification_score(baseline_cov)
    baseline_pen = overlap_penalty(baseline_cov)

    candidates_eval: list[dict[str, Any]] = []
    for combo in itertools.product(*pools):
        metrics = estimate_coupon_ev(recommendations, list(combo), stake_per_ticket=cfg.stake_per_ticket)
        div = diversification_score(list(combo))
        pen = overlap_penalty(list(combo))
        candidates_eval.append(
            {
                "combo": list(combo),
                "ev": float(metrics["expected_coupon_value"]),
                "monetary_ev": float(metrics["monetary_ev"]),
                "hit_mass": float(metrics["hit_mass"]),
                "div": div,
                "pen": pen,
            }
        )

    evs = [c["ev"] for c in candidates_eval]
    n_ev = _normalize_ev(evs)
    for i, c in enumerate(candidates_eval):
        c["coupon_score"] = round(
            cfg.ev_weight * n_ev[i] + cfg.diversification_weight * c["div"] - cfg.overlap_penalty_weight * c["pen"],
            8,
        )

    candidates_eval.sort(
        key=lambda c: (
            -float(c["coupon_score"]),
            -float(c["ev"]),
            -float(c["div"]),
            str([x.market_key if x else "none" for x in c["combo"]]),
        )
    )
    best = candidates_eval[0]
    best_combo: list[CoverageMarketEvaluation | None] = best["combo"]

    optimized_recs = [apply_coverage_choice(r, cov) for r, cov in zip(recommendations, best_combo)]
    tickets = generate_64_tickets(optimized_recs, stake_per_ticket=cfg.stake_per_ticket)

    selected_map = {
        str(r.fixture_id): (
            {
                "market_key": cov.market_key,
                "market_label": cov.market_label,
                "odds": cov.odds,
                "coverage_score": cov.coverage_score,
                "estimated_model_probability": cov.estimated_model_probability,
            }
            if cov
            else None
        )
        for r, cov in zip(optimized_recs, best_combo)
    }

    return CouponOptimizationResult(
        coupon_score=float(best["coupon_score"]),
        expected_coupon_value=float(best["ev"]),
        diversification_score=float(best["div"]),
        overlap_penalty=float(best["pen"]),
        selected_coverage_by_fixture=selected_map,
        recommendations=optimized_recs,
        tickets=tickets,
        independent_baseline={
            "expected_coupon_value": baseline_ev,
            "hit_mass": float(baseline_metrics["hit_mass"]),
            "monetary_ev": float(baseline_metrics["monetary_ev"]),
            "diversification_score": baseline_div,
            "overlap_penalty": baseline_pen,
            "selected_coverage_by_fixture": {
                str(r.fixture_id): (
                    {"market_key": c.market_key, "market_label": c.market_label, "odds": c.odds}
                    if c
                    else None
                )
                for r, c in zip(recommendations, baseline_cov)
            },
            "ev_delta_vs_independent": round(float(best["ev"]) - baseline_ev, 8),
            "best_hit_mass": float(best.get("hit_mass") or 0.0),
        },
    )


def write_coupon_artifacts(result: CouponOptimizationResult, output_dir) -> dict[str, str]:
    from pathlib import Path
    import json

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    payload = result.to_dict()
    # tickets already nested; also write dedicated 64 files
    paths.update(write_tickets_artifacts(result.tickets, output_dir))
    (output_dir / "coupon_optimizer.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    paths["coupon_optimizer.json"] = str(output_dir / "coupon_optimizer.json")
    return paths
