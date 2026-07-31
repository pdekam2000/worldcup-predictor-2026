"""Insurance ticket optimizer — selective tickets, never default 125."""

from __future__ import annotations

import itertools
from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.generate_tickets import _selection_legs
from worldcup_predictor.research.bet_coverage_optimizer.insurance.constants import DEFAULT_INSURANCE
from worldcup_predictor.research.bet_coverage_optimizer.insurance.insurance_candidates import (
    build_insurance_raw_candidates,
)
from worldcup_predictor.research.bet_coverage_optimizer.insurance.insurance_scoring import score_insurance_candidates
from worldcup_predictor.research.bet_coverage_optimizer.insurance.schemas import (
    InsuranceCandidate,
    InsuranceTicket,
    UncoveredMassReport,
)
from worldcup_predictor.research.bet_coverage_optimizer.insurance.uncovered_mass import (
    compute_uncovered_mass,
    primary_covered_score_set,
)
from worldcup_predictor.research.bet_coverage_optimizer.models import CoverageRecommendation
from worldcup_predictor.research.bet_coverage_optimizer.scoring import normalize_batch


def _primary_leg_prob(rec: CoverageRecommendation, leg: dict[str, Any]) -> float:
    kind = leg.get("kind")
    if kind == "exact_score":
        score = leg.get("score")
        for ex in rec.selected_exact_scores:
            if ex.score == score:
                return max(0.0, float(ex.weighted_probability or 0.0))
        return 0.0
    if kind == "coverage" and rec.selected_coverage_market:
        return max(0.0, float(rec.selected_coverage_market.estimated_model_probability or 0.0))
    return 0.0


def _primary_leg_odds(leg: dict[str, Any]) -> float | None:
    o = leg.get("odds")
    try:
        return float(o) if o is not None and float(o) > 1.0 else None
    except (TypeError, ValueError):
        return None


def build_fixture_insurance_candidates(
    rec: CoverageRecommendation,
    *,
    raw_payload: dict[str, Any] | None = None,
    real_odds_markets: list[dict[str, Any]] | None = None,
    insurance_cfg: dict[str, Any] | None = None,
    insurance_weights: dict[str, Any] | None = None,
) -> tuple[UncoveredMassReport, list[InsuranceCandidate]]:
    uncovered = compute_uncovered_mass(rec)
    top_pairs = [(s.score, float(s.probability)) for s in rec.top_n_scores_list]
    exacts = [e.score for e in rec.selected_exact_scores]
    primary = primary_covered_score_set(rec)

    raw_cands = build_insurance_raw_candidates(
        int(rec.fixture_id),
        uncovered=uncovered,
        exact_scores=exacts,
        primary_covered=primary,
        top_n_pairs=top_pairs,
        raw_payload=raw_payload,
    )
    if real_odds_markets:
        # Already mapped rows from real_odds loader
        from worldcup_predictor.research.bet_coverage_optimizer.insurance.insurance_candidates import (
            enrich_candidate_against_uncovered,
        )

        for m in real_odds_markets:
            enriched = enrich_candidate_against_uncovered(
                dict(m),
                uncovered=uncovered,
                exact_scores=set(exacts),
                primary_covered=primary,
                top_n_pairs=top_pairs,
            )
            if enriched:
                raw_cands.append(enriched)

    ranked = score_insurance_candidates(raw_cands, insurance_cfg=insurance_cfg, weights=insurance_weights)
    return uncovered, ranked


def _eligible_top(cands: list[InsuranceCandidate], k: int) -> list[InsuranceCandidate]:
    elig = [c for c in cands if c.eligible and c.insurance_score is not None]
    return elig[: max(0, int(k))]


def optimize_insurance_tickets(
    recommendations: list[CoverageRecommendation],
    *,
    candidates_by_fixture: dict[int, list[InsuranceCandidate]],
    uncovered_by_fixture: dict[int, UncoveredMassReport],
    insurance_cfg: dict[str, Any] | None = None,
) -> list[InsuranceTicket]:
    """
    Build selective insurance tickets (default max 15, never full 5^3=125).

    Priority:
      1) single-insurance-leg tickets
      2) two-insurance-leg tickets if joint mass high enough
      3) triple only if explicitly enabled
    """
    if len(recommendations) != 3:
        raise ValueError("insurance ticket optimizer requires exactly 3 fixtures")
    cfg = {**DEFAULT_INSURANCE, **(insurance_cfg or {})}
    max_t = int(cfg.get("max_insurance_tickets", 15))
    min_t = int(cfg.get("min_insurance_tickets", 3))
    top_k = int(cfg.get("top_k_candidates", 5))
    allow_triple = bool(cfg.get("allow_triple_insurance", False))
    min_two = float(cfg.get("min_two_leg_joint_mass", 0.02))

    recs = list(recommendations)
    pools = {
        int(r.fixture_id): _eligible_top(candidates_by_fixture.get(int(r.fixture_id), []), top_k) for r in recs
    }
    primary_legs = {int(r.fixture_id): _selection_legs(r) for r in recs}

    draft: list[dict[str, Any]] = []

    def _ticket_from_mask(ins_map: dict[int, InsuranceCandidate], reason: str) -> dict[str, Any]:
        selections: list[dict[str, Any]] = []
        probs: list[float] = []
        odds_vals: list[float] = []
        complete_odds = True
        risk = 0.0
        for r in recs:
            fid = int(r.fixture_id)
            if fid in ins_map:
                cand = ins_map[fid]
                selections.append(
                    {
                        "fixture_id": fid,
                        "selection_id": f"insurance:{cand.market_key}",
                        "label": cand.market_label,
                        "kind": "insurance",
                        "odds": cand.odds,
                        "market_key": cand.market_key,
                    }
                )
                probs.append(max(0.0, float(cand.model_probability or 0.0)))
                if cand.odds is None or float(cand.odds) <= 1.0:
                    complete_odds = False
                else:
                    odds_vals.append(float(cand.odds))
                risk += float(cand.residual_risk_reduction or 0.0)
            else:
                # Use main coverage as the non-insurance leg for coupon survival paths
                # Prefer highest-prob primary exact for single-leg insurance companions
                legs = primary_legs[fid]
                best = max(legs[:3], key=lambda L: _primary_leg_prob(r, L), default=legs[0])
                selections.append(
                    {
                        "fixture_id": fid,
                        "selection_id": best["selection_id"],
                        "label": best["label"],
                        "kind": best["kind"],
                        "odds": best.get("odds"),
                        "score": best.get("score"),
                    }
                )
                probs.append(_primary_leg_prob(r, best))
                o = _primary_leg_odds(best)
                if o is None:
                    complete_odds = False
                else:
                    odds_vals.append(o)

        joint_p = 1.0
        for p in probs:
            joint_p *= float(p)
        combined = None
        monetary = None
        if complete_odds and len(odds_vals) == 3:
            combined = round(odds_vals[0] * odds_vals[1] * odds_vals[2], 6)
            monetary = round(joint_p * combined - 1.0, 8)  # per unit stake
        types = [ins_map[f].market_type for f in ins_map]
        div = len(set(types)) / max(1, len(types))
        # overlap penalty: reuse same market_type across insurance legs
        ov = 0.0
        if len(types) >= 2:
            pairs = list(itertools.combinations(types, 2))
            ov = sum(1 for a, b in pairs if a == b) / max(1, len(pairs))
        return {
            "selections": selections,
            "insurance_fixture_ids": sorted(ins_map.keys()),
            "n_insurance_legs": len(ins_map),
            "combined_odds": combined,
            "modeled_joint_hit_probability": round(joint_p, 10),
            "monetary_ev": monetary,
            "probability_mass_utility": round(joint_p, 10),
            "residual_risk_reduction": round(risk, 8),
            "diversification_score": round(div, 8),
            "overlap_penalty": round(ov, 8),
            "inclusion_reason": reason,
            "utility": round(joint_p + 0.5 * risk - 0.2 * ov, 10),
        }

    # Single-leg first
    for i, r in enumerate(recs):
        fid = int(r.fixture_id)
        for cand in pools[fid]:
            draft.append(_ticket_from_mask({fid: cand}, "single_insurance_leg_priority"))

    # Two-leg next
    fids = [int(r.fixture_id) for r in recs]
    for a, b in itertools.combinations(fids, 2):
        for ca in pools[a][:3]:
            for cb in pools[b][:3]:
                joint = float(ca.incremental_uncovered_probability_mass) * float(cb.incremental_uncovered_probability_mass)
                if joint < min_two:
                    continue
                draft.append(_ticket_from_mask({a: ca, b: cb}, "two_insurance_leg_high_joint_mass"))

    if allow_triple:
        for ca in pools[fids[0]][:2]:
            for cb in pools[fids[1]][:2]:
                for cc in pools[fids[2]][:2]:
                    draft.append(
                        _ticket_from_mask(
                            {fids[0]: ca, fids[1]: cb, fids[2]: cc},
                            "triple_insurance_explicitly_enabled",
                        )
                    )

    # Deterministic unique by selection ids
    seen: set[tuple] = set()
    unique: list[dict[str, Any]] = []
    for d in draft:
        key = tuple((s["fixture_id"], s["selection_id"]) for s in d["selections"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(d)

    # Score
    utils = [u["utility"] for u in unique]
    risks = [u["residual_risk_reduction"] for u in unique]
    divs = [u["diversification_score"] for u in unique]
    ovs = [u["overlap_penalty"] for u in unique]
    n_u = normalize_batch(utils)
    n_r = normalize_batch(risks)
    n_d = normalize_batch(divs)
    n_o = normalize_batch(ovs)
    for i, u in enumerate(unique):
        # Prefer fewer insurance legs
        leg_bonus = 0.15 if u["n_insurance_legs"] == 1 else (0.05 if u["n_insurance_legs"] == 2 else 0.0)
        u["insurance_coupon_score"] = round(
            0.55 * n_u[i] + 0.25 * n_r[i] + 0.15 * n_d[i] - 0.10 * n_o[i] + leg_bonus,
            8,
        )

    unique.sort(
        key=lambda u: (
            u["n_insurance_legs"],  # single first among equal score via secondary
            -float(u["insurance_coupon_score"]),
            -float(u["probability_mass_utility"]),
            str(u["selections"]),
        )
    )
    # Re-sort primarily by score but keep single-leg preference in score already
    unique.sort(
        key=lambda u: (
            -float(u["insurance_coupon_score"]),
            u["n_insurance_legs"],
            -float(u["probability_mass_utility"]),
            str([(s["fixture_id"], s["selection_id"]) for s in u["selections"]]),
        )
    )

    selected = unique[:max_t]
    if len(selected) < min_t and unique:
        selected = unique[: max(min_t, min(len(unique), max_t))]

    # Hard guarantee: never 125
    assert len(selected) <= max_t
    assert len(selected) <= 64  # safety vs accidental explosion

    tickets: list[InsuranceTicket] = []
    for i, u in enumerate(selected, start=1):
        tickets.append(
            InsuranceTicket(
                ticket_id=f"INS-{i:03d}",
                rank=i,
                selections=u["selections"],
                insurance_fixture_ids=u["insurance_fixture_ids"],
                n_insurance_legs=u["n_insurance_legs"],
                combined_odds=u["combined_odds"],
                modeled_joint_hit_probability=u["modeled_joint_hit_probability"],
                monetary_ev=u["monetary_ev"],
                probability_mass_utility=u["probability_mass_utility"],
                residual_risk_reduction=u["residual_risk_reduction"],
                diversification_score=u["diversification_score"],
                overlap_penalty=u["overlap_penalty"],
                insurance_coupon_score=u["insurance_coupon_score"],
                inclusion_reason=u["inclusion_reason"],
            )
        )
    return tickets
